# Decision 003 — Data integrity: persisted dataset snapshots

Status: Implemented (Nov 2026, Sprint 1) · Validation: automated tests and browser verification; not yet tested with users

## Problem

Every API already read one in-memory dataset, so totals reconciled. Three integrity problems remained:

- **Nothing was persisted.** The dataset was rebuilt from `date.today()` whenever the server started. History was lost, and the data shifted on its own at each month boundary.
- **Decisions could become detached.** Month-based anomaly ids disappeared after a rollover, orphaning their lifecycle events. Recommendation statuses silently carried over onto different data.
- **"Refresh data" didn't refresh anything.** The button re-read the same cache, and "generated_at" was the time the process started.

## Hypothesis

Users trust figures they can trace. If every screen states which snapshot it shows, when that data was produced, and whether a refresh changed anything, numbers that disagree, or that change unexplained, stop being possible. Measures to track:

- support questions of the form "why did this number change";
- refresh failure rate, from `refresh_runs`.

## What was built

| Area | Decision |
| --- | --- |
| Identifiers | **`dataset_id`** is a content hash: identical data gets the identical id, and it is unchanged from before Sprint 1. **`snapshot_id`** is one persisted, activated version. Re-activating identical content creates a new `snapshot_id` with the same `dataset_id`. |
| Storage | `dataset_snapshots`, `billing_records`, `resources`, `utilization_metrics` (a missing metric is stored as `missing`, not as 0) and `refresh_runs`. Lifecycle event tables gain a nullable `snapshot_id`. |
| Atomic activation | A new snapshot and all its rows are inserted, read back and re-hashed, then swapped to `active`, all inside one `BEGIN IMMEDIATE` transaction. Any error rolls everything back. A partial unique index makes a second active snapshot impossible. |
| Failure handling | A refresh is validated first: consecutive months, every service present every month, finite non-negative costs, unique resources, and a hash that matches the content. On failure, the run is recorded as `failed` with the error and the previous snapshot stays active. Runs interrupted by a crash are marked failed at startup. |
| No mixed reads | Each request resolves its snapshot once (a FastAPI dependency), and every calculation in that request uses it. Snapshots are immutable and cached by `snapshot_id`. The UI loads the active dashboard first and pins every other request to the same snapshot, including detail views, Copilot and lifecycle actions. |
| Refresh semantics | Identical regenerated data gives `unchanged`: no duplicate snapshot, but the run is recorded. A new billing month, or an explicit seed or reference date, gives `created`. Concurrent refreshes get a 409. |
| Freshness | `current` / `stale`. Stale means the snapshot's latest month is older than the calendar month. The header pill shows the status and when the data was generated, and opens snapshot details and refresh history. |
| Date comparison | `/api/dashboard` returns a `comparison` object: both windows are full calendar months (start, end, days, total, daily average) covering the same services. `equivalent_windows` is computed, not asserted. |
| Migrations | Versioned, additive only (`schema_migrations`). The database is backed up with SQLite's online backup API, and the backup integrity-checked, before any pending migration touches existing data. |

## Alternatives considered

- **Keep the dataset in memory and add a refresh endpoint.** That still loses history and can't prove that a failed refresh left the old data intact. Rejected.
- **Store each snapshot as one JSON blob.** Simpler and atomic, but billing and utilization records can't be queried or constrained (`CHECK cost >= 0`, primary keys), and it doesn't match the target data model. Rejected in favour of normalised tables plus a content-hash check on read.
- **Alembic / SQLAlchemy.** A heavier dependency for five tables. The project uses `sqlite3` directly, so a small versioned runner was enough. Revisit if the schema grows or moves to Postgres.
- **Retry on the client when snapshot ids differ.** This was kept only as a defensive check. Pinning by `snapshot_id` prevents the mismatch in the first place.

## Known limitations / next steps

- **The synthetic generator ties the scenario to the latest month.** A month rollover therefore relabels the same synthetic figures; for example, October and November snapshots both show $6,348. The generator was deliberately not changed in this sprint.
- **Lifecycle status is still keyed by recommendation or anomaly id, not by snapshot.** Events now record their `snapshot_id`, but a status set on one snapshot is shown on later snapshots that contain the same id.
- **Events recorded before Sprint 1** have `snapshot_id = NULL`.
- **No UI to browse or compare historical snapshots yet.** They are available through the API with `?snapshot_id=`.
- **Old snapshots are never pruned.** At about 50 rows per snapshot this is negligible for a demo.
- **Cross-process refresh serialisation relies on SQLite's write lock.** The in-process 409 guard only covers a single worker.
