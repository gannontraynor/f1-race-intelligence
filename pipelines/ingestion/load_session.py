"""Load and validate one Formula 1 session using FastF1."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final
from unidecode import unidecode

import fastf1
import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CACHE_DIR: Final[Path] = PROJECT_ROOT / ".cache" / "fastf1"
RAW_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "processed"

VALID_SESSION_TYPES: Final[set[str]] = {
    "FP1",
    "FP2",
    "FP3",
    "Q",
    "SQ",
    "S",
    "R",
}


@dataclass(frozen=True)
class IngestionSummary:
    year: int
    event: str
    session_type: str
    session_name: str
    drivers: int
    lap_rows: int
    stint_rows: int
    valid_lap_times: int
    missing_lap_times: int
    output_directory: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load one historical Formula 1 session."
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Season year, for example 2025.",
    )
    parser.add_argument(
        "--event",
        required=True,
        help='Event name or round number, for example "Monaco" or 8.',
    )
    parser.add_argument(
        "--session",
        required=True,
        type=str.upper,
        choices=sorted(VALID_SESSION_TYPES),
        help="Session type, such as R, Q, S, FP1, FP2, or FP3.",
    )

    return parser.parse_args()


def slugify(value: str) -> str:
    """Convert a human-readable value into a filesystem-safe slug."""

    normalized = unidecode(value).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def ensure_directories() -> None:
    for directory in (CACHE_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def duration_to_milliseconds(series: pd.Series) -> pd.Series:
    """Convert a pandas timedelta series into nullable milliseconds."""

    return series.dt.total_seconds().mul(1000).round().astype("Int64")


def normalize_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Select and normalize lap-level fields used by the application."""

    required_columns = [
        "Driver",
        "DriverNumber",
        "LapNumber",
        "Stint",
        "LapTime",
        "Sector1Time",
        "Sector2Time",
        "Sector3Time",
        "Compound",
        "TyreLife",
        "FreshTyre",
        "Team",
        "TrackStatus",
        "Position",
        "PitInTime",
        "PitOutTime",
        "IsAccurate",
    ]

    missing_columns = sorted(set(required_columns) - set(laps.columns))
    if missing_columns:
        raise ValueError(
            f"FastF1 lap data is missing required columns: {missing_columns}"
        )

    normalized = laps.loc[:, required_columns].copy()

    normalized["lap_number"] = normalized["LapNumber"].astype("Int64")
    normalized["stint"] = normalized["Stint"].astype("Int64")
    normalized["position"] = normalized["Position"].astype("Int64")
    normalized["tyre_life"] = normalized["TyreLife"].astype("Float64")

    normalized["lap_time_ms"] = duration_to_milliseconds(
        normalized["LapTime"]
    )
    normalized["sector_1_ms"] = duration_to_milliseconds(
        normalized["Sector1Time"]
    )
    normalized["sector_2_ms"] = duration_to_milliseconds(
        normalized["Sector2Time"]
    )
    normalized["sector_3_ms"] = duration_to_milliseconds(
        normalized["Sector3Time"]
    )
    normalized["pit_in_ms"] = duration_to_milliseconds(
        normalized["PitInTime"]
    )
    normalized["pit_out_ms"] = duration_to_milliseconds(
        normalized["PitOutTime"]
    )

    normalized = normalized.rename(
        columns={
            "Driver": "driver_code",
            "DriverNumber": "driver_number",
            "Compound": "compound",
            "FreshTyre": "fresh_tyre",
            "Team": "team",
            "TrackStatus": "track_status",
            "IsAccurate": "is_accurate",
        }
    )

    normalized = normalized[
        [
            "driver_code",
            "driver_number",
            "team",
            "lap_number",
            "stint",
            "position",
            "lap_time_ms",
            "sector_1_ms",
            "sector_2_ms",
            "sector_3_ms",
            "compound",
            "tyre_life",
            "fresh_tyre",
            "track_status",
            "pit_in_ms",
            "pit_out_ms",
            "is_accurate",
        ]
    ]

    return normalized.sort_values(
        ["driver_code", "lap_number"],
        ignore_index=True,
    )


def build_stints(laps: pd.DataFrame) -> pd.DataFrame:
    """Aggregate normalized lap records into driver stints."""

    valid_stints = laps.dropna(
        subset=["driver_code", "stint", "lap_number"]
    ).copy()

    stints = (
        valid_stints.groupby(
            ["driver_code", "team", "stint", "compound"],
            dropna=False,
            as_index=False,
        )
        .agg(
            start_lap=("lap_number", "min"),
            end_lap=("lap_number", "max"),
            lap_count=("lap_number", "count"),
            starting_tyre_life=("tyre_life", "min"),
            ending_tyre_life=("tyre_life", "max"),
            median_lap_time_ms=("lap_time_ms", "median"),
        )
        .sort_values(["driver_code", "stint"], ignore_index=True)
    )

    stints["median_lap_time_ms"] = (
        stints["median_lap_time_ms"].round().astype("Int64")
    )

    return stints


def save_outputs(
    *,
    year: int,
    event_name: str,
    session_type: str,
    raw_laps: pd.DataFrame,
    normalized_laps: pd.DataFrame,
    stints: pd.DataFrame,
    metadata: dict[str, object],
) -> Path:
    event_slug = slugify(event_name)
    session_slug = session_type.lower()

    raw_directory = (
        RAW_DATA_DIR
        / f"year={year}"
        / f"event={event_slug}"
        / f"session={session_slug}"
    )
    processed_directory = (
        PROCESSED_DATA_DIR
        / f"year={year}"
        / f"event={event_slug}"
        / f"session={session_slug}"
    )

    raw_directory.mkdir(parents=True, exist_ok=True)
    processed_directory.mkdir(parents=True, exist_ok=True)

    raw_laps.to_parquet(
        raw_directory / "laps.parquet",
        index=False,
    )

    normalized_laps.to_parquet(
        processed_directory / "laps.parquet",
        index=False,
    )

    stints.to_parquet(
        processed_directory / "stints.parquet",
        index=False,
    )

    with (processed_directory / "metadata.json").open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(metadata, metadata_file, indent=2, default=str)

    return processed_directory


def ingest_session(
    year: int,
    event: str | int,
    session_type: str,
) -> IngestionSummary:
    ensure_directories()
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    logging.info(
        "Loading season=%s event=%s session=%s",
        year,
        event,
        session_type,
    )

    session = fastf1.get_session(year, event, session_type)
    session.load(
        laps=True,
        telemetry=False,
        weather=False,
        messages=False,
    )

    raw_laps = pd.DataFrame(session.laps).copy()

    if raw_laps.empty:
        raise ValueError("The loaded session contains no lap records.")

    normalized_laps = normalize_laps(raw_laps)
    stints = build_stints(normalized_laps)

    event_name = str(session.event["EventName"])
    session_name = str(session.name)

    metadata: dict[str, object] = {
        "year": year,
        "event_name": event_name,
        "session_name": session_name,
        "session_type": session_type,
        "event_date": session.event.get("EventDate"),
        "country": session.event.get("Country"),
        "location": session.event.get("Location"),
        "driver_codes": sorted(
            normalized_laps["driver_code"].dropna().unique().tolist()
        ),
    }

    output_directory = save_outputs(
        year=year,
        event_name=event_name,
        session_type=session_type,
        raw_laps=raw_laps,
        normalized_laps=normalized_laps,
        stints=stints,
        metadata=metadata,
    )

    summary = IngestionSummary(
        year=year,
        event=event_name,
        session_type=session_type,
        session_name=session_name,
        drivers=normalized_laps["driver_code"].nunique(),
        lap_rows=len(normalized_laps),
        stint_rows=len(stints),
        valid_lap_times=int(normalized_laps["lap_time_ms"].notna().sum()),
        missing_lap_times=int(normalized_laps["lap_time_ms"].isna().sum()),
        output_directory=str(output_directory.relative_to(PROJECT_ROOT)),
    )

    return summary


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    arguments = parse_arguments()

    event: str | int
    event = (
        int(arguments.event)
        if arguments.event.isdigit()
        else arguments.event
    )

    try:
        summary = ingest_session(
            year=arguments.year,
            event=event,
            session_type=arguments.session,
        )
    except Exception:
        logging.exception("Session ingestion failed.")
        return 1

    print(json.dumps(asdict(summary), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())