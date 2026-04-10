"""
Tests for shared report helpers in common/report.py.

Covers the new gauge + decision badge helpers added for the
change-risk-scoring-engine CAB report enhancements.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.report import decision_badge, risk_badge, score_gauge


# ── score_gauge ──────────────────────────────────────────────────────

class TestScoreGauge:
    def test_low_score_marks_low_band(self):
        out = score_gauge(1.5, "LOW")
        assert "LOW (≤2.0)▲" in out
        assert "1.5 / 5.0" in out

    def test_medium_score_marks_med_band(self):
        out = score_gauge(2.7, "MEDIUM")
        assert "MED (≤3.0)▲" in out
        assert "**LOW**" not in out  # only the active band has the marker

    def test_high_score_marks_high_band(self):
        out = score_gauge(3.28, "HIGH")
        assert "HIGH (≤4.0)▲" in out
        assert "3.28 / 5.0" in out

    def test_critical_score_marks_crit_band(self):
        out = score_gauge(4.6, "CRITICAL")
        assert "CRIT (>4.0)▲" in out

    def test_only_one_band_marked(self):
        out = score_gauge(3.28, "HIGH")
        # Only one triangle should appear
        assert out.count("▲") == 1

    def test_gauge_shows_all_threshold_boundaries(self):
        """Gauge must display numeric thresholds for all bands."""
        out = score_gauge(3.0, "MEDIUM")
        assert "≤2.0" in out
        assert "≤3.0" in out
        assert "≤4.0" in out
        assert ">4.0" in out

    def test_gauge_renders_as_markdown_table(self):
        out = score_gauge(3.28, "HIGH")
        # Markdown table has header separator
        assert "| --- |" in out
        assert "Score" in out
        assert "Where it sits" in out

    def test_gauge_includes_color_badge(self):
        out = score_gauge(3.28, "HIGH")
        assert "🔴" in out  # HIGH badge color


# ── decision_badge ──────────────────────────────────────────────────

class TestDecisionBadge:
    def test_go_badge(self):
        assert "🟢" in decision_badge("GO")
        assert "**GO**" in decision_badge("GO")

    def test_go_conditional_badge_underscore(self):
        out = decision_badge("GO_CONDITIONAL")
        assert "🟡" in out
        assert "CONDITIONAL" in out

    def test_go_conditional_human_readable(self):
        out = decision_badge("GO (conditional)")
        assert "🟡" in out

    def test_no_go_badge_with_dash(self):
        out = decision_badge("NO-GO")
        assert "🔴" in out
        assert "NO-GO" in out

    def test_no_go_badge_with_underscore(self):
        out = decision_badge("NO_GO")
        assert "🔴" in out

    def test_unknown_decision_falls_through(self):
        out = decision_badge("DEFER")
        assert "DEFER" in out
