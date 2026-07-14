# System Architecture

## Philosophy

The platform is intentionally designed as a collection of independent services with clear responsibilities.

Every layer should be replaceable without affecting the rest of the system.

```
                Browser
                    │
         React / Next.js Frontend
                    │
             REST / GraphQL API
                    │
          FastAPI Application Layer
                    │
    ┌───────────────┴───────────────┐
    │                               │
 Analytics Engine            AI Services
    │                               │
    └───────────────┬───────────────┘
                    │
             PostgreSQL Database
                    │
              Raw Data Storage
                 (AWS S3)
```

---

## Major Components

### Frontend

Responsibilities

- Interactive dashboards
- Data visualization
- Driver comparison
- Race timeline
- Strategy exploration
- User interaction

Technology

- React
- TypeScript
- Plotly
- Tailwind CSS

---

### API Layer

Responsibilities

- Authentication
- Request validation
- Analytics endpoints
- Data aggregation
- AI orchestration

Technology

- FastAPI
- Pydantic

---

### Analytics Engine

Contains deterministic business logic.

Examples:

- Pace calculations
- Tire degradation
- Consistency metrics
- Pit stop analysis
- Strategy evaluation
- Driver comparison

This layer should contain **zero AI**.

---

### AI Layer

AI should never perform calculations directly.

Instead it should:

- retrieve analysis
- explain findings
- answer natural language questions
- summarize race events

The analytics engine remains the source of truth.

---

### Database

Relational data:

- Seasons
- Events
- Sessions
- Drivers
- Teams
- Laps
- Stints
- Pit Stops

---

### Object Storage

AWS S3 stores:

- Raw session data
- Telemetry
- Processed parquet files
- Generated reports

---

## Architectural Principles

- API-first
- Strong typing
- Testable business logic
- Infrastructure as code
- Containerized services
- Cloud-native deployment
- Observable systems
- Modular components