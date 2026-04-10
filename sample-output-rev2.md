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

The proposed change, Migrate Payment Gateway to AWS EKS, poses a moderate level of risk to the organization. The primary concerns revolve around the complexity and potential impact on payment processing systems. With a scope/blast radius score of 3/5, there is a moderate likelihood that the change could affect multiple components within the payment gateway system.

The high security exposure score of 4/5 highlights the importance of ensuring that the migration to EKS does not compromise the security and integrity of sensitive customer data. The recent stability score of 1/5 also raises concerns, as it suggests that the team may be less familiar with the new technology stack, potentially leading to unforeseen issues during deployment.

The risk narrative is further supported by a review of similar past changes. While some have been successful, others have resulted in significant downtime or performance issues. For instance, the migration to AWS EC2 experienced a rollback due to a TLS certificate chain issue, highlighting the potential for unforeseen complications. Conversely, the canary deployment of the new fraud detection ML model v2.4 was successful, but this was a more controlled and gradual rollout.

**Recommendations**

Given the moderate level of risk associated with this change request, it is essential that the CAB continues to monitor its progress closely. The team should remain vigilant in addressing any issues that arise during deployment and be prepared to execute the rollback procedure if necessary. Additionally, the success of this migration will depend on the effectiveness of the enhanced monitoring pre-staged and the war room scheduled for the deployment window.

**Risk Mitigation**

The CAB has already approved several mitigations to address potential risks, including a staging dry-run, InfoSec sign-off, customer comms templates, and an enhanced monitoring plan. These measures should help minimize the likelihood of unforeseen complications during the migration process.


## Go / No-Go Recommendation

> 🟢 **GO** — Low risk. Proceed with standard change procedures.  
*Residual risk after 5/5 mitigations addressed.*


## Required Mitigations

1. ✅ Conduct a dry-run in staging that mirrors the exact production sequence. Document each step with expected vs. actual outcomes. *(−2 to Change Complexity)*
2. ✅ Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, API key rotation, and encryption-at-rest settings before cutover. *(−3 to Security Exposure)*
3. ✅ Prepare customer communication templates (status page, in-app banner) in case of degraded service. Pre-brief the support team. *(−2 to Customer Visibility)*
4. ✅ Establish a dedicated war room (bridge call) for the duration of the change window with representatives from engineering, SRE, and on-call support. *(−1 to Team Experience)*
5. ✅ Enable enhanced monitoring and alerting 30 minutes before the change window. Set up real-time dashboards for all affected systems. *(−1 to Recent Stability)*


## Risk Assessment

**Inherent Risk** (raw score, before mitigations)

| Score | Level | Where it sits |
| --- | --- | --- |
| **2.89 / 5.0** | **MEDIUM** ⚠️ | `LOW (≤2.0) │ MED (≤3.0)▲ │ HIGH (≤4.0) │ CRIT (>4.0)` |

**Residual Risk** (after addressed mitigations — drives the recommendation)

| Score | Level | Where it sits |
| --- | --- | --- |
| **1.72 / 5.0** | **LOW** ✅ | `LOW (≤2.0)▲ │ MED (≤3.0) │ HIGH (≤4.0) │ CRIT (>4.0)` |


### Dimension Breakdown

| Dimension | Inherent | Weight | Weighted | Why High | Residual |
| --- | --- | --- | --- | --- | --- |
| Scope / Blast Radius | ███░░ 3 | 3 | 9 | — | 3 |
| Change Complexity | ████░ 4 | 3 | 12 | Infrastructure change touching 3 system(s) — high coordination and execution complexity | 4 → 2 ✅ |
| Security Exposure | ████░ 4 | 3 | 12 | Touches authentication, encryption, PII, or payment data (security_impact=true) — InfoSec review required | 4 → 1 ✅ |
| Customer Visibility | ████░ 4 | 2 | 8 | Customer-facing systems affected — failure would be visible to end users immediately | 4 → 2 ✅ |
| Rollback Readiness | █░░░░ 1 | 2 | 2 | — | 1 |
| Deployment Window | █░░░░ 1 | 1 | 1 | — | 1 |
| Team Experience | ███░░ 3 | 2 | 6 | — | 3 → 2 ✅ |
| Recent Stability | █░░░░ 1 | 2 | 2 | — | 1 |


## Revision History

| Rev | Timestamp | Inherent | Residual | Decision |
| --- | --- | --- | --- | --- |
| rev 1 | 2026-04-09 21:45:47 | 3.11/5.0 HIGH | 3.11/5.0 HIGH | GO CONDITIONAL |
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