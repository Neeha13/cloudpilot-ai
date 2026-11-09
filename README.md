# CloudPilot AI

AI-assisted cloud cost intelligence and optimization platform. This is an independent portfolio MVP built with synthetic AWS-style billing and resource data. It does not connect to a real cloud account or execute infrastructure changes.

## Product scope

- Cloud spend overview and service breakdown
- Spend trend and budget utilization
- Recommendation Intelligence v2: evidence, transparent savings formulas, confidence and risk scoring, and a weighted priority score (see [docs/decisions/001-recommendation-intelligence-v2.md](docs/decisions/001-recommendation-intelligence-v2.md))
- Recommendation lifecycle (investigate → plan → implement, snooze, dismiss with reason, reopen) with an append-only audit log
- Decision analytics (coverage, acceptance rate, dismissal reasons, savings by stage)
- Anomaly Detection v2: median baselines with robust z-scores; spike, gradual-growth and new-service types; severity; walk-forward history; acknowledge/investigate/resolve lifecycle; investigation panel (see [docs/decisions/002-anomaly-detection-v2.md](docs/decisions/002-anomaly-detection-v2.md))
- Copilot Q&A returning structured, sourced answer cards built from the engine
- Data integrity (Sprint 1): the dataset is persisted in SQLite as versioned snapshots. Every API reads one snapshot per request; refresh is controlled, validated and atomic; refresh history and data freshness are visible in the header (see [docs/decisions/003-data-integrity-snapshots.md](docs/decisions/003-data-integrity-snapshots.md))
- API tests and product documentation

## Stack

- Frontend: Next.js App Router, React, TypeScript, Recharts
- Backend: Python, FastAPI, SQLite
- Data: synthetic AWS-style billing/resource records
- AI layer: explainable recommendation and anomaly rules; optional OpenAI-powered natural-language response when `OPENAI_API_KEY` is configured

> The default mode is deterministic and works without an API key. The optional LLM mode is an enhancement, not a prerequisite.

## Run locally

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000

## Key API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/recommendations` | Scored recommendations with lifecycle status |
| `GET /api/recommendations/{id}` | One recommendation plus its decision history |
| `POST /api/recommendations/{id}/actions` | `{action, reason?, note?, snooze_days?}`; 409 on an invalid transition |
| `GET /api/recommendations/model` | Scoring weights, definitions and dismissal reasons |
| `GET /api/recommendations/analytics` | Decision analytics from recorded interactions |
| `GET /api/anomalies` | Anomalies detected this month, with status, most severe first |
| `GET /api/anomalies/history` | All detections across months plus a summary (by status, service, severity) |
| `GET /api/anomalies/{id}` | Investigation detail: timeline, attribution, related recommendations, history |
| `POST /api/anomalies/{id}/actions` | `{action, resolution?, note?}`; 409 on an invalid transition |
| `GET /api/anomalies/config` | Detection thresholds and resolution options |
| `GET /api/dataset` | Active snapshot metadata: `snapshot_id`, `dataset_id`, billing period, freshness, last refresh |
| `POST /api/dataset/refresh` | Optional `{reference_date?, seed?}`. `created` / `unchanged`; 409 while another refresh runs; 500 on failure (previous snapshot stays active) |
| `GET /api/dataset/snapshots` | All snapshots, newest first, with the active one |
| `GET /api/dataset/snapshots/{snapshot_id}` | Metadata of one (possibly superseded) snapshot |
| `GET /api/dataset/refresh-history` | Refresh runs: trigger, status, error, snapshot produced |
| `GET /api/dataset/migrations` | Applied schema migrations and their backup files |

Every data endpoint (`/api/dashboard`, `/api/spend`, `/api/resources`, recommendations, anomalies, `/api/copilot`) accepts `?snapshot_id=` to read a specific snapshot, and returns `X-Snapshot-Id` / `X-Dataset-Id` headers.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Database migrations and backups

Schema changes are additive, versioned migrations recorded in `schema_migrations` and applied on startup. Before migrating a database that already holds data, the API writes a verified copy to `backend/backups/` (SQLite online backup + integrity check). Databases and backups are git-ignored.

## Important limitations

- The included data is synthetic. Do not present it as real customer savings or real AWS account data.
- Recommendations are advisory. The MVP does not stop, resize, delete, or modify cloud resources.
- Savings are estimates based on simplified assumptions and must be validated against actual utilization, pricing, commitments, and workload requirements.
- The default copilot is grounded in deterministic data and rules. Configure an OpenAI API key only if you want optional generated explanations. Never commit secrets.

## Portfolio use

Use this project to demonstrate product discovery, user segmentation, MVP scoping, technical execution, explainable AI, measurement, and iterative product decisions. Update the project with real user research and usability-test findings before claiming validated outcomes.
