# Change Risk Assessment
## CAB Review Document

> Generated: 2026-04-09
> Tool: AI-powered analysis with local LLM (Ollama) for data security


## Change Request Overview

| Field | Value |  | Field | Value |
| --- | --- | --- | --- | --- |
| **Change ID** | CR-2026-0042 (rev 2) |  | **Systems Affected** | payment-gateway, transaction-service, fraud-detection |
| **Title** | Migrate Payment Gateway to AWS EKS |  | **Deployment Window** | Saturday 02:00-06:00 PST |
| **Type** | infrastructure |  | **CAB Date** | 2026-04-12 |
| **Requester** | Jane Smith |  | **Implementation Plan** | [View Runbook](https://confluence.example.com/display/PAY/CR-2026-0042-runbook-v2) |
| **Requesting Team** | Payments Engineering |  | **Rollback Plan** | Revert DNS to previous EC2 instances, estimated 8 minutes (improved from 15 min after dry-run). Rollback procedure executed successfully twice in staging on 2026-04-10 and 2026-04-11. |
| **Implementation Team** | Platform SRE |  | **Rollback Tested** | Yes |


## Risk Narrative

**Risk Narrative for Change Request CR-2026-0042**

The proposed change, Migrate Payment Gateway to AWS EKS, poses a moderate level of risk to the organization. The change involves migrating payment processing from EC2 to EKS, which introduces new complexities in terms of auto-scaling and container orchestration. According to the provided data, the change complexity is rated 4/5, indicating a higher degree of difficulty.

The potential risks associated with this change include security exposure (rated 4/5) due to the introduction of new infrastructure components, and customer visibility (rated 4/5) as any disruptions during the deployment window may impact customer transactions. Additionally, the recent stability rating is low at 1/5, indicating that the team has not had extensive experience with EKS deployments in the past. The overall risk score of 2.89/5.0 highlights the need for careful planning and execution to mitigate these risks.

Notwithstanding the mitigations incorporated in Revision 2, such as staging dry-run completion, InfoSec sign-off, customer comms templates approval, war room scheduling, and enhanced monitoring pre-staging, there is still a risk of unforeseen issues arising during deployment. The rollback procedure has been successfully executed twice in staging, but this does not guarantee success in the production environment. Therefore, it is essential to closely monitor the change's progress and be prepared to revert to the previous EC2 instances if necessary.


## Go / No-Go Recommendation

> 🟢 **GO** — Low risk (1.72 / 5.0). Proceed with standard change procedures.  
*Residual risk after 5/5 mitigations addressed.*

*Decision bands: GO (≤ 3.0) · GO conditional (3.0 – 4.0) · NO-GO (> 4.0)*


## Required Mitigations

1. ✅ Conduct a dry-run in staging that mirrors the exact production sequence. Document each step with expected vs. actual outcomes. *(−2 to Change Complexity)*
2. ✅ Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, API key rotation, and encryption-at-rest settings before cutover. *(−3 to Security Exposure)*
3. ✅ Prepare customer communication templates (status page, in-app banner) in case of degraded service. Pre-brief the support team. *(−2 to Customer Visibility)*
4. ✅ Establish a dedicated war room (bridge call) for the duration of the change window with representatives from engineering, SRE, and on-call support. *(−1 to Team Experience)*
5. ✅ Enable enhanced monitoring and alerting 30 minutes before the change window. Set up real-time dashboards for all affected systems. *(−1 to Recent Stability)*


## Risk Assessment

**Inherent Risk** (raw score, before mitigations)

| Score | Level | Recommendation | Where it sits |
| --- | --- | --- | --- |
| **2.89 / 5.0** | **MEDIUM** ⚠️ | GO | `LOW (≤2.0) │ MED (≤3.0)▲ │ HIGH (≤4.0) │ CRIT (>4.0)` |

**Residual Risk** (after addressed mitigations — drives the recommendation)

| Score | Level | Recommendation | Where it sits |
| --- | --- | --- | --- |
| **1.72 / 5.0** | **LOW** ✅ | GO | `LOW (≤2.0)▲ │ MED (≤3.0) │ HIGH (≤4.0) │ CRIT (>4.0)` |


### Dimension Breakdown

| Dimension | Inherent | Weight | Weighted (Inherent) | Residual | Weighted (Residual) | Why High |
| --- | --- | --- | --- | --- | --- | --- |
| Scope / Blast Radius | ███░░ 3 | 3 | 9 | 3 | 9 | — |
| Change Complexity | ████░ 4 | 3 | 12 | 4 → 2 ✅ | 6 | Infrastructure change touching 3 system(s) — high coordination and execution complexity |
| Security Exposure | ████░ 4 | 3 | 12 | 4 → 1 ✅ | 3 | Touches authentication, encryption, PII, or payment data (security_impact=true) — InfoSec review required |
| Customer Visibility | ████░ 4 | 2 | 8 | 4 → 2 ✅ | 4 | Customer-facing systems affected — failure would be visible to end users immediately |
| Rollback Readiness | █░░░░ 1 | 2 | 2 | 1 | 2 | — |
| Deployment Window | █░░░░ 1 | 1 | 1 | 1 | 1 | — |
| Team Experience | ███░░ 3 | 2 | 6 | 3 → 2 ✅ | 4 | — |
| Recent Stability | █░░░░ 1 | 2 | 2 | 1 | 2 | — |
| **Total** |  | **18** | **52** |  | **31** |  |
| **Risk Score** |  |  | **52 ÷ 18 = 2.89** |  | **31 ÷ 18 = 1.72** |  |


## Revision History

| Rev | Timestamp | Inherent | Residual | Decision |
| --- | --- | --- | --- | --- |
| rev 1 | 2026-04-09 22:10:00 | 3.11/5.0 HIGH | 3.11/5.0 HIGH | GO CONDITIONAL |
*Inherent risk dropped 0.22 since rev 1 due to updated input data (e.g., resolved incidents, improved rollback, increased team experience). Residual risk reflects both this data improvement and addressed mitigations.*


**Mitigations addressed since rev 1:**

- ✅ 1. Conduct a dry-run in staging that mirrors the exact production sequence. Document each step with expected vs. actual outcomes.
- ✅ 2. Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, API key rotation, and encryption-at-rest settings before cutover.
- ✅ 3. Prepare customer communication templates (status page, in-app banner) in case of degraded service. Pre-brief the support team.
- ✅ 4. Establish a dedicated war room (bridge call) for the duration of the change window with representatives from engineering, SRE, and on-call support.
- ✅ 5. Enable enhanced monitoring and alerting 30 minutes before the change window. Set up real-time dashboards for all affected systems.


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