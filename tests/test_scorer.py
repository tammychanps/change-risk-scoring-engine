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
    classify_risk,
    generate_mitigations,
    go_nogo,
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
    def test_no_security_impact(self):
        assert score_security_exposure({"security_impact": False}) == 1

    def test_security_impact_no_sensitive(self):
        assert score_security_exposure({
            "security_impact": True,
            "systems_affected": ["ci-cd-pipeline"],
        }) == 4

    def test_security_impact_with_sensitive(self):
        result = score_security_exposure({
            "security_impact": True,
            "systems_affected": ["payment-gateway", "fraud-detection"],
        })
        assert result == 5

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
        assert "standard" in mits[0].lower()

    def test_high_risk_gets_war_room(self, default_config):
        dim_results = {k: {"label": k, "score": 4, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "HIGH")
        assert any("war room" in m.lower() for m in mits)

    def test_critical_gets_monitoring(self, default_config):
        dim_results = {k: {"label": k, "score": 5, "weight": 1} for k in DIMENSION_SCORERS}
        mits = generate_mitigations({}, dim_results, "CRITICAL")
        assert any("monitoring" in m.lower() for m in mits)


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
