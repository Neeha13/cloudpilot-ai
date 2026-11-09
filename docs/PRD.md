# Product Requirements Document

## 1. Background
Cloud cost information can be fragmented across billing views, resource inventories and engineering context. CloudPilot AI explores whether a unified, explainable workflow can reduce the effort required to investigate cost drivers.

## 2. Users
- Primary hypothesis: DevOps/cloud engineer at a small or mid-sized AWS-using company
- Secondary: startup CTO or engineering manager
- Later: FinOps analyst

## 3. User stories and acceptance criteria

### Cost overview
As a cloud engineer, I want to see total spend, month-over-month change and service breakdown so I can quickly understand the current cost picture.
- Dashboard shows total spend and previous-period comparison.
- Service breakdown sums to the displayed total.
- Demo dataset is clearly labelled.

### Anomaly investigation
As a cloud engineer, I want unusual spending changes highlighted with context.
- Anomaly includes service, date/period, observed amount and baseline.
- Anomaly explanation states why it was flagged.
- No claim that correlation proves root cause.

### Recommendations
As a cloud engineer, I want prioritized optimization opportunities with evidence and estimated savings.
- Each recommendation has resource, reason, risk, estimated monthly savings and action guidance.
- Estimates include assumptions and are labelled estimates.
- User can accept for review or dismiss; no cloud action is executed.

### Copilot
As a user, I want to ask questions in natural language and receive answers based on the dashboard data.
- Answers use available spend, anomalies and recommendations.
- If the answer cannot be supported by available data, the copilot says so.
- Optional LLM mode must receive only the necessary demo context.

### Feedback
As a product team, we want to learn whether recommendations are useful.
- User can mark recommendation accepted or dismissed.
- Feedback is persisted locally.

## 4. Success metrics (initial hypotheses)
- Recommendation review rate = recommendations opened / recommendations shown
- Acceptance rate = accepted / (accepted + dismissed)
- Investigation task completion = users who correctly identify the top cost driver / users tested
- Time to insight = time from opening dashboard to identifying top cost driver
- Explanation helpfulness = positive feedback / total feedback

Do not claim targets as industry benchmarks. Establish baselines through usability testing.

## 5. Risks
- False positives may reduce trust.
- Savings estimates may be misleading without workload context.
- Cost data may be delayed or incomplete.
- Users may mistake advisory recommendations for safe-to-execute actions.

## 6. Privacy and safety
Use synthetic data in the portfolio MVP. Do not upload customer billing data or secrets. No infrastructure changes are performed.
