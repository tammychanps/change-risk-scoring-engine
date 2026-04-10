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
from typing import Dict, List, Optional, Tuple

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
    """Score based on security impact flag.

    Returns 4 when the change touches authentication, encryption, PII, or
    payment data; 1 otherwise. We deliberately do NOT bump for breadth of
    sensitive-system overlap — that signal is already captured by
    score_scope_impact and score_change_complexity, and double-counting it
    here inflated the residual score and broke the GO-conditional pathway.
    See DECISIONS.md ("Security dimension is binary, not bump-by-breadth").
    """
    if cr.get("security_impact", False):
        return 4
    return 1


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

# =====================================================================
#  Mitigation Templates  (text + target dim + reduction)
# =====================================================================
# Each mitigation maps to a single dimension it addresses. When marked
# as "addressed" in a future revision, that dimension's residual score
# drops by `reduction` points (floor at 1).
#
# Reductions are calibrated per mitigation, not flat. A full InfoSec
# pre-deployment review meaningfully removes more risk than a war-room
# bridge call. Each value is chosen to be individually defensible to a
# CAB reviewer asking "why does this mitigation deserve N points?".

DIMENSION_MITIGATIONS = {
    "scope_impact": {
        "text": ("Implement phased rollout — deploy to one system at a time with "
                 "validation gates between each phase."),
        "target_dim": "scope_impact",
        "reduction": 1,  # phasing helps but blast radius still exists
    },
    "change_complexity": {
        "text": ("Conduct a dry-run in staging that mirrors the exact production sequence. "
                 "Document each step with expected vs. actual outcomes."),
        "target_dim": "change_complexity",
        "reduction": 2,  # rehearsal removes most execution uncertainty
    },
    "security_exposure": {
        "text": ("Engage InfoSec for pre-deployment review. Verify TLS/mTLS configurations, "
                 "API key rotation, and encryption-at-rest settings before cutover."),
        "target_dim": "security_exposure",
        "reduction": 3,  # full controls verification = security risk largely controlled
    },
    "customer_visibility": {
        "text": ("Prepare customer communication templates (status page, in-app banner) "
                 "in case of degraded service. Pre-brief the support team."),
        "target_dim": "customer_visibility",
        "reduction": 2,  # users informed + support ready dampens visibility risk
    },
    "rollback_readiness": {
        "text": ("Test the rollback procedure end-to-end in staging before the change window. "
                 "Document the exact rollback trigger criteria and decision authority."),
        "target_dim": "rollback_readiness",
        "reduction": 2,  # E2E tested rollback removes recovery uncertainty
    },
    "deployment_window": {
        "text": ("Consider rescheduling to an off-peak window (weekend 02:00-06:00). "
                 "If not possible, ensure real-time traffic monitoring is active."),
        "target_dim": "deployment_window",
        "reduction": 2,  # off-peak reschedule directly addresses timing risk
    },
    "team_experience": {
        "text": ("Assign a subject-matter expert or external consultant to shadow the deployment. "
                 "Review runbook with the full team 24 hours before the window."),
        "target_dim": "team_experience",
        "reduction": 1,  # SME shadow helps but doesn't replace muscle memory
    },
    "recent_stability": {
        "text": ("Resolve or document root cause of recent incidents before proceeding. "
                 "Lower the rollback trigger threshold — faster rollback if anomalies appear."),
        "target_dim": "recent_stability",
        "reduction": 2,  # root cause resolved = baseline restored
    },
}

# General mitigations triggered by HIGH/CRITICAL risk levels. These map
# to dims that aren't necessarily high-scoring on their own but benefit
# from the mitigation (war-room reduces team-experience risk; enhanced
# monitoring reduces recent-stability risk).
GENERAL_HIGH_MITIGATIONS = [
    {
        "text": ("Establish a dedicated war room (bridge call) for the duration of the change "
                 "window with representatives from engineering, SRE, and on-call support."),
        "target_dim": "team_experience",
        "reduction": 1,  # additional coverage during execution
    },
    {
        "text": ("Enable enhanced monitoring and alerting 30 minutes before the change window. "
                 "Set up real-time dashboards for all affected systems."),
        "target_dim": "recent_stability",
        "reduction": 1,  # faster detection of anomalies
    },
]

STANDARD_MITIGATION = {
    "text": ("Standard change procedures apply. Ensure the on-call team is aware of the "
             "deployment window."),
    "target_dim": None,
    "reduction": 0,
}


def generate_mitigations(cr: dict, dim_results: dict, risk_level: str) -> List[dict]:
    """Generate numbered mitigation recommendations as tagged dicts.

    Each mitigation is {"text", "target_dim", "reduction"}. The target_dim
    and reduction enable residual-risk computation when the mitigation is
    marked addressed in a later revision.
    """
    mitigations: List[dict] = []

    # Per-dimension mitigations for any dim scoring >= 4
    for dim_key, info in dim_results.items():
        if info["score"] >= 4 and dim_key in DIMENSION_MITIGATIONS:
            mitigations.append(dict(DIMENSION_MITIGATIONS[dim_key]))

    # General HIGH/CRITICAL mitigations (always added at HIGH or above)
    if risk_level in ("HIGH", "CRITICAL"):
        for mit in GENERAL_HIGH_MITIGATIONS:
            mitigations.append(dict(mit))

    if not mitigations:
        mitigations.append(dict(STANDARD_MITIGATION))

    return mitigations


def mitigation_text(mit) -> str:
    """Return the text of a mitigation, accepting either dict or legacy str."""
    if isinstance(mit, dict):
        return mit.get("text", "")
    return str(mit)


def mitigation_texts(mits: List) -> List[str]:
    """Convert a list of mitigation dicts (or strings) to a list of text strings."""
    return [mitigation_text(m) for m in mits]


# =====================================================================
#  Residual Risk  (inherent score adjusted by addressed mitigations)
# =====================================================================

def compute_residual(inherent_dim_results: Dict[str, dict],
                     mitigations: List[dict],
                     addressed_indices: List[int],
                     config: dict) -> Tuple[Dict[str, dict], float, str]:
    """Apply addressed mitigations to inherent scores to produce residual.

    Each addressed mitigation reduces its target dimension's score by its
    `reduction` value (flat -1 by default), with a floor of 1. The weighted
    average and risk level are recomputed from the residual dim scores.

    This implements the inherent vs. residual risk model from ISO 31000 /
    NIST SP 800-30: inherent stays auditable; residual reflects the
    expected post-mitigation state and drives the Go/No-Go recommendation.

    Args:
        inherent_dim_results: dim_results dict from score_change()
        mitigations: list of mitigation dicts (with target_dim, reduction)
        addressed_indices: 1-based mitigation indices marked as addressed
        config: full config dict (for thresholds + weights)

    Returns:
        (residual_dim_results, residual_weighted_avg, residual_level)
    """
    # Deep-copy inherent scores so we don't mutate the input
    residual = {
        k: {"label": v["label"], "score": v["score"], "weight": v["weight"]}
        for k, v in inherent_dim_results.items()
    }

    addressed_set = set(addressed_indices or [])
    for idx, mit in enumerate(mitigations or [], start=1):
        if idx not in addressed_set:
            continue
        target = mit.get("target_dim") if isinstance(mit, dict) else None
        if not target or target not in residual:
            continue
        reduction = mit.get("reduction", 1) if isinstance(mit, dict) else 1
        residual[target]["score"] = max(1, residual[target]["score"] - reduction)

    # Recompute weighted average from residual scores
    weighted_sum = 0.0
    total_weight = 0
    for info in residual.values():
        weighted_sum += info["score"] * info["weight"]
        total_weight += info["weight"]
    residual_avg = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
    residual_level = classify_risk(residual_avg, config)

    return residual, residual_avg, residual_level


# =====================================================================
#  Go / No-Go Recommendation
# =====================================================================

def go_nogo(risk_level: str, dim_results: dict,
            score: Optional[float] = None) -> str:
    """Return a Go/No-Go recommendation with rationale and score.

    Decision bands (simplified scheme):
      LOW    (≤ 2.0)  → GO
      MEDIUM (≤ 3.0)  → GO  (acceptable risk, proceed with awareness)
      HIGH   (≤ 4.0)  → GO (conditional)  (mitigations required before proceed)
      CRITICAL (> 4.0) → NO-GO  (defer or decompose)

    When score is provided it is displayed inline so the reviewer sees
    the number next to the decision without scrolling to the gauge.
    """
    score_str = f" ({score} / 5.0)" if score is not None else ""
    if risk_level in ("LOW", "MEDIUM"):
        return f"**GO** — Low risk{score_str}. Proceed with standard change procedures."
    elif risk_level == "HIGH":
        return (
            f"**GO (conditional)** — High risk{score_str} but manageable. "
            "Proceed only with all mitigations implemented and CAB approval."
        )
    else:  # CRITICAL
        return (
            f"**NO-GO** — Critical risk level{score_str}. Defer this change or decompose "
            "into smaller, lower-risk changes. Requires VP-level exception approval to proceed."
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
#  Revision History (per-change audit trail)
# =====================================================================

def revision_dir(history_root: str, change_id: str) -> Path:
    """Return the per-change folder under the history root."""
    return Path(history_root) / change_id


def load_revision_history(history_root: str, change_id: str) -> List[dict]:
    """
    Load all prior revision records for a change ID, sorted by revision.

    Returns [] if the change has no prior revisions.
    """
    folder = revision_dir(history_root, change_id)
    if not folder.exists():
        return []
    records = []
    for filepath in sorted(folder.glob("rev-*.json")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                records.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    records.sort(key=lambda r: r.get("revision", 0))
    return records


def save_revision_record(history_root: str, change_id: str, record: dict) -> Path:
    """
    Persist a single revision record to {history_root}/{change_id}/rev-{n}.json.

    Creates the folder if needed. Overwrites if the same revision number
    is rerun (idempotent within a revision).
    """
    folder = revision_dir(history_root, change_id)
    folder.mkdir(parents=True, exist_ok=True)
    rev_num = record.get("revision", 1)
    filepath = folder / f"rev-{rev_num}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return filepath


def build_revision_record(cr: dict, weighted_avg: float, risk_level: str,
                          recommendation: str, mitigations: List,
                          residual_score: Optional[float] = None,
                          residual_level: Optional[str] = None) -> dict:
    """Capture the assessment outcome for a single revision.

    Stores both inherent and residual scores so future revisions can
    show the progression. If residual_score / residual_level are not
    provided, residual = inherent (no mitigations addressed yet).

    `mitigations` may be a list of dicts (new format with target_dim) or
    a list of strings (legacy). Both are persisted as text for the audit
    trail; dicts also persist their target_dim and reduction.
    """
    # Normalize mitigations to a list of dicts for the audit record
    mits_for_record = []
    for m in (mitigations or []):
        if isinstance(m, dict):
            mits_for_record.append({
                "text": m.get("text", ""),
                "target_dim": m.get("target_dim"),
                "reduction": m.get("reduction", 1),
            })
        else:
            mits_for_record.append({"text": str(m), "target_dim": None, "reduction": 0})

    return {
        "change_id": cr.get("id"),
        "revision": cr.get("revision", 1),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "inherent_score": weighted_avg,
        "inherent_level": risk_level,
        "residual_score": residual_score if residual_score is not None else weighted_avg,
        "residual_level": residual_level if residual_level is not None else risk_level,
        # Backward-compat: keep score/level fields pointing at residual
        # (the decision-relevant value).
        "score": residual_score if residual_score is not None else weighted_avg,
        "level": residual_level if residual_level is not None else risk_level,
        "recommendation": recommendation,
        "decision": decision_key(recommendation),
        "mitigations": mits_for_record,
        "addressed_mitigations": cr.get("addressed_mitigations", []),
    }


def render_revision_history(history: List[dict], current_rev: int,
                            current_addressed: List[int],
                            current_inherent: Optional[float] = None,
                            current_residual: Optional[float] = None) -> str:
    """Render a markdown section showing prior revisions with inherent +
    residual progression, plus a checklist of which mitigations from the
    most recent prior revision were addressed in this run.

    Each prior-revision row shows BOTH inherent and residual scores so a
    CAB reviewer can see the risk-reduction story across revisions.

    When current_inherent is provided and differs from the prior revision's
    inherent, a delta note explains the shift (e.g., data improved over time
    independent of mitigations).
    """
    prior = [r for r in history if r.get("revision", 0) < current_rev]
    if not prior:
        return ""

    headers = ["Rev", "Timestamp", "Inherent", "Residual", "Decision"]
    rows = []
    for rec in prior:
        # Backward-compat: older records may only have `score` / `level`
        inherent_score = rec.get("inherent_score", rec.get("score", "N/A"))
        inherent_level = rec.get("inherent_level", rec.get("level", "N/A"))
        residual_score = rec.get("residual_score", rec.get("score", "N/A"))
        residual_level = rec.get("residual_level", rec.get("level", "N/A"))
        rows.append([
            f"rev {rec.get('revision')}",
            rec.get("timestamp", "N/A")[:19].replace("T", " "),
            f"{inherent_score}/5.0 {inherent_level}",
            f"{residual_score}/5.0 {residual_level}",
            rec.get("decision", "N/A").replace("_", " "),
        ])
    table_md = rpt.table(headers, rows)

    # Inherent-delta note: explain why current inherent differs from prior
    latest_prior = prior[-1]
    delta_note = ""
    prior_inh = latest_prior.get("inherent_score", latest_prior.get("score"))
    if current_inherent is not None and prior_inh is not None:
        delta = round(current_inherent - prior_inh, 2)
        if delta != 0:
            direction = "dropped" if delta < 0 else "rose"
            delta_note = (
                f"\n*Inherent risk {direction} {abs(delta):.2f} since rev "
                f"{latest_prior['revision']} due to updated input data "
                f"(e.g., resolved incidents, improved rollback, increased team experience). "
                f"Residual risk reflects both this data improvement and addressed mitigations.*\n"
            )

    # Diff against the most recent prior revision
    prior_mits = latest_prior.get("mitigations", [])
    diff_lines = []
    if prior_mits and current_addressed:
        diff_lines.append(f"\n**Mitigations addressed since rev {latest_prior['revision']}:**\n")
        for i, mit in enumerate(prior_mits, start=1):
            mark = "✅" if i in current_addressed else "⬜"
            diff_lines.append(f"- {mark} {i}. {mitigation_text(mit)}")
    elif prior_mits:
        diff_lines.append(
            f"\n*No mitigations from rev {latest_prior['revision']} marked as addressed yet.*"
        )

    return table_md + delta_note + "\n" + "\n".join(diff_lines)


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
                 mitigations: List, config: dict,
                 prior_revisions: Optional[List[dict]] = None,
                 residual_dim_results: Optional[Dict[str, dict]] = None,
                 residual_score: Optional[float] = None,
                 residual_level: Optional[str] = None,
                 prior_mitigations: Optional[List[dict]] = None) -> str:
    """Assemble the full Markdown risk report.

    Section order is decision-first:
      1. Change Request Overview
      2. Risk Narrative  (LLM-written)
      3. Go / No-Go Recommendation  (residual decision, color-coded)
      4. Required Mitigations  (with addressed checkboxes if rev > 1)
      5. Risk Assessment  (inherent + residual gauges)
      6. Dimension Breakdown  (inherent + residual columns + Why High)
      7. Revision History  (only if prior revisions exist)
      8. Similar Past Changes

    Residual params default to inherent values for backward compatibility
    when no mitigations have been addressed (rev 1, no prior history).
    """
    # Default residual to inherent (rev 1 / no addressed mitigations case)
    if residual_dim_results is None:
        residual_dim_results = dim_results
    if residual_score is None:
        residual_score = weighted_avg
    if residual_level is None:
        residual_level = risk_level

    parts = []

    # Header
    parts.append(rpt.header(
        config.get("report", {}).get("title", "Change Risk Assessment"),
        config.get("report", {}).get("subtitle", "CAB Review Document"),
    ))

    # 1. Change Request Overview (two-column)
    parts.append(rpt.section("Change Request Overview", _build_overview_table(cr)))

    # 2. Risk Narrative (LLM-written)
    parts.append(rpt.section("Risk Narrative", narrative))

    # 3. Go / No-Go Recommendation — uses RESIDUAL decision (color-coded)
    # Show residual score if mitigations were addressed, else inherent score
    display_score = residual_score if residual_score != weighted_avg else weighted_avg
    recommendation = go_nogo(residual_level, residual_dim_results, score=display_score)
    addressed = cr.get("addressed_mitigations", [])
    # Use the prior revision's mitigation list for the "X of Y addressed"
    # count when this revision is tracking a prior commitment.
    tracked_mits = prior_mitigations if prior_mitigations else mitigations
    total_tracked = len(tracked_mits or [])
    addressed_count = len([i for i in addressed if 1 <= i <= total_tracked])
    if addressed_count > 0 and total_tracked > 0:
        recommendation = (
            f"{recommendation.rstrip()}  \n"
            f"*Residual risk after {addressed_count}/{total_tracked} mitigations addressed.*"
        )
    badge = rpt.decision_badge(decision_key(recommendation))
    rec_text = recommendation.split("** — ", 1)[-1] if "** — " in recommendation else recommendation
    callout = f"> {badge} — {rec_text}"
    # 3b. Decision-band legend (inline, so the viewer knows the thresholds)
    legend = "\n\n*Decision bands: GO (≤ 3.0) · GO conditional (3.0 – 4.0) · NO-GO (> 4.0)*"
    parts.append(rpt.section("Go / No-Go Recommendation", callout + legend))

    # 4. Required Mitigations (with checkbox status + reduction tag)
    display_mits = prior_mitigations if prior_mitigations else mitigations
    if display_mits:
        mit_lines = []
        for i, m in enumerate(display_mits, start=1):
            text = mitigation_text(m)
            # Reduction tag: "(−N to Dimension Label)"
            tag = ""
            if isinstance(m, dict) and m.get("target_dim") and m.get("reduction"):
                dim_label = dim_results.get(m["target_dim"], {}).get("label", m["target_dim"])
                tag = f" *(−{m['reduction']} to {dim_label})*"
            if addressed_count > 0:
                mark = "✅" if i in addressed else "⬜"
                mit_lines.append(f"{i}. {mark} {text}{tag}")
            else:
                mit_lines.append(f"{i}. {text}{tag}")
        mit_text = "\n".join(mit_lines)
        parts.append(rpt.section("Required Mitigations", mit_text))

    # 5. Risk Assessment — show inherent + residual side by side
    inherent_gauge = rpt.score_gauge(weighted_avg, risk_level)
    if residual_score != weighted_avg or residual_level != risk_level:
        residual_gauge = rpt.score_gauge(residual_score, residual_level)
        ra_content = (
            "**Inherent Risk** (raw score, before mitigations)\n\n"
            f"{inherent_gauge}\n\n"
            "**Residual Risk** (after addressed mitigations — drives the recommendation)\n\n"
            f"{residual_gauge}"
        )
    else:
        ra_content = inherent_gauge
    parts.append(rpt.section("Risk Assessment", ra_content))

    # 6. Dimension breakdown with totals + explanation rows
    show_residual = residual_dim_results is not dim_results and any(
        residual_dim_results[k]["score"] != dim_results[k]["score"]
        for k in dim_results
    )
    total_weight = sum(info["weight"] for info in dim_results.values())
    if show_residual:
        dim_headers = ["Dimension", "Inherent", "Weight", "Weighted (Inherent)",
                       "Residual", "Weighted (Residual)", "Why High"]
    else:
        dim_headers = ["Dimension", "Score (1-5)", "Weight", "Weighted", "Why High"]
    dim_rows = []
    inh_weighted_total = 0
    res_weighted_total = 0
    for dim_key, info in dim_results.items():
        weighted_val = info["score"] * info["weight"]
        inh_weighted_total += weighted_val
        score_bar = "█" * info["score"] + "░" * (5 - info["score"])
        why = explain_high_score(dim_key, cr, info["score"])
        if show_residual:
            r_score = residual_dim_results[dim_key]["score"]
            r_weighted = r_score * info["weight"]
            res_weighted_total += r_weighted
            if r_score < info["score"]:
                residual_cell = f"{info['score']} → {r_score} ✅"
            else:
                residual_cell = f"{r_score}"
            dim_rows.append([
                info["label"],
                f"{score_bar} {info['score']}",
                str(info["weight"]),
                str(weighted_val),
                residual_cell,
                str(r_weighted),
                why or "—",
            ])
        else:
            dim_rows.append([
                info["label"],
                f"{score_bar} {info['score']}",
                str(info["weight"]),
                str(weighted_val),
                why or "—",
            ])
    # Totals row
    if show_residual:
        dim_rows.append([
            "**Total**", "", f"**{total_weight}**",
            f"**{inh_weighted_total}**", "",
            f"**{res_weighted_total}**", "",
        ])
        dim_rows.append([
            "**Risk Score**", "", "",
            f"**{inh_weighted_total} ÷ {total_weight} = {weighted_avg}**", "",
            f"**{res_weighted_total} ÷ {total_weight} = {residual_score}**", "",
        ])
    else:
        dim_rows.append([
            "**Total**", "", f"**{total_weight}**",
            f"**{inh_weighted_total}**", "",
        ])
        dim_rows.append([
            "**Risk Score**", "", "",
            f"**{inh_weighted_total} ÷ {total_weight} = {weighted_avg}**", "",
        ])
    parts.append(rpt.subsection("Dimension Breakdown", rpt.table(dim_headers, dim_rows)))

    # 7. Revision History (only if prior revisions exist)
    if prior_revisions:
        history_md = render_revision_history(
            prior_revisions,
            current_rev=cr.get("revision", 1),
            current_addressed=cr.get("addressed_mitigations", []),
            current_inherent=weighted_avg,
            current_residual=residual_score,
        )
        if history_md:
            parts.append(rpt.section("Revision History", history_md))

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

    # Load prior revision history (if any) and compute residual risk
    prior_revisions = []
    prior_mitigations: List[dict] = []
    residual_dim_results = dim_results
    residual_score = weighted_avg
    residual_level = risk_level

    rev_cfg = config.get("revisions", {})
    if rev_cfg.get("enabled", True):
        history_root = SCRIPT_DIR / rev_cfg.get("history_dir", "change-revisions")
        prior_revisions = load_revision_history(str(history_root), cr.get("id", ""))
        if prior_revisions:
            print(f"  Found {len(prior_revisions)} prior revision(s) in history")
            # Track addressed mitigations against the most recent prior
            # revision's mitigation list (the "commitments" being audited).
            prior_mitigations = prior_revisions[-1].get("mitigations", []) or []

        # Apply addressed mitigations to inherent scores -> residual
        addressed = cr.get("addressed_mitigations", [])
        if prior_mitigations and addressed:
            residual_dim_results, residual_score, residual_level = compute_residual(
                dim_results, prior_mitigations, addressed, config
            )
            print(f"  Residual after {len(addressed)} addressed mitigation(s): "
                  f"{residual_score}/5.0 ({residual_level})")

        recommendation_str = go_nogo(residual_level, residual_dim_results)
        record = build_revision_record(
            cr, weighted_avg, risk_level, recommendation_str, mitigations,
            residual_score=residual_score, residual_level=residual_level,
        )
        save_path = save_revision_record(str(history_root), cr.get("id", ""), record)
        print(f"  Saved revision record: {save_path.name}")

    # Build and save report
    print("\n  Assembling report...")
    report = build_report(
        cr, dim_results, weighted_avg, risk_level,
        similar, narrative, mitigations, config,
        prior_revisions=prior_revisions,
        residual_dim_results=residual_dim_results,
        residual_score=residual_score,
        residual_level=residual_level,
        prior_mitigations=prior_mitigations,
    )
    rpt.save_report(args.output, report)

    print(f"\n  Inherent Risk: {risk_level} ({weighted_avg}/5.0)")
    if residual_score != weighted_avg:
        print(f"  Residual Risk: {residual_level} ({residual_score}/5.0)")
    print(f"  Report:        {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
