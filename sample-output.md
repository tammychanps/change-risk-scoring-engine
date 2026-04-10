# Change Risk Assessment
## CAB Review Document

> Generated: 2026-04-09
> Tool: AI-powered analysis with local LLM (Ollama) for data security


## Change Request Overview

| Field | Value |  | Field | Value |
| --- | --- | --- | --- | --- |
| **Change ID** | CR-2026-0042 (rev 1) |  | **Systems Affected** | payment-gateway, transaction-service, fraud-detection |
| **Title** | Migrate Payment Gateway to AWS EKS |  | **Deployment Window** | Saturday 02:00-06:00 PST |
| **Type** | infrastructure |  | **CAB Date** | 2026-04-12 |
| **Requester** | Jane Smith |  | **Implementation Plan** | [View Runbook](https://confluence.example.com/display/PAY/CR-2026-0042-runbook) |
| **Requesting Team** | Payments Engineering |  | **Rollback Plan** | Revert DNS to previous EC2 instances, estimated 15 minutes. Tested in staging. |
| **Implementation Team** | Platform SRE |  | **Rollback Tested** | Yes |


## Risk Narrative

**Risk Narrative for Change Request CR-2026-0042**

The proposed change, Migrate Payment Gateway to AWS EKS (CR-2026-0042), poses a moderate to high level of risk due to its complexity and potential impact on system stability. The change involves migrating payment processing from EC2 to EKS, which will enable better auto-scaling and container orchestration. However, the analysis reveals several areas of concern.

The primary risks associated with this change are related to Change Complexity (4/5) and Security Exposure (4/5). The migration to a new infrastructure platform introduces uncertainty around system behavior, particularly during the deployment window on Saturday between 02:00-06:00 PST. Additionally, the increased reliance on AWS EKS may expose the payment gateway to potential security vulnerabilities if not properly configured or monitored. Furthermore, the recent stability of the systems involved (3/5) is a concern, as it indicates that there may be underlying issues that could be exacerbated by this change.

The risk narrative also highlights the importance of effective rollback procedures in case of an issue. Although the team has experience with similar past changes (e.g., Migrate payment gateway from on-prem to AWS EC2), the roll back readiness score is only 1/5, indicating a potential challenge in reverting to the previous state quickly and efficiently. Overall, while the change has been tested in staging, careful planning, monitoring, and execution are essential to mitigate the risks associated with this migration.


## Go / No-Go Recommendation

> 🟡 **GO (CONDITIONAL)** — High risk but manageable. Proceed only with all mitigations implemented and CAB approval.


## Required Mitigations

1. Conduct a dry-run in staging that mirrors the exact production sequence. Document each step with expected vs. actual outcomes. *(−2 to Change Complexity)*
2. Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, API key rotation, and encryption-at-rest settings before cutover. *(−3 to Security Exposure)*
3. Prepare customer communication templates (status page, in-app banner) in case of degraded service. Pre-brief the support team. *(−2 to Customer Visibility)*
4. Establish a dedicated war room (bridge call) for the duration of the change window with representatives from engineering, SRE, and on-call support. *(−1 to Team Experience)*
5. Enable enhanced monitoring and alerting 30 minutes before the change window. Set up real-time dashboards for all affected systems. *(−1 to Recent Stability)*


## Risk Assessment

| Score | Level | Where it sits |
| --- | --- | --- |
| **3.11 / 5.0** | **HIGH** 🔴 | `LOW (≤2.0) │ MED (≤3.0) │ HIGH (≤4.0)▲ │ CRIT (>4.0)` |


### Dimension Breakdown

| Dimension | Score (1-5) | Weight | Weighted | Why High |
| --- | --- | --- | --- | --- |
| Scope / Blast Radius | ███░░ 3 | 3 | 9 | — |
| Change Complexity | ████░ 4 | 3 | 12 | Infrastructure change touching 3 system(s) — high coordination and execution complexity |
| Security Exposure | ████░ 4 | 3 | 12 | Touches authentication, encryption, PII, or payment data (security_impact=true) — InfoSec review required |
| Customer Visibility | ████░ 4 | 2 | 8 | Customer-facing systems affected — failure would be visible to end users immediately |
| Rollback Readiness | █░░░░ 1 | 2 | 2 | — |
| Deployment Window | █░░░░ 1 | 1 | 1 | — |
| Team Experience | ███░░ 3 | 2 | 6 | — |
| Recent Stability | ███░░ 3 | 2 | 6 | — |


## Similar Past Changes (Top 3)

| Change ID | Title | Type | Risk Score | Outcome | Date |
| --- | --- | --- | --- | --- | --- |
| CR-2025-0260 | Migrate payment gateway from on-prem to AWS EC2 | infrastructure | 4.3 | Rollback | 2025-10-08 |
| CR-2025-0275 | Deploy new fraud detection ML model v2.4 | application | 3.2 | Success | 2025-10-20 |
| CR-2025-0301 | Migrate core banking API from REST v2 to v3 | application | 3.8 | Success | 2025-11-15 |

**Outcome Details:**
- **CR-2025-0260**: TLS certificate chain issue caused 502 errors at 03:15. Rolled back to on-prem at 03:42. Root cause: intermediate cert not included in ELB config.
- **CR-2025-0275**: Canary deployment over 4 hours. False positive rate dropped from 2.1% to 1.4%.
- **CR-2025-0301**: Completed within window. Minor latency spike (12ms) during cutover resolved in 5 minutes.



---

*This report was generated by the Change Risk Scoring Engine. All processing is performed locally — no data is sent to external APIs. Designed for regulated environments (PCI DSS, SOX, FFIEC).*