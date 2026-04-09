#!/usr/bin/env python3
"""
Change Risk Scoring Engine

Scores production change requests against 8 risk dimensions, retrieves
similar past changes via RAG, and generates a CAB-ready risk narrative.

Works fully without Ollama — uses template-based fallback for narratives
and keyword-based matching when FAISS is unavailable.

Usage:
    python scorer.py                          # defaults
    python scorer.py --input cr.json          # custom input
    python scorer.py --output report.md       # custom output
    python scorer.py --verbose                # show dimension details
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# ── Allow imports from ../common/ ─────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml
from common import rag as rag_module
from common import llm as llm_module
from common import report as rpt

# ── Defaults ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_CONFIG = SCRIPT_DIR / "config.yaml"
DEFAULT_INPUT = SCRIPT_DIR / "sample-input.json"
DEFAULT_HISTORY = SCRIPT_DIR / "change-history.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "risk-report.md"


# =====================================================================
#  Dimension Scoring Functions  (each returns 1–5)
# =====================================================================

def score_scope_impact(cr: dict) -> int:
    """Score based on number of systems affected."""
    n = len(cr.get("systems_affected", []))
    if n <= 1:
        return 1
    if n == 2:
        return 2
    if n == 3:
        return 3
    if n <= 5:
        return 4
    return 5


def score_change_complexity(cr: dict) -> int:
    """Score based on change type."""
    complexity_map = {
        "tooling": 1,
        "compliance": 2,
        "application": 3,
        "security": 3,
        "infrastructure": 4,
        "database": 4,
    }
    return complexity_map.get(cr.get("change_type", "").lower(), 3)


def score_security_exposure(cr: dict) -> int:
    """Score based on security impact flag and affected systems."""
    base = 1
    if cr.get("security_impact", False):
        base = 4
    # Bump if payment or auth systems are touched
    sensitive = {"payment-gateway", "auth-service", "identity-service",
                 "fraud-detection", "customer-data-lake"}
    affected = set(cr.get("systems_affected", []))
    overlap = len(affected & sensitive)
    if overlap >= 2:
        base = min(base + 1, 5)
    return base


def score_customer_visibility(cr: dict) -> int:
    """Score based on whether the change is customer-facing."""
    if not cr.get("customer_facing", False):
        return 1
    # Customer-facing + payment or mobile = higher
    affected = set(cr.get("systems_affected", []))
    if affected & {"payment-gateway", "mobile-app", "web-portal"}:
        return 4
    return 3


def score_rollback_readiness(cr: dict) -> int:
    """Lower score (better) if rollback plan exists and is tested."""
    has_plan = bool(cr.get("rollback_plan", "").strip())
    tested = cr.get("rollback_tested", False)
    if has_plan and tested:
        return 1
    if has_plan and not tested:
        return 3
    if not has_plan:
        return 5
    return 3


def score_deployment_window(cr: dict) -> int:
    """Score based on deployment window timing."""
    window = cr.get("deployment_window", "").lower()
    # Weekend off-hours = best
    if any(day in window for day in ["saturday", "sunday"]):
        if any(t in window for t in ["01:", "02:", "03:", "04:", "05:"]):
            return 1
        return 2
    # Weekday off-hours
    if any(t in window for t in ["01:", "02:", "03:", "04:", "05:", "22:", "23:", "00:"]):
        return 2
    # Weekday business hours = worst
    return 4


def score_team_experience(cr: dict) -> int:
    """Score inversely proportional to similar-change experience."""
    exp = cr.get("team_experience_similar", 0)
    if exp >= 10:
        return 1
    if exp >= 5:
        return 2
    if exp >= 3:
        return 3
    if exp >= 1:
        return 4
    return 5


def score_recent_stability(cr: dict) -> int:
    """Score based on recent incidents on affected systems."""
    incidents = cr.get("recent_incidents_30d", 0)
    if incidents == 0:
        return 1
    if incidents == 1:
        return 3
    if incidents == 2:
        return 4
    return 5


# Map dimension keys to scoring functions
DIMENSION_SCORERS = {
    "scope_impact": score_scope_impact,
    "change_complexity": score_change_complexity,
    "security_exposure": score_security_exposure,
    "customer_visibility": score_customer_visibility,
    "rollback_readiness": score_rollback_readiness,
    "deployment_window": score_deployment_window,
    "team_experience": score_team_experience,
    "recent_stability": score_recent_stability,
}


# =====================================================================
#  Core Scoring Logic
# =====================================================================

def score_change(cr: dict, config: dict) -> Tuple[Dict[str, dict], float]:
    """
    Score a change request across all dimensions.

    Returns:
        (dimension_results, weighted_average)
        dimension_results: {dim_key: {"label": str, "score": int, "weight": int}}
    """
    dimensions = config.get("dimensions", {})
    results = {}
    weighted_sum = 0.0
    total_weight = 0

    for dim_key, scorer_fn in DIMENSION_SCORERS.items():
        dim_cfg = dimensions.get(dim_key, {})
        weight = dim_cfg.get("weight", 1)
        label = dim_cfg.get("label", dim_key.replace("_", " ").title())
        score = scorer_fn(cr)
        results[dim_key] = {"label": label, "score": score, "weight": weight}
        weighted_sum += score * weight
        total_weight += weight

    weighted_avg = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
    return results, weighted_avg


def classify_risk(score: float, config: dict) -> str:
    """Map a numeric score to a risk level using config thresholds."""
    thresholds = config.get("thresholds", {"LOW": 2.0, "MEDIUM": 3.0, "HIGH": 4.0})
    return rpt.score_to_level(score, thresholds)


# =====================================================================
#  Similar Change Retrieval (RAG with keyword fallback)
# =====================================================================

def _keyword_similarity(cr: dict, past: dict) -> float:
    """Simple keyword overlap score between a CR and a past change."""
    cr_words = set()
    cr_words.update(cr.get("title", "").lower().split())
    cr_words.update(s.lower() for s in cr.get("systems_affected", []))
    cr_words.add(cr.get("change_type", "").lower())

    past_words = set()
    past_words.update(past.get("title", "").lower().split())
    past_words.update(s.lower() for s in past.get("systems_affected", []))
    past_words.add(past.get("change_type", "").lower())

    # Remove common stop words
    stop = {"to", "the", "a", "an", "from", "for", "and", "of", "in", "on", "with", "new"}
    cr_words -= stop
    past_words -= stop

    if not cr_words or not past_words:
        return 0.0
    overlap = cr_words & past_words
    return len(overlap) / max(len(cr_words), len(past_words))


def find_similar_changes(cr: dict, history_path: str, config: dict, verbose: bool = False) -> List[dict]:
    """
    Find similar past changes using RAG (FAISS) or keyword fallback.

    Returns top-N past changes sorted by relevance.
    """
    top_n = config.get("report", {}).get("similar_changes_count", 3)

    # Load history
    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    # Attempt RAG retrieval
    query = f"{cr.get('title', '')} {cr.get('change_type', '')} {' '.join(cr.get('systems_affected', []))}"
    docs = rag_module.load_documents_from_json(history_path, text_field="title")
    retriever = rag_module.create_retriever(docs, k=top_n)

    if retriever is not None:
        try:
            results = retriever.invoke(query)
            # Match back to full records
            matched_ids = set()
            similar = []
            for doc in results:
                meta = doc.metadata if hasattr(doc, "metadata") else {}
                # Try to find matching record by title
                for rec in history:
                    if rec["id"] not in matched_ids and rec["title"] in doc.page_content:
                        similar.append(rec)
                        matched_ids.add(rec["id"])
                        break
            if similar:
                if verbose:
                    print(f"  RAG returned {len(similar)} similar changes")
                return similar[:top_n]
        except Exception as e:
            if verbose:
                print(f"  RAG retrieval failed, using keyword fallback: {e}")

    # Keyword fallback
    if verbose:
        print("  Using keyword-based similarity (FAISS/Ollama not available)")
    scored = []
    for past in history:
        sim = _keyword_similarity(cr, past)
        scored.append((sim, past))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_n]]


# =====================================================================
#  Narrative Generation (LLM with template fallback)
# =====================================================================

def _build_template_narrative(cr: dict, dim_results: dict, weighted_avg: float,
                               risk_level: str, similar: List[dict]) -> str:
    """Generate a deterministic template-based narrative when LLM is unavailable."""
    systems = ", ".join(cr.get("systems_affected", ["N/A"]))
    n_systems = len(cr.get("systems_affected", []))
    window = cr.get("deployment_window", "not specified")

    # Identify top risk drivers (score >= 4)
    drivers = []
    for dim_key, info in dim_results.items():
        if info["score"] >= 4:
            drivers.append(info["label"].lower())

    driver_text = ""
    if drivers:
        driver_text = f"Primary risk drivers: {', '.join(drivers)}. "
    else:
        driver_text = "No single dimension scores critically high, but the cumulative profile warrants attention. "

    # Past change context
    past_text = ""
    failures = [s for s in similar if s.get("outcome") in ("rollback", "incident")]
    successes = [s for s in similar if s.get("outcome") == "success"]
    if failures:
        past_text += (
            f"Historical data shows {len(failures)} of {len(similar)} similar changes "
            f"experienced issues ({', '.join(f.get('outcome', '') for f in failures)}). "
        )
        for f in failures:
            past_text += f'Notably, "{f["title"]}" ({f["date"]}) resulted in {f["outcome"]}: {f.get("outcome_notes", "N/A")} '
    if successes:
        past_text += (
            f"{len(successes)} similar change(s) completed successfully, "
            f"suggesting the team can execute this type of work when properly prepared. "
        )

    # Rollback assessment
    rb = cr.get("rollback_plan", "")
    rb_tested = cr.get("rollback_tested", False)
    rb_text = ""
    if rb and rb_tested:
        rb_text = "The rollback plan has been documented and tested in staging, which is a positive indicator. "
    elif rb:
        rb_text = "A rollback plan exists but has NOT been tested. Testing prior to the change window is strongly recommended. "
    else:
        rb_text = "No rollback plan has been documented. This is a significant gap that must be addressed before approval. "

    # Window assessment
    window_text = ""
    wl = window.lower()
    if "saturday" in wl or "sunday" in wl:
        window_text = f"The deployment window ({window}) is during off-peak hours, reducing customer impact potential. "
    else:
        window_text = f"The deployment window ({window}) overlaps with business hours, increasing the risk of customer impact. "

    narrative = (
        f"This change request ({cr.get('id', 'N/A')}) proposes to {cr.get('title', 'N/A').lower()}, "
        f"affecting {n_systems} system(s): {systems}. "
        f"The overall risk assessment is {weighted_avg}/5.0 ({risk_level}).\n\n"
        f"{driver_text}"
        f"{window_text}"
        f"{rb_text}\n\n"
        f"**Historical Context:** {past_text}\n\n"
        f"Given the {risk_level.lower()} risk classification, "
    )

    if risk_level == "LOW":
        narrative += "standard change procedures apply. No additional mitigations required beyond the documented plan."
    elif risk_level == "MEDIUM":
        narrative += "enhanced monitoring during and after deployment is recommended. Ensure the on-call team is briefed."
    elif risk_level == "HIGH":
        narrative += (
            "this change requires explicit CAB approval with documented mitigations for each high-scoring dimension. "
            "A war room should be established for the duration of the change window."
        )
    else:  # CRITICAL
        narrative += (
            "this change should be deferred unless business-critical. If proceeding, require VP-level sign-off, "
            "dedicated war room, and pre-staged rollback execution. Consider breaking into smaller, lower-risk changes."
        )

    return narrative


def generate_narrative(cr: dict, dim_results: dict, weighted_avg: float,
                       risk_level: str, similar: List[dict], config: dict) -> str:
    """Generate risk narrative using LLM or template fallback."""
    # Always build template fallback first
    fallback = _build_template_narrative(cr, dim_results, weighted_avg, risk_level, similar)

    if not config.get("report", {}).get("include_narrative", True):
        return fallback

    # Build LLM prompt
    dim_summary = "\n".join(
        f"  - {info['label']}: {info['score']}/5 (weight {info['weight']})"
        for info in dim_results.values()
    )
    similar_summary = "\n".join(
        f"  - {s['title']} ({s['date']}): {s['outcome']} — {s.get('outcome_notes', 'N/A')}"
        for s in similar
    )

    prompt = f"""You are a Change Advisory Board (CAB) analyst at a financial services company.
Write a professional risk narrative for the following change request.
Be specific, reference the data provided, and write in a formal but readable tone.
Keep it to 2-3 paragraphs.

CHANGE REQUEST:
  ID: {cr.get('id')}
  Title: {cr.get('title')}
  Description: {cr.get('description')}
  Type: {cr.get('change_type')}
  Systems: {', '.join(cr.get('systems_affected', []))}
  Window: {cr.get('deployment_window')}
  Rollback: {cr.get('rollback_plan')}

RISK SCORES (1-5, higher = riskier):
{dim_summary}
  Overall: {weighted_avg}/5.0 ({risk_level})

SIMILAR PAST CHANGES:
{similar_summary}

Write the risk narrative now:"""

    return llm_module.generate(prompt, fallback=fallback)


# =====================================================================
#  Mitigation Recommendations
# =====================================================================

def generate_mitigations(cr: dict, dim_results: dict, risk_level: str) -> List[str]:
    """Generate numbered mitigation recommendations based on high-scoring dimensions."""
    mitigations = []

    # Always recommend based on high-scoring dimensions
    for dim_key, info in dim_results.items():
        if info["score"] >= 4:
            if dim_key == "scope_impact":
                mitigations.append(
                    "Implement phased rollout — deploy to one system at a time with "
                    "validation gates between each phase."
                )
            elif dim_key == "change_complexity":
                mitigations.append(
                    "Conduct a dry-run in staging that mirrors the exact production sequence. "
                    "Document each step with expected vs. actual outcomes."
                )
            elif dim_key == "security_exposure":
                mitigations.append(
                    "Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, "
                    "API key rotation, and encryption-at-rest settings before cutover."
                )
            elif dim_key == "customer_visibility":
                mitigations.append(
                    "Prepare customer communication templates (status page, in-app banner) "
                    "in case of degraded service. Pre-brief the support team."
                )
            elif dim_key == "rollback_readiness":
                mitigations.append(
                    "Test the rollback procedure end-to-end in staging before the change window. "
                    "Document the exact rollback trigger criteria and decision authority."
                )
            elif dim_key == "deployment_window":
                mitigations.append(
                    "Consider rescheduling to an off-peak window (weekend 02:00-06:00). "
                    "If not possible, ensure real-time traffic monitoring is active."
                )
            elif dim_key == "team_experience":
                mitigations.append(
                    "Assign a subject-matter expert or external consultant to shadow the deployment. "
                    "Review runbook with the full team 24 hours before the window."
                )
            elif dim_key == "recent_stability":
                mitigations.append(
                    "Resolve or document root cause of recent incidents before proceeding. "
                    "Lower the rollback trigger threshold — faster rollback if anomalies appear."
                )

    # General mitigations for HIGH/CRITICAL
    if risk_level in ("HIGH", "CRITICAL"):
        mitigations.append(
            "Establish a dedicated war room (bridge call) for the duration of the change window "
            "with representatives from engineering, SRE, and on-call support."
        )
        mitigations.append(
            "Enable enhanced monitoring and alerting 30 minutes before the change window. "
            "Set up real-time dashboards for all affected systems."
        )

    if not mitigations:
        mitigations.append(
            "Standard change procedures apply. Ensure the on-call team is aware of the deployment window."
        )

    return mitigations


# =====================================================================
#  Go / No-Go Recommendation
# =====================================================================

def go_nogo(risk_level: str, dim_results: dict) -> str:
    """Return a Go/No-Go recommendation with rationale."""
    critical_dims = [info["label"] for info in dim_results.values() if info["score"] == 5]

    if risk_level == "LOW":
        return "**GO** — Low risk. Proceed with standard change procedures."
    elif risk_level == "MEDIUM":
        return "**GO (conditional)** — Proceed with enhanced monitoring and documented mitigations."
    elif risk_level == "HIGH":
        if critical_dims:
            return (
                f"**NO-GO (pending mitigations)** — High risk with critical scores in: "
                f"{', '.join(critical_dims)}. Address mitigations before re-assessment."
            )
        return (
            "**GO (conditional)** — High risk but no critical-scoring dimensions. "
            "Proceed only with all mitigations implemented and CAB approval."
        )
    else:  # CRITICAL
        return (
            "**NO-GO** — Critical risk level. Defer this change or decompose into smaller, "
            "lower-risk changes. Requires VP-level exception approval to proceed."
        )


def decision_key(recommendation: str) -> str:
    """
    Extract the machine-readable decision key from a recommendation string.

    Returns one of: GO, GO_CONDITIONAL, NO_GO
    Used to render the color-coded badge.
    """
    rec_upper = recommendation.upper()
    if "NO-GO" in rec_upper or "NO_GO" in rec_upper:
        return "NO_GO"
    if "CONDITIONAL" in rec_upper:
        return "GO_CONDITIONAL"
    if "GO" in rec_upper:
        return "GO"
    return "GO_CONDITIONAL"


# =====================================================================
#  High Score Justification (deterministic, rule-based)
# =====================================================================

def explain_high_score(dim_key: str, cr: dict, score: int) -> str:
    """
    Return a short, rule-based justification for a dimension score >= 4.

    Justifications are deterministic — they reference the input data
    directly. This keeps the audit trail explainable without depending
    on the LLM (which is reserved for the narrative layer).

    Returns "" for scores < 4 so callers can keep low-risk rows clean.
    """
    if score < 4:
        return ""

    n_systems = len(cr.get("systems_affected", []))
    systems = cr.get("systems_affected", [])
    change_type = cr.get("change_type", "unknown")

    explanations = {
        "scope_impact": (
            f"{n_systems} systems affected — wide blast radius across "
            f"{', '.join(systems[:3])}{'...' if n_systems > 3 else ''}"
        ),
        "change_complexity": (
            f"{change_type.title()} change touching {n_systems} system(s) — "
            f"high coordination and execution complexity"
        ),
        "security_exposure": (
            "Touches authentication, encryption, PII, or payment data "
            "(security_impact=true) — InfoSec review required"
        ),
        "customer_visibility": (
            "Customer-facing systems affected — failure would be visible "
            "to end users immediately"
        ),
        "rollback_readiness": (
            "Rollback plan missing or untested — recovery path unverified "
            "before go-live"
        ),
        "deployment_window": (
            f"Window '{cr.get('deployment_window', 'N/A')}' overlaps peak "
            f"traffic — elevated customer impact risk"
        ),
        "team_experience": (
            f"Team has completed only {cr.get('team_experience_similar', 0)} "
            f"similar change(s) — limited execution muscle memory"
        ),
        "recent_stability": (
            f"{cr.get('recent_incidents_30d', 0)} incidents on affected "
            f"systems in the last 30 days — fragile baseline"
        ),
    }
    return explanations.get(dim_key, f"Score {score}/5 — review required")


# =====================================================================
#  Report Assembly
# =====================================================================

def _build_overview_table(cr: dict) -> str:
    """
    Render a two-column Change Request Overview table.

    Left block holds metadata (who/what); right block holds operational
    details (when/how/where). An empty middle column acts as a visual
    gutter so the two halves read as side-by-side.
    """
    rev = cr.get("revision", 1)
    plan_url = cr.get("implementation_plan_url", "")
    plan_cell = f"[View Runbook]({plan_url})" if plan_url else "N/A"

    left = [
        ("Change ID", f"{cr.get('id', 'N/A')} (rev {rev})"),
        ("Title", cr.get("title", "N/A")),
        ("Type", cr.get("change_type", "N/A")),
        ("Requester", cr.get("requester", "N/A")),
        ("Requesting Team", cr.get("requesting_team", "N/A")),
        ("Implementation Team", cr.get("implementation_team", "N/A")),
    ]
    right = [
        ("Systems Affected", ", ".join(cr.get("systems_affected", ["N/A"]))),
        ("Deployment Window", cr.get("deployment_window", "N/A")),
        ("CAB Date", cr.get("cab_date", "N/A")),
        ("Implementation Plan", plan_cell),
        ("Rollback Plan", cr.get("rollback_plan", "N/A")),
        ("Rollback Tested", "Yes" if cr.get("rollback_tested") else "No"),
    ]

    lines = ["| Field | Value |  | Field | Value |",
             "| --- | --- | --- | --- | --- |"]
    for (lk, lv), (rk, rv) in zip(left, right):
        lines.append(f"| **{lk}** | {lv} |  | **{rk}** | {rv} |")
    return "\n".join(lines)


def build_report(cr: dict, dim_results: dict, weighted_avg: float,
                 risk_level: str, similar: List[dict], narrative: str,
                 mitigations: List[str], config: dict) -> str:
    """Assemble the full Markdown risk report.

    Section order is decision-first:
      1. Change Request Overview
      2. Risk Narrative  (LLM-written)
      3. Go / No-Go Recommendation  (color-coded)
      4. Required Mitigations
      5. Risk Assessment  (score + inline gauge)
      6. Dimension Breakdown  (with Why High justifications)
      7. Similar Past Changes
    """
    parts = []

    # Header
    parts.append(rpt.header(
        config.get("report", {}).get("title", "Change Risk Assessment"),
        config.get("report", {}).get("subtitle", "CAB Review Document"),
    ))

    # 1. Change Request Overview (two-column)
    parts.append(rpt.section("Change Request Overview", _build_overview_table(cr)))

    # 2. Risk Narrative (moved up)
    parts.append(rpt.section("Risk Narrative", narrative))

    # 3. Go / No-Go Recommendation (color-coded callout)
    recommendation = go_nogo(risk_level, dim_results)
    badge = rpt.decision_badge(decision_key(recommendation))
    # Strip the leading bold marker from recommendation since the badge replaces it
    rec_text = recommendation.split("** — ", 1)[-1] if "** — " in recommendation else recommendation
    callout = f"> {badge} — {rec_text}"
    parts.append(rpt.section("Go / No-Go Recommendation", callout))

    # 4. Required Mitigations
    if mitigations:
        mit_text = "\n".join(f"{i+1}. {m}" for i, m in enumerate(mitigations))
        parts.append(rpt.section("Required Mitigations", mit_text))

    # 5. Risk Assessment (score + inline gauge)
    gauge = rpt.score_gauge(weighted_avg, risk_level)
    parts.append(rpt.section("Risk Assessment", gauge))

    # 6. Dimension breakdown with "Why High" justification column
    dim_headers = ["Dimension", "Score (1-5)", "Weight", "Weighted", "Why High"]
    dim_rows = []
    for dim_key, info in dim_results.items():
        weighted_val = info["score"] * info["weight"]
        score_bar = "█" * info["score"] + "░" * (5 - info["score"])
        why = explain_high_score(dim_key, cr, info["score"])
        dim_rows.append([
            info["label"],
            f"{score_bar} {info['score']}",
            str(info["weight"]),
            str(weighted_val),
            why or "—",
        ])
    parts.append(rpt.subsection("Dimension Breakdown", rpt.table(dim_headers, dim_rows)))

    # 7. Similar past changes
    if similar:
        sim_headers = ["Change ID", "Title", "Type", "Risk Score", "Outcome", "Date"]
        sim_rows = []
        for s in similar:
            outcome_str = s.get("outcome", "N/A")
            if outcome_str == "success":
                outcome_str = "Success"
            elif outcome_str == "rollback":
                outcome_str = "Rollback"
            elif outcome_str == "incident":
                outcome_str = "Incident"
            sim_rows.append([
                s.get("id", "N/A"),
                s.get("title", "N/A"),
                s.get("change_type", "N/A"),
                str(s.get("risk_score", "N/A")),
                outcome_str,
                s.get("date", "N/A"),
            ])
        sim_content = rpt.table(sim_headers, sim_rows)
        sim_content += "\n\n**Outcome Details:**\n"
        for s in similar:
            sim_content += f"- **{s.get('id')}**: {s.get('outcome_notes', 'N/A')}\n"
        parts.append(rpt.section("Similar Past Changes (Top 3)", sim_content))

    # Footer
    parts.append("\n---\n")
    parts.append(
        "*This report was generated by the Change Risk Scoring Engine. "
        "All processing is performed locally — no data is sent to external APIs. "
        "Designed for regulated environments (PCI DSS, SOX, FFIEC).*"
    )

    return "\n".join(parts)


# =====================================================================
#  Main
# =====================================================================

def load_config(path: str) -> dict:
    """Load YAML configuration file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_input(path: str) -> dict:
    """Load change request JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Change Risk Scoring Engine — score production changes for CAB review"
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help="Path to change request JSON file")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="Path to config YAML file")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY),
                        help="Path to change history JSON file")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Output path for risk report (.md)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed scoring information")
    args = parser.parse_args()

    print("=" * 60)
    print("  Change Risk Scoring Engine")
    print("=" * 60)

    # Load config and input
    config = load_config(args.config)
    cr = load_input(args.input)
    print(f"\n  Change: {cr.get('id')} - {cr.get('title')}")

    # Set Ollama model from config
    ollama_cfg = config.get("ollama", {})
    if ollama_cfg.get("model"):
        llm_module.OLLAMA_MODEL = ollama_cfg["model"]
    if ollama_cfg.get("base_url"):
        llm_module.OLLAMA_BASE_URL = ollama_cfg["base_url"]

    # Score dimensions
    print("\n  Scoring risk dimensions...")
    dim_results, weighted_avg = score_change(cr, config)
    risk_level = classify_risk(weighted_avg, config)

    if args.verbose:
        for dim_key, info in dim_results.items():
            print(f"    {info['label']:25s}  {info['score']}/5  (weight {info['weight']})")
        print(f"    {'':25s}  -----")
        print(f"    {'Weighted Average':25s}  {weighted_avg}/5.0  -> {risk_level}")

    print(f"  Overall: {weighted_avg}/5.0 -> {risk_level}")

    # Find similar past changes
    print("\n  Searching change history...")
    similar = find_similar_changes(cr, args.history, config, verbose=args.verbose)
    print(f"  Found {len(similar)} similar past changes")

    # Generate narrative
    print("\n  Generating risk narrative...")
    narrative = generate_narrative(cr, dim_results, weighted_avg, risk_level, similar, config)

    # Generate mitigations
    mitigations = generate_mitigations(cr, dim_results, risk_level)

    # Build and save report
    print("\n  Assembling report...")
    report = build_report(cr, dim_results, weighted_avg, risk_level,
                          similar, narrative, mitigations, config)
    rpt.save_report(args.output, report)

    print(f"\n  Risk Level: {risk_level} ({weighted_avg}/5.0)")
    print(f"  Report:     {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
