# Decision 002 — Anomaly Detection v2

Status: Implemented (Nov 2026) · Validation: not yet tested with users

## Problem

v1 flagged any service whose spend rose ≥ 20% over the previous month. That has three weaknesses:

- **It is noisy.** A single low month makes the next normal month look like a spike.
- **It is blind to slow growth.** For example, CloudWatch logs creeping up a few percent a month never cross 20%.
- **It gives nothing to investigate.** There was no baseline, window, severity, history or status. The blueprint's acceptance criteria require every anomaly to have a baseline, observation window, deviation, affected service, detection timestamp and investigation status.

## Hypothesis

A robust baseline plus a written explanation of how each anomaly was found will produce fewer false alarms, and will let users decide whether an anomaly matters without leaving the page. Measures to track:

- the share of anomalies resolved as "False positive";
- the time from detection to acknowledgement.

## What was built

| Area | Decision |
| --- | --- |
| Baseline | Median of up to 6 prior months. A single historic outlier doesn't distort it. |
| Confirmation | Robust z-score = (current − median) / (1.4826 × MAD), with the spread floored at 5% of the baseline so a very stable history can't produce enormous z-scores. |
| Types | **Spike:** ≥ 20% above the baseline *and* z ≥ 3. **Gradual growth:** 3 consecutive monthly increases, each below 20%, totalling ≥ 15%. **New service:** spend with no baseline. |
| Severity | Spikes are Critical at ≥ 60%, High at ≥ 30% and Medium at ≥ 20% deviation from the baseline. New services are Medium; gradual growth is Low. These are example thresholds, published at `GET /api/anomalies/config`. |
| History | Walk-forward detection: each month is evaluated only with data that existed at the time, so past results never change when new months arrive. A test enforces this. |
| Lifecycle | open → acknowledged → investigating → resolved, with reopen. Resolving requires a resolution: expected change, root cause fixed, false positive, or other plus a note. Every action is recorded in the `anomaly_events` log. |
| Investigation | Monthly timeline against the baseline, resource attribution, investigation areas per service, related recommendations and a next step. |
| Honesty | Attribution shows how much spend the inventory actually explains: 11.7% for EC2. The remainder is labelled "Not attributed" rather than guessed. |
| Dashboard | Unresolved anomalies are marked on the spend trend chart. |
| Copilot | Anomaly answers include type, severity and baseline, and state that unusual spend is not proof of cause. |

The demo scenario now also includes steady CloudWatch log-ingestion growth (+7% a month for 4 months) so that gradual growth is visible. This raised the current month's total from $6,255 to $6,348.

## Alternatives considered

- **Keep month-over-month only.** It's what v1 does, and it's noisy and blind to slow growth. Rejected.
- **Mean and standard deviation.** One historic spike inflates both and hides the next one. Rejected in favour of median and MAD.
- **ML or seasonal models (Prophet, isolation forest).** Seven months of data is too short for seasonality, and there are no labelled outcomes to evaluate against. Deferred: resolutions recorded as "False positive" become the labels for comparing a future model against this baseline.
- **Count every month of an ongoing trend as a new anomaly.** This is what happens today: CloudWatch appears in both October and November. Keeping each month separate preserves an honest history. Grouping ongoing trends into one incident is a follow-up.

## Known limitations / next steps

- **Monthly granularity only.** Daily spikes and "spend after a resource should have been stopped" need daily, resource-level billing data.
- **Unusual regional spend isn't detected,** because the dataset has no regional cost breakdown.
- **Thresholds aren't user-configurable yet.**
- **Business impact in recommendation scoring** uses current-month spikes and new-service spend. Gradual growth is excluded as too mild.
