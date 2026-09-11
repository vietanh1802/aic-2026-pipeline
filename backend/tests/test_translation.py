from __future__ import annotations

from app.routers.evaluation import translation_policies
from app.translation import (
    DEFAULT_TRANSLATION_POLICY,
    TRANSLATION_POLICIES,
    normalize_translation_policy,
    translation_policy_options,
    translator_id_for_policy,
)

# literal_v1 was added as a plain baseline after our own experiment found
# visual_faithful scored worst of all tested policies (24% Top-1 / 0.428 MRR
# vs. the plain baseline's 48% Top-1 / 0.542 MRR). literal_visual_v2 is a
# second, non-default option available for selection per run.
EXISTING_FOUR = {"visual_faithful", "scene_clauses", "retrieval_compact", "salience_first"}


def test_default_policy_is_literal_v1() :
    assert DEFAULT_TRANSLATION_POLICY == "literal_v1"


def test_literal_v1_and_literal_visual_v2_are_registered() :
    assert "literal_v1" in TRANSLATION_POLICIES
    assert "literal_visual_v2" in TRANSLATION_POLICIES


def test_existing_four_policies_are_unchanged() :
    assert EXISTING_FOUR <= TRANSLATION_POLICIES.keys()


def test_translation_policy_options_includes_both_new_policies() :
    ids = {option["id"] for option in translation_policy_options()}
    assert {"literal_v1", "literal_visual_v2"} <= ids
    assert EXISTING_FOUR <= ids


def test_translator_id_for_policy_is_distinct_for_new_policies() :
    ids = {translator_id_for_policy(policy) for policy in TRANSLATION_POLICIES}
    assert len(ids) == len(TRANSLATION_POLICIES)


def test_normalize_translation_policy_defaults_to_literal_v1() :
    assert normalize_translation_policy(None) == "literal_v1"


def test_translation_policies_endpoint_default_is_literal_v1() :
    response = translation_policies(None)
    assert response["default"] == "literal_v1"
    ids = {option["id"] for option in response["policies"]}
    assert {"literal_v1", "literal_visual_v2"} <= ids
