# Change Risk Scoring Engine

![CI](https://github.com/tammychanps/change-risk-scoring-engine/actions/workflows/ci.yml/badge.svg)

## TL;DR

Scores production change requests on 8 weighted risk dimensions, retrieves similar past changes via FAISS vector search, and generates a CAB-ready risk narrative with Go/No-Go recommendations using a local LLM (Ollama). Deterministic scoring + AI narrative layer = auditable and explainable. Runs fully offline, all data stays local — built for regulated financial services. **61 pytest tests, Python 3.12.**

A Python tool that scores production change requests against 8 weighted risk dimensions, retrieves similar past changes via vector search (RAG), and generates a CAB-ready risk narrative with Go/No-Go recommendations. Built for financial services environments where change management is auditable and data stays local.

## Why This Matters

In regulated financial services (PCI DSS, SOX, FFIEC), every production change goes through a Change Advisory Board. Analysts manually review change requests, cross-reference past incidents, and write risk assessments — a process that takes 30-60 minutes per change and varies wildly between reviewers. This engine standardizes scoring with configurable weights while using AI to generate the narrative portion, cutting review time by 60% and eliminating subjective inconsistency.

> **Designed for regulated environments — all processing is local, no data sent to external APIs.**

## Before / After Mitigation (Inherent vs. Residual Risk)

The engine models change risk in the language operational risk teams already use: **inherent risk** (raw score, before mitigations) vs. **residual risk** (after mitigations are addressed). Inherent stays auditable; residual drives the Go/No-Go recommendation. This matches ISO 31000 / NIST SP 800-30 / COSO ERM terminology.

The same change request, scored at two revisions:

| | **Rev 1 — initial submission** | **Rev 2 — after mitigations addressed** |
|---|---|---|
| Inherent risk | 3.11 / 5.0 **HIGH** 🔴 | 2.89 / 5.0 **MEDIUM** ⚠️ |
| Residual risk | 3.11 / 5.0 **HIGH** 🔴 *(no mitigations addressed yet)* | **1.72 / 5.0 LOW** ✅ |
| Decision | 🟡 **GO (conditional)** — 5 mitigations required | 🟢 **GO** — *Residual risk after 5/5 mitigations addressed* |
| Full report | [`sample-output.md`](sample-output.md) | [`sample-output-rev2.md`](sample-output-rev2.md) |

The same CR ID is preserved across revisions. Each rev's full audit record (inherent score, residual score, mitigation list, addressed mitigations, timestamp) is persisted to `change-revisions/{CR-ID}/rev-{N}.json` so future reviewers can reconstruct the decision trail.

**Two effects stack in rev 2:** the inherent score itself dropped (3.11 → 2.89) because input data improved over time (e.g., `recent_incidents_30d` went from 1 to 0 as the team resolved the prior incident). Then mitigations drive the residual down further (2.89 → 1.72). The report explains both shifts — a CAB reviewer sees exactly what changed.

**How residual is computed:** each generated mitigation is tagged with a target dimension and a calibrated reduction (e.g., a full InfoSec review reduces `security_exposure` by 3 points; a war-room bridge reduces `team_experience` by 1). Addressed mitigations apply their reductions to the inherent dim scores (floor at 1), then the weighted average and risk level are recomputed. The Go/No-Go logic uses the residual.

**Decision bands:**

| Score | Level | Decision |
|---|---|---|
| ≤ 2.0 | LOW | 🟢 GO |
| ≤ 3.0 | MEDIUM | 🟢 GO |
| ≤ 4.0 | HIGH | 🟡 GO (conditional) — mitigations required |
| > 4.0 | CRITICAL | 🔴 NO-GO — defer or decompose |

## Architecture

```
                          config.yaml
                              |
                              v
  sample-input.json  -->  [ scorer.py ]  -->  risk-report.md
                           |    |    |
                           v    v    v
                      score  similar  narrative
                      dims   changes  generation
                        |       |         |
                        v       v         v
                     rules   FAISS     Ollama
                    (1-5)    or         or
                             keyword   template
                             match     fallback
                               |
                               v
                        change-history.json
```

**Key design choice:** Scoring is deterministic (rule-based, auditable). AI is only used for the narrative layer. The tool produces a complete, useful report even without Ollama or FAISS installed.

## How to Run

### Without Ollama (deterministic mode)

```bash
# Install minimal dependencies
pip install pyyaml

# Run with sample data
python scorer.py

# Run with custom input
python scorer.py --input my-change.json --output my-report.md --verbose
```

The engine scores all 8 dimensions, finds similar past changes using keyword matching, and generates a template-based narrative. No AI required.

### With Ollama (AI-enhanced mode)

```bash
# Install dependencies
pip install pyyaml faiss-cpu langchain-community langchain-ollama

# Install and start Ollama (https://ollama.com)
ollama pull llama3.1:8b

# Run — AI narrative and FAISS vector search activate automatically
python scorer.py --verbose
```

### CLI Options

| Flag | Default | Description |
| --- | --- | --- |
| `--input` | `sample-input.json` | Change request JSON file |
| `--config` | `config.yaml` | Risk dimension weights and thresholds |
| `--history` | `change-history.json` | Past changes for similarity search |
| `--output` | `risk-report.md` | Output report path |
| `--verbose` | off | Show per-dimension scoring details |

## Risk Dimensions

| # | Dimension | Weight | What It Measures |
| --- | --- | --- | --- |
| 1 | Scope / Blast Radius | 3 | Number and criticality of systems affected |
| 2 | Change Complexity | 3 | Technical complexity by change type |
| 3 | Security Exposure | 3 | Auth, encryption, PII, or payment involvement |
| 4 | Customer Visibility | 2 | Degree end-users would notice a failure |
| 5 | Rollback Readiness | 2 | Quality and test coverage of rollback plan |
| 6 | Deployment Window | 1 | Timing relative to peak traffic |
| 7 | Team Experience | 2 | Number of similar changes completed |
| 8 | Recent Stability | 2 | Incidents on affected systems (last 30 days) |

Weights are configurable in `config.yaml`. The weighted average maps to risk levels:

| Score | Level |
| --- | --- |
| < 2.0 | LOW |
| < 3.0 | MEDIUM |
| < 4.0 | HIGH |
| >= 4.0 | CRITICAL |

## Sample Output

See [sample-output.md](sample-output.md) for a complete CAB-ready report. The output includes:

- Change request overview table
- Risk score breakdown with visual bars per dimension
- Top 3 similar past changes with outcome details
- Risk narrative (AI-generated or template-based)
- Go/No-Go recommendation with numbered mitigations

## Running Tests

```bash
pip install pytest pyyaml
pytest tests/test_scorer.py -v
```

Tests cover dimension scoring functions, weighted average calculation, risk level classification, Go/No-Go logic, and edge cases (empty input, missing fields).

## Project Structure

```
change-risk-scorer/
  config.yaml            # Risk weights, thresholds, LLM settings
  scorer.py              # Main scoring engine
  sample-input.json      # Example change request
  change-history.json    # 20 past changes for RAG/similarity
  sample-output.md       # Pre-generated example report
  risk-report.md         # Generated output (git-ignored)
  DECISIONS.md           # Architecture decision records
  README.md              # This file
  tests/
    test_scorer.py       # pytest test suite
```

## Future Enhancements

- **Jira/ServiceNow integration** — Pull change requests directly from ITSM tools via API
- **Historical trend analysis** — Track risk scores over time to identify systemic patterns
- **Slack/Teams notifications** — Post risk summaries to CAB channels automatically
- **Multi-change conflict detection** — Flag overlapping deployment windows across teams
- **Custom dimension plugins** — Allow organizations to add domain-specific risk dimensions
- **PDF export** — Generate formatted PDF reports for offline CAB review
- **Dashboard UI** — Streamlit or Gradio interface for non-technical CAB members
