# Decision 001 — Recommendation Intelligence v2

Status: Implemented (Nov 2026) · Validation: not yet tested with users

## Problem

v1 recommendations were rule-generated alerts: a title, a savings figure and a risk label. A user could not tell why a recommendation existed, how strong the evidence was, how the saving was calculated, or what to check before acting. Decisions were a single accept/dismiss click that recorded no reason. Each API also built its own copy of the synthetic data, so screens could in principle disagree.

## Hypothesis

If every recommendation shows its evidence, its calculation, its confidence and its risk, and lets the user record a reasoned decision, then users will:

1. reach a justified decision faster than with v1 cards, and
2. dismiss fewer recommendations as "incorrect", because weak ones are flagged as low-confidence up front.

How to test this: run a usability test with 5–8 cloud or DevOps engineers on the tasks in `USER_RESEARCH.md`. Measure time to decision, decision accuracy, and the distribution of dismissal reasons.

## What was built

| Area | Decision |
| --- | --- |
| One dataset snapshot | `app/dataset.py` builds the data once per process, with a content-hashed `dataset_id`. Every API and every copilot answer references that ID. The month arithmetic is now calendar-correct (v1 could skip a month). |
| Evidence | Each rule emits evidence rows (label, value, source). A metric that was not collected is shown as **Not collected**, never imputed. |
| Savings | Deterministic: `monthly_cost × reduction_rate`, with the formula, method and assumptions returned in the response. Always labelled `kind: "estimate"`. |
| Confidence | Mean of 4 factors: completeness, freshness, observation window and signal strength. **It is capped below High when any required evidence is missing.** |
| Risk | A rule baseline "risk safety" score, lowered for production workloads and missing safeguards (for example, no snapshot). Each risk level has a written explanation. |
| Priority | `0.35·S + 0.25·C + 0.20·B + 0.10·E + 0.10·R`, with every factor normalised to 0–100. Published at `GET /api/recommendations/model`. |
| Lifecycle | `open → investigating → planned → implemented`, plus `snoozed`, `dismissed` and `reopen`. Invalid transitions return 409. Dismissing requires a reason, and "Other" also requires a note. |
| Audit log | Append-only `recommendation_events` table, storing the ruleset version, dataset ID and the estimate at decision time. |
| Analytics | `GET /api/recommendations/analytics` reports decision coverage, acceptance rate, dismissal reasons, and savings by stage. All of it is computed only from recorded decisions. |
| Copilot | Returns structured cards and sources built from the engine. The optional LLM only writes the prose; it never produces figures. |

## Alternatives considered

- **Rank by savings alone (v1).** Simple, but it puts risky, low-confidence changes first. Rejected.
- **Normalise savings relative to the largest recommendation.** Scores would shift whenever the set changes, so the same resource could move rank without any change to it. Rejected in favour of a fixed log scale capped at $500/month.
- **An ML model for confidence.** There are no labelled outcomes yet. Rejected until the decision log has enough data to evaluate one against this baseline.
- **Let the LLM write the explanations and the numbers.** It risks invented savings. Rejected: the deterministic engine owns every number.

## Known limitations / next steps

- The weights and thresholds are a hypothesis. Validate them against user decisions, starting with the dismissal reasons per rule.
- "Implemented" means the user *reported* the change. Realized savings need before/after billing comparison, which is the Savings Tracker work.
- Business impact currently means "addresses an active anomaly, and the saving's share of the service's spend". It does not yet use service criticality from users.
- The reduction rates (35%, 25%, 12%) are planning assumptions, not pricing data.
