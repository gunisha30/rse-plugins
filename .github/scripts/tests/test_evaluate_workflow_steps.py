import json

import pytest
from conftest import run_step, workflow_step

MODELS_JSON = json.dumps({"data": [{"id": "gpt-5.4-mini"}, {"id": "anthropic/claude-sonnet-4-6"}]})
CURL_STUB = 'printf "%s" "$MODELS_JSON"\n'


@pytest.mark.parametrize(
    "model, expected",
    [("gpt-5.4-mini", "gpt-5.4-mini"), ("anthropic/claude-sonnet-4-6", "anthropic-claude-sonnet-4-6"),
     ("bedrock/us.anthropic.claude-v1:0", "bedrock-us.anthropic.claude-v1-0")],
)
def test_model_ids_become_valid_artifact_names(tmp_path, model, expected):
    script = workflow_step("evaluate-per-model.yml", "Derive names")
    proc, out = run_step(script, tmp_path, {"SKILL_PATH": "plugins/p/skills/python-testing", "MODEL": model})
    assert proc.returncode == 0, proc.stderr
    assert out == {"skill": "python-testing", "model": expected}


def test_models_filter_keeps_requested_models(tmp_path):
    script = workflow_step("evaluate-all-skills.yml", "Fetch available models from LiteLLM proxy")
    env = {"LITELLM_API_KEY": "k", "LITELLM_PROXY_URL": "https://proxy/", "MODELS_JSON": MODELS_JSON,
           "MODELS_FILTER": " gpt-5.4-mini "}
    proc, out = run_step(script, tmp_path, env, {"curl": CURL_STUB})
    assert proc.returncode == 0, proc.stderr
    assert (json.loads(out["models"]), out["count"]) == (["gpt-5.4-mini"], "1")


def test_models_filter_typo_fails_and_lists_available(tmp_path):
    script = workflow_step("evaluate-all-skills.yml", "Fetch available models from LiteLLM proxy")
    env = {"LITELLM_API_KEY": "k", "LITELLM_PROXY_URL": "https://proxy", "MODELS_JSON": MODELS_JSON,
           "MODELS_FILTER": "gpt-5.4-mni"}
    proc, _ = run_step(script, tmp_path, env, {"curl": CURL_STUB})
    assert proc.returncode == 1
    assert "Unknown model(s): gpt-5.4-mni" in proc.stdout
    assert "gpt-5.4-mini" in proc.stdout


@pytest.fixture
def skills_tree(tmp_path):
    for skill in ("plugins/a/skills/python-testing", "plugins/b/skills/podman", "community-plugins/c/skills/gaia"):
        (tmp_path / skill).mkdir(parents=True)
        (tmp_path / skill / "SKILL.md").write_text("---\n", encoding="utf-8")
    (tmp_path / ".testcases/plugins/a/skills/python-testing/evals").mkdir(parents=True)
    return tmp_path


def test_skills_filter_matches_names_and_paths(skills_tree):
    script = workflow_step("evaluate-all-skills.yml", "Discover skills")
    env = {"SKILLS_FILTER": "python-testing, community-plugins/c/skills/gaia", "TEST_DIR": ".testcases"}
    proc, out = run_step(script, skills_tree, env)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out["all-skills"]) == ["community-plugins/c/skills/gaia", "plugins/a/skills/python-testing"]
    assert json.loads(out["eval-skills"]) == ["plugins/a/skills/python-testing"]
    assert (out["count"], out["eval-count"]) == ("2", "1")


def test_empty_skills_filter_selects_everything(skills_tree):
    script = workflow_step("evaluate-all-skills.yml", "Discover skills")
    proc, out = run_step(script, skills_tree, {"SKILLS_FILTER": "", "TEST_DIR": ".testcases"})
    assert proc.returncode == 0, proc.stderr
    assert out["count"] == "3"


def test_skills_filter_typo_fails_loudly(skills_tree):
    script = workflow_step("evaluate-all-skills.yml", "Discover skills")
    proc, _ = run_step(script, skills_tree, {"SKILLS_FILTER": "python-tsting", "TEST_DIR": ".testcases"})
    assert proc.returncode == 1
    assert "No skill matches the skills input: python-tsting" in proc.stdout
