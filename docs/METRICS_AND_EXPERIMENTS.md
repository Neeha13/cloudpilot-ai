# Metrics and Experiments

## North-star candidate
Successful cost-investigation sessions: sessions in which a user identifies a cost driver and chooses a justified next step.

This is a candidate metric, not a validated north star.

## Supporting metrics
- Time to identify top cost driver
- Correct identification rate in a guided task
- Recommendation review rate
- Recommendation acceptance / dismissal rate
- Explanation helpfulness rating
- Repeat usage within a test period

## Guardrails
- False-positive recommendation rate
- Percentage of recommendations missing assumptions
- User confidence after reading a recommendation
- Number of users who interpret an advisory suggestion as an automatic action

## Experiment 1 — Does explanation improve recommendation trust?
Hypothesis: Showing evidence, assumptions and risk alongside a recommendation improves users' ability to judge it.
Method: Give participants two versions of the same recommendation card (bare recommendation vs. explanation/evidence). Randomize order.
Measure: Correct understanding, confidence calibration and task time.
Do not equate higher confidence with better trust unless correctness also improves.

## Experiment 2 — Does a prioritized list help?
Hypothesis: Ranking by estimated savings and risk helps users choose an investigation task.
Method: Compare an unranked list with a ranked list.
Measure: Time to choose, quality of chosen action and user rationale.

## Experiment 3 — Copilot vs. filters
Hypothesis: Natural-language questions may help users find cost drivers faster than navigating charts alone.
Method: Ask participants to answer the same questions using dashboard-only and dashboard-plus-copilot flows.
Measure: Accuracy, time, unsupported answer rate and perceived effort.
