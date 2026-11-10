"""Tests for the domain rules that orchestrate H2 runs (pure functions, GEN-47).

Acceptance: run keys and branch names are deterministic per the repo
conventions, PR/commit texts link back to Linear, the agent prompt states the
sandbox hard rules, audit ids are stable per phase, and every invalid input
fails fast with a clear error.
"""

import pytest

from super_factory.domain.pipeline import (
    branch_name_for,
    build_agent_prompt,
    commit_message_for,
    is_valid_run_key,
    linear_issue_url,
    pipeline_audit_delivery_id,
    pr_body_for,
    pr_title_for,
    run_key_for,
    slugify,
)


def test_run_key_is_deterministic_per_issue_and_spec_version() -> None:
    assert run_key_for("GEN-47", 1) == "GEN-47-v1"
    assert run_key_for("GEN-47", 2) == "GEN-47-v2"
    assert run_key_for("GEN-47", 1) == run_key_for("GEN-47", 1)


def test_run_key_rejects_bad_issue_or_version() -> None:
    with pytest.raises(ValueError, match="GEN-N format"):
        run_key_for("ISS-1", 1)
    with pytest.raises(ValueError, match="spec_version"):
        run_key_for("GEN-47", 0)


def test_is_valid_run_key_matches_shape() -> None:
    assert is_valid_run_key("GEN-47-v1")
    assert not is_valid_run_key("GEN-47")
    assert not is_valid_run_key("GEN-47-V1")
    assert not is_valid_run_key("")
    assert not is_valid_run_key("issue-GEN-47-v1")


def test_slugify_strips_accents_symbols_and_collapses_dashes() -> None:
    assert slugify("H2 \u2014 agente Codex aislado, y PR") == "h2-agente-codex-aislado-y-pr"
    assert slugify("Hello, World!!!") == "hello-world"
    assert slugify("   ") == "task"
    assert slugify("") == "task"
    assert slugify("\u00e1\u00e9\u00ed\u00f3\u00fa") == "aeiou"


def test_slugify_truncates_to_branch_safe_length() -> None:
    long = slugify("a b c d e f g h i j k l m n o p q r s t u v w x y z 1 2 3")
    assert len(long) <= 48
    assert not long.endswith("-")


def test_branch_name_follows_repo_conventions() -> None:
    assert branch_name_for("GEN-47", "H2 \u2014 agente Codex") == "feat/gen-47-h2-agente-codex"
    assert branch_name_for("GEN-47", "H2 \u2014 agente Codex") == branch_name_for(
        "GEN-47", "H2 \u2014 agente Codex"
    )
    with pytest.raises(ValueError, match="GEN-N format"):
        branch_name_for("nope", "any")


def test_pr_title_is_conventional_and_collapses_whitespace() -> None:
    assert pr_title_for("GEN-47", "Isolated  Codex\nagent") == "feat(gen-47): Isolated Codex agent"


def test_pr_title_truncates_long_objectives() -> None:
    title = pr_title_for("GEN-47", "x" * 200)
    assert title.startswith("feat(gen-47): ")
    assert len(title) <= len("feat(gen-47): ") + 72


def test_commit_message_matches_pr_title() -> None:
    assert commit_message_for("GEN-47", "objective") == pr_title_for("GEN-47", "objective")


def test_linear_issue_url_uses_workspace_template() -> None:
    assert (
        linear_issue_url("GEN-47")
        == "https://linear.app/genesisnavarra/issue/GEN-47"
    )
    assert (
        linear_issue_url("GEN-47", template="https://linear.local/issue/{issue_id}")
        == "https://linear.local/issue/GEN-47"
    )
    with pytest.raises(ValueError, match="placeholder"):
        linear_issue_url("GEN-47", template="https://linear.local/issue/")
    with pytest.raises(ValueError, match="GEN-N format"):
        linear_issue_url("X-1")


def test_pr_body_links_linear_and_lists_criteria() -> None:
    body = pr_body_for("GEN-47", "goal", ("criteria one", "criteria two"))
    assert "**Linear issue:** https://linear.app/genesisnavarra/issue/GEN-47" in body
    assert "- [x] criteria one" in body
    assert "- [x] criteria two" in body
    assert "Human review required" in body
    assert body.startswith("feat(gen-47): ")


def test_agent_prompt_states_sandbox_hard_rules() -> None:
    prompt = build_agent_prompt(
        objective="Do the thing",
        acceptance_criteria=("works", "tested"),
        base_branch="main",
        branch_name="feat/gen-47-thing",
    )
    assert "/workspace" in prompt
    assert "feat/gen-47-thing" in prompt
    assert "main" in prompt
    assert "- works" in prompt
    assert "- tested" in prompt
    assert "no network" in prompt
    assert "never push" in prompt.lower()


def test_pipeline_audit_delivery_id_is_stable_and_composed() -> None:
    built = pipeline_audit_delivery_id("d-1", "GEN-47-v1", "PLANNING")
    assert built == "d-1#GEN-47-v1#PLANNING"
    assert built == pipeline_audit_delivery_id("d-1", "GEN-47-v1", "PLANNING")


@pytest.mark.parametrize(
    ("delivery", "run_key", "phase"),
    [("", "GEN-47-v1", "PLANNING"), ("d-1", " ", "PLANNING"), ("d-1", "GEN-47-v1", "")],
)
def test_pipeline_audit_delivery_id_rejects_blank_parts(
    delivery: str, run_key: str, phase: str
) -> None:
    with pytest.raises(ValueError, match="not be blank"):
        pipeline_audit_delivery_id(delivery, run_key, phase)
