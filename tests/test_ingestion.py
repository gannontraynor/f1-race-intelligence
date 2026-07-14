from __future__ import annotations

import pandas as pd
import pytest

from pipelines.ingestion.load_session import (
    build_stints,
    duration_to_milliseconds,
    normalize_laps,
    slugify,
)


def test_slugify() -> None:
    assert slugify("Monaco Grand Prix") == "monaco-grand-prix"
    assert slugify("São Paulo Grand Prix") == "sao-paulo-grand-prix"


def test_duration_to_milliseconds() -> None:
    values = pd.Series(
        [
            pd.Timedelta(seconds=90.123),
            pd.NaT,
        ]
    )

    result = duration_to_milliseconds(values)

    assert result.iloc[0] == 90123
    assert pd.isna(result.iloc[1])


def test_normalize_laps() -> None:
    raw = pd.DataFrame(
        {
            "Driver": ["NOR"],
            "DriverNumber": ["4"],
            "LapNumber": [1.0],
            "Stint": [1.0],
            "LapTime": [pd.Timedelta(seconds=90)],
            "Sector1Time": [pd.Timedelta(seconds=30)],
            "Sector2Time": [pd.Timedelta(seconds=31)],
            "Sector3Time": [pd.Timedelta(seconds=29)],
            "Compound": ["MEDIUM"],
            "TyreLife": [1.0],
            "FreshTyre": [True],
            "Team": ["McLaren"],
            "TrackStatus": ["1"],
            "Position": [1.0],
            "PitInTime": pd.Series([pd.NaT], dtype="timedelta64[ns]"),
            "PitOutTime": pd.Series([pd.NaT], dtype="timedelta64[ns]"),
            "IsAccurate": [True],
        }
    )

    result = normalize_laps(raw)

    assert len(result) == 1
    assert result.loc[0, "driver_code"] == "NOR"
    assert result.loc[0, "lap_number"] == 1
    assert result.loc[0, "lap_time_ms"] == 90000
    assert result.loc[0, "compound"] == "MEDIUM"


def test_normalize_laps_rejects_missing_columns() -> None:
    raw = pd.DataFrame({"Driver": ["NOR"]})

    with pytest.raises(ValueError, match="missing required columns"):
        normalize_laps(raw)


def test_build_stints() -> None:
    laps = pd.DataFrame(
        {
            "driver_code": ["NOR", "NOR", "NOR"],
            "team": ["McLaren", "McLaren", "McLaren"],
            "stint": pd.Series([1, 1, 2], dtype="Int64"),
            "compound": ["MEDIUM", "MEDIUM", "HARD"],
            "lap_number": pd.Series([1, 2, 3], dtype="Int64"),
            "tyre_life": pd.Series([1.0, 2.0, 1.0], dtype="Float64"),
            "lap_time_ms": pd.Series(
                [90000, 89000, 88000],
                dtype="Int64",
            ),
        }
    )

    result = build_stints(laps)

    assert len(result) == 2

    first_stint = result.iloc[0]
    assert first_stint["driver_code"] == "NOR"
    assert first_stint["start_lap"] == 1
    assert first_stint["end_lap"] == 2
    assert first_stint["lap_count"] == 2
    assert first_stint["median_lap_time_ms"] == 89500