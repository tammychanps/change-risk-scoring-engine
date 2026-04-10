"""
Tests for the Change Risk Scoring Engine.

Run:  pytest tests/test_scorer.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scorer import (
    DIMENSION_SCORERS,
    _build_overview_table,
    build_report,
    build_revision_record,
    classify_risk,
    compute_residual,
    decision_key,
    explain_high_score,
    generate_mitigations,
    go_nogo,
    load_revision_history,
    mitigation_text,
    render_revision_history,
    save_revision_record,
    score_change,
    score_change_complexity,
    score_customer_visibility,
    score_deployment_window,
    score_recent_stability,
    score_rollback_readiness,
    score_scope_impact,
    score_security_exposure,
    score_team_experience,
)

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_cr():
    """Load the sample change request."""
    path = Path(__file__).parent.parent / "sample-input.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def default_config():
    """Minimal config for testing."""
    return {
        "dimensions": {
            "scope_impact": {"label": "Scope", "weight": 3},
            "change_complexity": {"label": "Complexity", "weight": 3},
            "security_exposure": {"label": "Security", "weight": 3},
            "customer_visibility": {"label": "Customer", "weight": 2},
            "rollback_readiness": {"label": "Rollback", "weight": 2},
            "deployment_window": {"label": "Window", "weight": 1},
            "team_experience": {"label": "Experience", "weight": 2},
            "recent_stability": {"label": "Stability", "weight": 2},
        },
        "thresholds": {"LOW": 2.0, "MEDIUM": 3.0, "HIGH": 4.0},
    }


# ── Dimension Scoring Tests ──────────────────────────────────────────

class TestScopeImpact:
    def test_single_system(self):
        assert score_scope_impact({"systems_affected": ["app"]}) == 1

    def test_two_systems(self):
        assert score_scope_impact({"systems_affected": ["a", "b"]}) == 2

    def test_three_systems(self):
        assert score_scope_impact({"systems_affected": ["a", "b", "c"]}) == 3

    def test_five_systems(self):
        assert score_scope_impact({"systems_affected": ["a", "b", "c", "d", "e"]}) == 4

    def test_many_systems(self):
        assert score_scope_impact({"systems_affected": list("abcdefgh")}) == 5

    def test_no_systems(self):
        assert score_scope_impact({"systems_affected": []}) == 1

    def test_missing_field(self):
        assert score_scope_impact({}) == 1


class TestChangeComplexity:
    def test_tooling(self):
        assert score_change_complexity({"change_type": "tooling"}) == 1

    def test_compliance(self):
        assert score_change_complexity({"change_type": "compliance"}) == 2

    def test_application(self):
        assert score_change_complexity({"change_type": "application"}) == 3

    def test_infrastructure(self):
        assert score_change_complexity({"change_type": "infrastructure"}) == 4

    def test_database(self):
        assert score_change_complexity({"change_type": "database"}) == 4

    def test_unknown_type(self):
        assert score_change_complexity({"change_type": "unknown"}) == 3

    def test_missing_field(self):
        assert score_change_complexity({}) == 3


class TestSecurityExposure:
    """Security dimension is binary (1 or 4). Breadth of sensitive-system
    overlap is intentionally NOT counted here — that signal already lives
    in scope_impact + change_complexity. See DECISIONS.md."""

    def test_no_security_impact(self):
        assert score_security_exposure({"security_impact": False}) == 1

    def test_security_impact_no_sensitive(self):
        assert score_security_exposure({
            "security_impact": True,
            "systems_affected": ["ci-cd-pipeline"],
        }) == 4

    def test_security_impact_with_sensitive_does_not_bump(self):
        """Even with multiple sensitive systems, security caps at 4."""
        result = score_security_exposure({
            "security_impact": True,
            "systems_affected": ["payment-gateway", "fraud-detection"],
        })
        assert result == 4

    def test_missing_field(self):
        assert score_security_exposure({}) == 1


class TestCustomerVisibility:
    def test_not_customer_facing(self):
        assert score_customer_visibility({"customer_facing": False}) == 1

    def test_customer_facing_generic(self):
        assert score_customer_visibility({
            "customer_facing": True,
            "systems_affected": ["internal-api"],
        }) == 3

    def test_customer_facing_payment(self):
        assert score_customer_visibility({
            "customer_facing": True,
            "systems_affected": ["payment-gateway"],
        }) == 4


class TestRollbackReadiness:
    def test_plan_tested(self):
        assert score_rollback_readiness({
            "rollback_plan": "Revert DNS.",
            "rollback_tested": True,
        }) == 1

    def test_plan_not_tested(self):
        assert score_rollback_readiness({
            "rollback_plan": "Revert DNS.",
            "rollback_tested": False,
        }) == 3

    def test_no_plan(self):
        assert score_rollback_readiness({"rollback_plan": ""}) == 5

    def test_missing_fields(self):
        assert score_rollback_readiness({}) == 5


class TestDeploymentWindow:
    def test_weekend_offhours(self):
        assert score_deployment_window({"deployment_window": "Saturday 02:00-06:00 PST"}) == 1

    def test_weekend_daytime(self):
        assert score_deployment_window({"deployment_window": "Sunday 10:00-14:00"}) == 2

    def test_weekday_offhours(self):
        assert score_deployment_window({"deployment_window": "Tuesday 02:00-04:00"}) == 2

    def test_weekday_business_hours(self):
        assert score_deployment_window({"deployment_window": "Wednesday 14:00-16:00"}) == 4


class TestTeamExperience:
    def test_very_experienced(self):
        assert score_team_experience({"team_experience_similar": 10}) == 1

    def test_experienced(self):
        assert score_team_experience({"team_experience_similar": 5}) == 2

    def test_some_experience(self):
        assert score_team_experience({"team_experience_similar": 3}) == 3

    def test_little_experience(self):
        assert score_team_experience({"team_experience_similar": 1}) == 4

    def test_no_experience(self):
        assert score_team_experience({"team_experience_similar": 0}) == 5

    def test_missing_field(self):
        assert score_team_experience({}) == 5


class TestRecentStability:
    def test_no_incidents(self):
        assert score_recent_stability({"recent_incidents_30d": 0}) == 1

    def test_one_incident(self):
        assert score_recent_stability({"recent_incidents_30d": 1}) == 3

    def test_two_incidents(self):
        assert score_recent_stability({"recent_incidents_30d": 2}) == 4

    def test_many_incidents(self):
        assert score_recent_stability({"recent_incidents_30d": 5}) == 5

    def test_missing_field(self):
        assert score_recent_stability({}) == 1


# ── Overall Scoring Tests ────────────────────────────────────────────

class TestScoreChange:
    def test_returns_all_dimensions(self, sample_cr, default_config):
        results, avg = score_change(sample_cr, default_config)
        assert len(results) == 8
        for key in DIMENSION_SCORERS:
            assert key in results

    def test_scores_in_range(self, sample_cr, default_config):
        results, avg = score_change(sample_cr, default_config)
        for info in results.values():
            assert 1 <= info["score"] <= 5

    def test_weighted_average_in_range(self, sample_cr, default_config):
        results, avg = score_change(sample_cr, default_config)
        assert 1.0 <= avg <= 5.0

    def test_known_input_known_score(self, default_config):
        """All-minimum CR should score close to 1.0."""
        cr = {
            "systems_affected": ["one-app"],
            "change_type": "tooling",
            "security_impact": False,
            "customer_facing": False,
            "rollback_plan": "Tested rollback.",
            "rollback_tested": True,
            "deployment_window": "Saturday 03:00-04:00",
            "team_experience_similar": 15,
            "recent_incidents_30d": 0,
        }
        results, avg = score_change(cr, default_config)
        assert avg == 1.0
        for info in results.values():
            assert info["score"] == 1

    def test_high_risk_input(self, default_config):
        """All-maximum CR should score close to 5.0."""
        cr = {
            "systems_affected": list("abcdefgh"),
            "change_type": "database",
            "security_impact": True,
            "customer_facing": True,
            "rollback_plan": "",
            "rollback_tested": False,
            "deployment_window": "Wednesday 14:00-16:00",
            "team_experience_similar": 0,
            "recent_incidents_30d": 5,
        }
        results, avg = score_change(cr, default_config)
        assert avg >= 4.0


# ── Risk Classification Tests ────────────────────────────────────────

class TestClassifyRisk:
    def test_low(self, default_config):
        assert classify_risk(1.5, default_config) == "LOW"

    def test_low_boundary(self, default_config):
        assert classify_risk(2.0, default_config) == "LOW"

    def test_medium(self, default_config):
        assert classify_risk(2.5, default_config) == "MEDIUM"

    def test_medium_boundary(self, default_config):
        assert classify_risk(3.0, default_config) == "MEDIUM"

    def test_high(self, default_config):
        assert classify_risk(3.5, default_config) == "HIGH"

    def test_high_boundary(self, default_config):
        assert classify_risk(4.0, default_config) == "HIGH"

    def test_critical(self, default_config):
        assert classify_risk(4.5, default_config) == "CRITICAL"

    def test_extreme(self, default_config):
        assert classify_risk(5.0, default_config) == "CRITICAL"


# ── Edge Cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_input(self, default_config):
        """Empty dict should not crash — returns safe defaults."""
        results, avg = score_change({}, default_config)
        assert len(results) == 8
        assert avg >= 1.0

    def test_missing_all_optional_fields(self, default_config):
        cr = {"id": "CR-TEST", "title": "Test"}
        results, avg = score_change(cr, default_config)
        assert len(results) == 8

    def test_extra_fields_ignored(self, default_config):
        cr = {
            "id": "CR-TEST",
            "extra_field": "should be ignored",
            "systems_affected": ["app"],
            "change_type": "tooling",
        }
        results, avg = score_change(cr, default_config)
        assert len(results) == 8


# ── Mitigation Tests ─────────────────────────────────────────────────

class TestMitigations:
    def test_low_risk_gets_standard(self, default_config):
        dim_results = {k: {"label": k, "score": 1, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "LOW")
        assert len(mits) >= 1
        assert "standard" in mits[0]["text"].lower()

    def test_high_risk_gets_war_room(self, default_config):
        dim_results = {k: {"label": k, "score": 4, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "HIGH")
        assert any("war room" in m["text"].lower() for m in mits)

    def test_critical_gets_monitoring(self, default_config):
        dim_results = {k: {"label": k, "score": 5, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "CRITICAL")
        assert any("monitoring" in m["text"].lower() for m in mits)

    def test_mitigations_are_tagged_dicts(self, default_config):
        """Each mitigation must carry text + target_dim + reduction."""
        dim_results = {k: {"label": k, "score": 4, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "HIGH")
        for m in mits:
            assert isinstance(m, dict)
            assert "text" in m and m["text"]
            assert "target_dim" in m  # may be None for the standard fallback
            assert "reduction" in m


# ── Go/No-Go Tests ───────────────────────────────────────────────────

class TestGoNoGo:
    def test_low_is_go(self):
        dim_results = {k: {"label": k, "score": 1, "weight": 1} for k in DIMENSION_SCORERS}
        result = go_nogo("LOW", dim_results)
        assert "GO" in result

    def test_critical_is_nogo(self):
        dim_results = {k: {"label": k, "score": 5, "weight": 1} for k in DIMENSION_SCORERS}
        result = go_nogo("CRITICAL", dim_results)
        assert "NO-GO" in result


# ── Decision Key Tests ──────────────────────────────────────────────

class TestDecisionKey:
    def test_go_string(self):
        assert decision_key("**GO** — Low risk.") == "GO"

    def test_go_conditional_string(self):
        assert decision_key("**GO (conditional)** — Proceed.") == "GO_CONDITIONAL"

    def test_no_go_string(self):
        assert decision_key("**NO-GO** — Critical.") == "NO_GO"

    def test_no_go_pending_mitigations(self):
        assert decision_key("**NO-GO (pending mitigations)** —") == "NO_GO"


# ── Explain High Score Tests (rule-based justification) ─────────────

class TestExplainHighScore:
    def test_no_explanation_below_4(self):
        cr = {"systems_affected": ["a"]}
        assert explain_high_score("scope_impact", cr, 3) == ""

    def test_no_explanation_for_score_1(self):
        assert explain_high_score("security_exposure", {}, 1) == ""

    def test_security_high_mentions_infosec(self):
        cr = {"security_impact": True}
        out = explain_high_score("security_exposure", cr, 5)
        assert "InfoSec" in out

    def test_complexity_high_mentions_change_type(self):
        cr = {"change_type": "infrastructure", "systems_affected": ["a", "b"]}
        out = explain_high_score("change_complexity", cr, 4)
        assert "Infrastructure" in out
        assert "2 system" in out

    def test_customer_visibility_mentions_end_users(self):
        out = explain_high_score("customer_visibility", {}, 4)
        assert "end users" in out.lower()

    def test_scope_impact_lists_systems(self):
        cr = {"systems_affected": ["a", "b", "c", "d"]}
        out = explain_high_score("scope_impact", cr, 5)
        assert "4 systems" in out
        assert "..." in out  # truncates after 3

    def test_recent_stability_includes_count(self):
        cr = {"recent_incidents_30d": 7}
        out = explain_high_score("recent_stability", cr, 4)
        assert "7 incidents" in out

    def test_unknown_dimension_falls_through(self):
        out = explain_high_score("unknown_dim", {}, 5)
        assert "5/5" in out


# ── Overview Table Tests ─────────────────────────────────────────────

class TestOverviewTable:
    def test_includes_new_metadata_fields(self, sample_cr):
        out = _build_overview_table(sample_cr)
        assert "Requester" in out
        assert "Requesting Team" in out
        assert "Implementation Team" in out
        assert "CAB Date" in out
        assert "Implementation Plan" in out

    def test_renders_implementation_plan_as_link(self, sample_cr):
        out = _build_overview_table(sample_cr)
        assert "[View Runbook]" in out
        assert "https://" in out

    def test_revision_appears_in_change_id_cell(self, sample_cr):
        out = _build_overview_table(sample_cr)
        assert "rev 1" in out

    def test_two_column_layout_has_5_pipes_per_row(self, sample_cr):
        out = _build_overview_table(sample_cr)
        # Two-column structure: | Field | Value |  | Field | Value |
        # Each data row should have 6 pipe characters (5 separators + outer)
        data_lines = [l for l in out.split("\n") if l.startswith("| **")]
        assert all(line.count("|") == 6 for line in data_lines)

    def test_handles_missing_optional_fields(self):
        cr = {"id": "CR-X", "title": "X"}
        out = _build_overview_table(cr)
        assert "N/A" in out  # falls back gracefully


# ── Report Layout Tests ─────────────────────────────────────────────

class TestReportLayout:
    def _build(self, sample_cr):
        config = {"thresholds": {"LOW": 2.0, "MEDIUM": 3.0, "HIGH": 4.0},
                  "report": {"include_narrative": True, "include_mitigations": True}}
        # Synthesize minimal dim_results
        dim_results = {
            "scope_impact": {"label": "Scope / Blast Radius", "score": 3, "weight": 3},
            "change_complexity": {"label": "Change Complexity", "score": 4, "weight": 3},
            "security_exposure": {"label": "Security Exposure", "score": 5, "weight": 3},
            "customer_visibility": {"label": "Customer Visibility", "score": 4, "weight": 2},
            "rollback_readiness": {"label": "Rollback Readiness", "score": 1, "weight": 2},
            "deployment_window": {"label": "Deployment Window", "score": 1, "weight": 1},
            "team_experience": {"label": "Team Experience", "score": 3, "weight": 2},
            "recent_stability": {"label": "Recent Stability", "score": 3, "weight": 2},
        }
        return build_report(
            sample_cr, dim_results, 3.28, "HIGH", [],
            "AI-written narrative goes here.",
            ["Mitigation 1", "Mitigation 2"], config,
        )

    def test_narrative_appears_before_dimension_breakdown(self, sample_cr):
        report = self._build(sample_cr)
        narr_pos = report.index("Risk Narrative")
        dim_pos = report.index("Dimension Breakdown")
        assert narr_pos < dim_pos

    def test_recommendation_appears_before_risk_assessment(self, sample_cr):
        report = self._build(sample_cr)
        rec_pos = report.index("## Go / No-Go Recommendation")
        risk_pos = report.index("## Risk Assessment")
        assert rec_pos < risk_pos

    def test_mitigations_appear_before_risk_assessment(self, sample_cr):
        report = self._build(sample_cr)
        mit_pos = report.index("## Required Mitigations")
        risk_pos = report.index("## Risk Assessment")
        assert mit_pos < risk_pos

    def test_recommendation_uses_color_badge(self, sample_cr):
        report = self._build(sample_cr)
        # HIGH risk with no critical-scoring dims -> conditional GO -> yellow
        # But this fixture has score 5 in security_exposure -> NO-GO -> red
        assert "🔴" in report or "🟡" in report or "🟢" in report

    def test_dimension_table_includes_why_high_column(self, sample_cr):
        report = self._build(sample_cr)
        assert "Why High" in report

    def test_low_score_rows_show_dash_in_why_high(self, sample_cr):
        report = self._build(sample_cr)
        # Rollback Readiness scores 1, should show "—" in Why High
        # Find that row in the dimension table
        for line in report.split("\n"):
            if "Rollback Readiness" in line and "|" in line:
                assert line.rstrip().endswith("— |")
                return
        pytest.fail("Rollback Readiness row not found")

    def test_high_score_row_shows_explanation(self, sample_cr):
        report = self._build(sample_cr)
        # security_exposure scores 5 -> should mention InfoSec
        for line in report.split("\n"):
            if "Security Exposure" in line and "|" in line:
                assert "InfoSec" in line
                return
        pytest.fail("Security Exposure row not found")


# ── Revision History Tests ──────────────────────────────────────────

class TestRevisionHistory:
    def test_load_no_history_returns_empty(self, tmp_path):
        result = load_revision_history(str(tmp_path), "CR-NONEXISTENT")
        assert result == []

    def test_save_creates_per_change_folder(self, tmp_path):
        record = {"change_id": "CR-X", "revision": 1, "score": 2.5}
        path = save_revision_record(str(tmp_path), "CR-X", record)
        assert path.exists()
        assert path.parent.name == "CR-X"
        assert path.name == "rev-1.json"

    def test_save_then_load_round_trip(self, tmp_path):
        rec1 = {"change_id": "CR-Y", "revision": 1, "score": 3.0, "level": "MEDIUM"}
        rec2 = {"change_id": "CR-Y", "revision": 2, "score": 2.0, "level": "LOW"}
        save_revision_record(str(tmp_path), "CR-Y", rec1)
        save_revision_record(str(tmp_path), "CR-Y", rec2)
        history = load_revision_history(str(tmp_path), "CR-Y")
        assert len(history) == 2
        assert history[0]["revision"] == 1
        assert history[1]["revision"] == 2

    def test_save_is_idempotent_for_same_revision(self, tmp_path):
        rec = {"change_id": "CR-Z", "revision": 1, "score": 3.0}
        save_revision_record(str(tmp_path), "CR-Z", rec)
        rec["score"] = 2.5  # rerun with updated score
        save_revision_record(str(tmp_path), "CR-Z", rec)
        history = load_revision_history(str(tmp_path), "CR-Z")
        assert len(history) == 1
        assert history[0]["score"] == 2.5

    def test_build_revision_record_captures_decision(self):
        cr = {"id": "CR-A", "revision": 1}
        record = build_revision_record(
            cr, 3.28, "HIGH", "**GO (conditional)** — proceed.", ["Mit 1"]
        )
        assert record["change_id"] == "CR-A"
        assert record["revision"] == 1
        assert record["decision"] == "GO_CONDITIONAL"
        assert record["score"] == 3.28
        assert "timestamp" in record

    def test_build_revision_record_includes_addressed_mitigations(self):
        cr = {"id": "CR-A", "revision": 2, "addressed_mitigations": [1, 2, 3]}
        record = build_revision_record(cr, 2.0, "LOW", "**GO** —", [])
        assert record["addressed_mitigations"] == [1, 2, 3]

    def test_render_history_returns_empty_with_no_prior(self):
        out = render_revision_history([], current_rev=1, current_addressed=[])
        assert out == ""

    def test_render_history_lists_prior_revisions(self):
        history = [
            {"revision": 1, "timestamp": "2026-04-09T10:00:00", "score": 3.28,
             "level": "HIGH", "decision": "GO_CONDITIONAL", "mitigations": ["A", "B"]},
        ]
        out = render_revision_history(history, current_rev=2, current_addressed=[1, 2])
        assert "rev 1" in out
        assert "3.28" in out
        assert "HIGH" in out

    def test_render_history_marks_addressed_mitigations(self):
        history = [
            {"revision": 1, "timestamp": "2026-04-09T10:00:00", "score": 3.28,
             "level": "HIGH", "decision": "GO_CONDITIONAL",
             "mitigations": ["First mit", "Second mit", "Third mit"]},
        ]
        out = render_revision_history(history, current_rev=2, current_addressed=[1, 3])
        assert "✅ 1. First mit" in out
        assert "⬜ 2. Second mit" in out
        assert "✅ 3. Third mit" in out

    def test_render_history_excludes_current_revision(self):
        history = [
            {"revision": 1, "timestamp": "2026-04-09T10:00:00", "score": 3.28,
             "level": "HIGH", "decision": "GO_CONDITIONAL", "mitigations": []},
            {"revision": 2, "timestamp": "2026-04-10T15:30:00", "score": 2.0,
             "level": "LOW", "decision": "GO", "mitigations": []},
        ]
        out = render_revision_history(history, current_rev=2, current_addressed=[])
        # rev 2 (current) should NOT appear in the prior table
        assert "2026-04-09" in out
        assert "2026-04-10" not in out

    def test_render_history_handles_dict_mitigations(self):
        """Mitigations stored as dicts (new schema) should render their text."""
        history = [
            {"revision": 1, "timestamp": "2026-04-09T10:00:00", "score": 3.28,
             "level": "HIGH", "decision": "GO_CONDITIONAL",
             "mitigations": [
                 {"text": "Dry-run in staging", "target_dim": "change_complexity",
                  "reduction": 1},
                 {"text": "Engage InfoSec", "target_dim": "security_exposure",
                  "reduction": 1},
             ]},
        ]
        out = render_revision_history(history, current_rev=2, current_addressed=[1])
        assert "Dry-run in staging" in out
        assert "Engage InfoSec" in out
        assert "✅ 1." in out
        assert "⬜ 2." in out

    def test_render_history_shows_inherent_and_residual_columns(self):
        """New schema records show both inherent and residual progression."""
        history = [
            {"revision": 1, "timestamp": "2026-04-09T10:00:00",
             "inherent_score": 3.28, "inherent_level": "HIGH",
             "residual_score": 3.28, "residual_level": "HIGH",
             "decision": "GO_CONDITIONAL", "mitigations": []},
        ]
        out = render_revision_history(history, current_rev=2, current_addressed=[])
        assert "Inherent" in out
        assert "Residual" in out
        assert "3.28/5.0 HIGH" in out


# ── Inherent vs Residual Risk Tests ──────────────────────────────────

class TestComputeResidual:
    """compute_residual applies addressed mitigations to inherent scores
    to produce a residual dim_results, weighted average, and risk level."""

    def _inherent(self):
        return {
            "scope_impact": {"label": "Scope", "score": 3, "weight": 3},
            "change_complexity": {"label": "Complexity", "score": 4, "weight": 3},
            "security_exposure": {"label": "Security", "score": 4, "weight": 3},
            "customer_visibility": {"label": "Customer", "score": 4, "weight": 2},
            "rollback_readiness": {"label": "Rollback", "score": 1, "weight": 2},
            "deployment_window": {"label": "Window", "score": 1, "weight": 1},
            "team_experience": {"label": "Experience", "score": 3, "weight": 2},
            "recent_stability": {"label": "Stability", "score": 3, "weight": 2},
        }

    def _config(self):
        return {"thresholds": {"LOW": 2.0, "MEDIUM": 3.0, "HIGH": 4.0}}

    def _mits(self):
        return [
            {"text": "Dry-run", "target_dim": "change_complexity", "reduction": 1},
            {"text": "InfoSec", "target_dim": "security_exposure", "reduction": 1},
            {"text": "Comms", "target_dim": "customer_visibility", "reduction": 1},
            {"text": "War room", "target_dim": "team_experience", "reduction": 1},
            {"text": "Monitoring", "target_dim": "recent_stability", "reduction": 1},
        ]

    def test_no_addressed_returns_unchanged_scores(self):
        inh = self._inherent()
        residual, avg, level = compute_residual(inh, self._mits(), [], self._config())
        for k in inh:
            assert residual[k]["score"] == inh[k]["score"]

    def test_all_addressed_drops_targeted_dims(self):
        residual, avg, level = compute_residual(
            self._inherent(), self._mits(), [1, 2, 3, 4, 5], self._config()
        )
        # All five targeted dims should drop by 1
        assert residual["change_complexity"]["score"] == 3
        assert residual["security_exposure"]["score"] == 3
        assert residual["customer_visibility"]["score"] == 3
        assert residual["team_experience"]["score"] == 2
        assert residual["recent_stability"]["score"] == 2
        # Untouched dims unchanged
        assert residual["scope_impact"]["score"] == 3
        assert residual["rollback_readiness"]["score"] == 1

    def test_partial_addressed_drops_only_specified(self):
        residual, avg, level = compute_residual(
            self._inherent(), self._mits(), [2, 5], self._config()
        )
        assert residual["security_exposure"]["score"] == 3  # mit 2 addressed
        assert residual["recent_stability"]["score"] == 2  # mit 5 addressed
        assert residual["change_complexity"]["score"] == 4  # mit 1 NOT addressed
        assert residual["customer_visibility"]["score"] == 4  # mit 3 NOT addressed
        assert residual["team_experience"]["score"] == 3  # mit 4 NOT addressed

    def test_residual_score_floors_at_1(self):
        """Score cannot drop below 1 even with multiple reductions."""
        inh = self._inherent()
        inh["security_exposure"]["score"] = 2
        mits = [
            {"text": "A", "target_dim": "security_exposure", "reduction": 1},
            {"text": "B", "target_dim": "security_exposure", "reduction": 1},
            {"text": "C", "target_dim": "security_exposure", "reduction": 1},
        ]
        residual, avg, level = compute_residual(inh, mits, [1, 2, 3], self._config())
        assert residual["security_exposure"]["score"] == 1  # floor, not 0 or -1

    def test_recomputes_weighted_average(self):
        """Residual weighted average must recompute from new scores."""
        inh = self._inherent()
        _, inh_avg, _ = compute_residual(inh, self._mits(), [], self._config())
        residual, res_avg, _ = compute_residual(
            inh, self._mits(), [1, 2, 3, 4, 5], self._config()
        )
        assert res_avg < inh_avg  # residual must be lower

    def test_recomputes_risk_level(self):
        """Risk level reclassifies when residual crosses a threshold."""
        # Inherent: all dims at 5 → CRITICAL
        inh = {k: {"label": k, "score": 5, "weight": 1} for k in DIMENSION_SCORERS}
        mits = [
            {"text": f"M{k}", "target_dim": k, "reduction": 4}
            for k in DIMENSION_SCORERS
        ]
        all_indices = list(range(1, len(mits) + 1))
        _, inh_avg, inh_level = compute_residual(inh, mits, [], self._config())
        _, res_avg, res_level = compute_residual(inh, mits, all_indices, self._config())
        levels_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        assert inh_level == "CRITICAL"
        # All scores driven to floor (1) → residual should be LOW
        assert res_level == "LOW"
        assert levels_order[res_level] < levels_order[inh_level]

    def test_invalid_addressed_index_ignored(self):
        """Out-of-range addressed indices should be silently ignored."""
        residual, avg, level = compute_residual(
            self._inherent(), self._mits(), [99], self._config()
        )
        # No change — index 99 doesn't map to any mitigation
        for k in self._inherent():
            assert residual[k]["score"] == self._inherent()[k]["score"]

    def test_does_not_mutate_input(self):
        """compute_residual must not mutate the inherent dim_results."""
        inh = self._inherent()
        original_security = inh["security_exposure"]["score"]
        compute_residual(inh, self._mits(), [1, 2, 3, 4, 5], self._config())
        assert inh["security_exposure"]["score"] == original_security


class TestRevisionRecordInherentResidual:
    """build_revision_record stores both inherent and residual scores."""

    def test_stores_inherent_and_residual_separately(self):
        cr = {"id": "CR-X", "revision": 2, "addressed_mitigations": [1, 2]}
        record = build_revision_record(
            cr, weighted_avg=3.28, risk_level="HIGH",
            recommendation="**GO** —", mitigations=[],
            residual_score=1.8, residual_level="LOW",
        )
        assert record["inherent_score"] == 3.28
        assert record["inherent_level"] == "HIGH"
        assert record["residual_score"] == 1.8
        assert record["residual_level"] == "LOW"

    def test_residual_defaults_to_inherent_when_not_provided(self):
        cr = {"id": "CR-X", "revision": 1}
        record = build_revision_record(
            cr, weighted_avg=3.28, risk_level="HIGH",
            recommendation="**GO (conditional)** —", mitigations=[],
        )
        assert record["inherent_score"] == record["residual_score"] == 3.28
        assert record["inherent_level"] == record["residual_level"] == "HIGH"

    def test_score_field_holds_residual_for_backward_compat(self):
        cr = {"id": "CR-X", "revision": 2}
        record = build_revision_record(
            cr, weighted_avg=3.28, risk_level="HIGH",
            recommendation="**GO** —", mitigations=[],
            residual_score=1.8, residual_level="LOW",
        )
        # Legacy `score`/`level` fields should reflect residual (the
        # decision-relevant value), so old downstream code keeps working.
        assert record["score"] == 1.8
        assert record["level"] == "LOW"

    def test_dict_mitigations_preserved_with_target_dim(self):
        cr = {"id": "CR-X", "revision": 1}
        mits = [
            {"text": "Dry run", "target_dim": "change_complexity", "reduction": 1},
            {"text": "InfoSec", "target_dim": "security_exposure", "reduction": 1},
        ]
        record = build_revision_record(
            cr, weighted_avg=3.0, risk_level="MEDIUM",
            recommendation="**GO (conditional)** —", mitigations=mits,
        )
        assert len(record["mitigations"]) == 2
        assert record["mitigations"][0]["text"] == "Dry run"
        assert record["mitigations"][0]["target_dim"] == "change_complexity"

    def test_string_mitigations_normalized_to_dicts(self):
        """Legacy string mitigations should be normalized for the audit record."""
        cr = {"id": "CR-X", "revision": 1}
        record = build_revision_record(
            cr, weighted_avg=3.0, risk_level="MEDIUM",
            recommendation="**GO (conditional)** —",
            mitigations=["legacy string mit"],
        )
        assert record["mitigations"][0]["text"] == "legacy string mit"
        assert record["mitigations"][0]["target_dim"] is None
