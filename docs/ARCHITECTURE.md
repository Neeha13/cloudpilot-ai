# Architecture

```text
Next.js browser UI
   | HTTP / JSON
   v
FastAPI service
   |-- Dashboard API
   |-- Spend API
   |-- Recommendations engine (explainable rules)
   |-- Anomaly detection (baseline comparison)
   |-- Copilot API (grounded fallback; optional LLM)
   |-- Feedback API
   v
SQLite (demo feedback persistence) + synthetic seed dataset
```

## Trust boundaries
- Frontend never receives cloud credentials.
- No real cloud account integration in this MVP.
- No infrastructure mutation APIs exist.
- Optional LLM receives aggregate demo context, not secrets.
- Feedback is stored in a local SQLite database.

## Future production architecture
Replace synthetic seed data with a secure ingestion pipeline for AWS Cost and Usage Reports and resource inventory. Add authentication, tenant isolation, encryption, audit logs, data retention controls, pricing-aware savings calculations, and human approval before any remediation.
