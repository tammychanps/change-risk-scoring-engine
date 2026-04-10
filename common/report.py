"""
Markdown report generation utilities.

Shared formatting functions for all 3 portfolio projects.
"""

from datetime import datetime
from typing import List, Dict, Optional


def header(title: str, subtitle: str = "", date: Optional[str] = None) -> str:
    """Generate a report header."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    lines = [f"# {title}"]
    if subtitle:
        lines.append(f"## {subtitle}")
    lines.append(f"\n> Generated: {date_str}")
    lines.append(f"> Tool: AI-powered analysis with local LLM (Ollama) for data security")
    lines.append("")
    return "\n".join(lines)


def section(title: str, content: str) -> str:
    """Generate a section with heading."""
    return f"\n## {title}\n\n{content}\n"


def subsection(title: str, content: str) -> str:
    """Generate a subsection with heading."""
    return f"\n### {title}\n\n{content}\n"


def table(headers: List[str], rows: List[List[str]]) -> str:
    """Generate a markdown table."""
    if not headers or not rows:
        return ""
    # Header row
    header_line = "| " + " | ".join(str(h) for h in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    # Data rows
    data_lines = []
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))  # pad if short
        data_lines.append("| " + " | ".join(str(c) for c in padded[:len(headers)]) + " |")
    return "\n".join([header_line, separator] + data_lines)


def risk_badge(level: str) -> str:
    """Generate a risk level badge. Level: LOW, MEDIUM, HIGH, CRITICAL."""
    badges = {
        "LOW": "**LOW** ✅",
        "MEDIUM": "**MEDIUM** ⚠️",
        "HIGH": "**HIGH** 🔴",
        "CRITICAL": "**CRITICAL** 🚨",
    }
    return badges.get(level.upper(), f"**{level.upper()}**")


def rag_status(status: str) -> str:
    """Generate a RAG (Red/Amber/Green) status indicator."""
    indicators = {
        "GREEN": "🟢 **GREEN** — On Track",
        "AMBER": "🟡 **AMBER** — At Risk",
        "RED": "🔴 **RED** — Off Track",
    }
    return indicators.get(status.upper(), f"**{status.upper()}**")


def action_item(number: int, action: str, owner: str = "", due: str = "") -> str:
    """Generate a numbered action item."""
    parts = [f"{number}. {action}"]
    if owner:
        parts.append(f"**Owner:** {owner}")
    if due:
        parts.append(f"**Due:** {due}")
    return " — ".join(parts) if len(parts) > 1 else parts[0]


def save_report(filepath: str, content: str):
    """Save a markdown report to file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] Report saved: {filepath}")


def score_gauge(score: float, level: str, max_score: float = 5.0) -> str:
    """
    Render a single-row inline gauge table showing score, level, and band position.

    Output is a markdown table that puts score, color-coded level, and a text
    gauge in one row so reviewers see the position at a glance.
    """
    bands = ["LOW", "MED", "HIGH", "CRIT"]
    level_short = {
        "LOW": "LOW",
        "MEDIUM": "MED",
        "HIGH": "HIGH",
        "CRITICAL": "CRIT",
    }.get(level.upper(), level.upper()[:4])

    # Mark the active band with a triangle + show threshold boundaries
    band_labels = {
        "LOW": "LOW (≤2.0)",
        "MED": "MED (≤3.0)",
        "HIGH": "HIGH (≤4.0)",
        "CRIT": "CRIT (>4.0)",
    }
    gauge_parts = []
    for band in bands:
        label = band_labels[band]
        if band == level_short:
            gauge_parts.append(f"{label}▲")
        else:
            gauge_parts.append(label)
    gauge_str = " │ ".join(gauge_parts)

    badge = risk_badge(level)
    rows = [[f"**{score} / {max_score}**", badge, f"`{gauge_str}`"]]
    return table(["Score", "Level", "Where it sits"], rows)


def decision_badge(decision: str) -> str:
    """
    Color-coded badge for Go/No-Go recommendations.

    Accepts: GO, GO_CONDITIONAL, NO_GO (or human-readable variants).
    """
    key = decision.upper().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
    badges = {
        "GO": "🟢 **GO**",
        "GO_CONDITIONAL": "🟡 **GO (CONDITIONAL)**",
        "NO_GO": "🔴 **NO-GO**",
        "NOGO": "🔴 **NO-GO**",
    }
    return badges.get(key, f"**{decision.upper()}**")


def score_to_level(score: float, thresholds: Dict[str, float] = None) -> str:
    """Convert a numeric score to a risk level string."""
    if thresholds is None:
        thresholds = {"LOW": 2.0, "MEDIUM": 3.0, "HIGH": 4.0}
    if score <= thresholds.get("LOW", 2.0):
        return "LOW"
    elif score <= thresholds.get("MEDIUM", 3.0):
        return "MEDIUM"
    elif score <= thresholds.get("HIGH", 4.0):
        return "HIGH"
    else:
        return "CRITICAL"
