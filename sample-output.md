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

The proposed change, Migrate Payment Gateway to AWS EKS (CR-2026-0042), carries a high overall risk score of 3.11/5.0 due to several factors. The primary concerns revolve around the migration's complexity and potential security exposure.

One significant risk is the change's scope and blast radius, rated at 3/5. As this change affects multiple systems (payment-gateway, transaction-service, fraud-detection), a failure could have far-reaching consequences, impacting customer transactions and potentially leading to financial losses. Additionally, the migration involves moving payment processing from EC2 to EKS, which introduces new complexities related to container orchestration and auto-scaling.

The security exposure is another critical concern, with a rating of 4/5. The change's potential impact on the payment gateway's security posture is substantial, given its sensitive nature. A successful rollback would require reverting DNS settings back to previous EC2 instances within a tight window (estimated 15 minutes), which could be challenging and may not be feasible in all scenarios. Furthermore, the team's experience with EKS and container orchestration is rated at 3/5, indicating some uncertainty about their ability to execute this change successfully.


## Go / No-Go Recommendation

> 🟡 **GO (CONDITIONAL)** — High risk (3.11 / 5.0) but manageable. Proceed only with all mitigations implemented and CAB approval.

*Decision bands: GO (≤ 3.0) · GO conditional (3.0 – 4.0) · NO-GO (> 4.0)*


## Required Mitigations

1. Conduct a dry-run in staging that mirrors the exact production sequence. Document each step with expected vs. actual outcomes. *(−2 to Change Complexity)*
2. Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, API key rotation, and encryption-at-rest settings before cutover. *(−3 to Security Exposure)*
3. Prepare customer communication templates (status page, in-app banner) in case of degraded service. Pre-brief the support team. *(−2 to Customer Visibility)*
4. Establish a dedicated war room (bridge call) for the duration of the change window with representatives from engineering, SRE, and on-call support. *(−1 to Team Experience)*
5. Enable enhanced monitoring and alerting 30 minutes before the change window. Set up real-time dashboards for all affected systems. *(−1 to Recent Stability)*


## Risk Assessment

| Score | Level | Recommendation | Where it sits |
| --- | --- | --- | --- |
| **3.11 / 5.0** | **HIGH** 🔴 | GO (conditional) | `LOW (≤2.0) │ MED (≤3.0) │ HIGH (≤4.0)▲ │ CRIT (>4.0)` |


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
| **Total** |  | **18** | **56** |  |
| **Risk Score** |  |  | **56 ÷ 18 = 3.11** |  |


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