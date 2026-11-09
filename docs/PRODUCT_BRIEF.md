# Product Brief — CloudPilot AI

## Vision
Help small engineering teams understand cloud spending and confidently decide which optimization opportunities to investigate first.

## Initial target segment
Small and mid-sized engineering teams using AWS without a dedicated FinOps function. This is an initial hypothesis to validate, not a proven market finding.

## Problem hypothesis
Engineering leads and cloud engineers may see a cloud bill but still spend time connecting cost changes to services/resources, assessing whether a resource is genuinely wasteful, and prioritizing safe actions.

## Jobs to be done
When cloud spending rises or a budget is at risk, help me identify the main cost drivers and investigate safe optimization opportunities so I can make informed decisions without manually stitching together multiple reports.

## MVP
1. Spend overview and trend
2. Service-level cost breakdown
3. Cost anomaly flags
4. Explainable resource recommendations with estimated savings
5. Copilot Q&A grounded in dashboard data
6. Feedback capture on recommendations

## Non-goals
- Automatically changing cloud resources
- Multi-cloud support in the first MVP
- Enterprise identity, billing ingestion and role-based access
- Guaranteed savings claims
- Full AWS Cost and Usage Report ingestion

## Product principles
- Explain every recommendation
- Show assumptions behind savings estimates
- Never take an infrastructure action without explicit authorization
- Prefer safe investigation over automated remediation
- Make synthetic/demo data clearly identifiable

## Validation plan
Interview 5–8 cloud engineers, startup CTOs or engineering managers. Ask about their last cloud-bill investigation, tools used, time spent, confidence in recommendations, and what they did next. Avoid leading questions such as "Would you use an AI cost tool?"
