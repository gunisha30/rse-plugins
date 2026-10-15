import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = "plugins/demo/skills/demo-skill/SKILL.md"
GOOD_CASE = "name: Demo\nprompt: |\n  do the thing\ncriteria:\n  - does it\nexpect_skill: true\ntimeout: 600\n"


@pytest.fixture
def pr_root(tmp_path):
    root = tmp_path / "pr-content"
    skill = root / SKILL
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo-skill\n---\n# Demo\n", encoding="utf-8")
    return root


def test_read_skill_returns_regular_file(gen, pr_root):
    assert gen.read_skill(pr_root, SKILL).startswith("---\nname: demo-skill")


def test_read_skill_refuses_symlink(gen, pr_root, tmp_path):
    secret = tmp_path / "environ"
    secret.write_text("LITELLM_API_KEY=sk-secret", encoding="utf-8")
    link = pr_root / "plugins/evil/skills/evil/SKILL.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(secret)
    with pytest.raises(ValueError, match="symlink"):
        gen.read_skill(pr_root, "plugins/evil/skills/evil/SKILL.md")


def test_read_skill_refuses_symlinked_parent_escaping_root(gen, pr_root, tmp_path):
    outside = tmp_path / "outside" / "skills" / "x"
    outside.mkdir(parents=True)
    (outside / "SKILL.md").write_text("secret", encoding="utf-8")
    (pr_root / "plugins" / "escape").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="outside"):
        gen.read_skill(pr_root, "plugins/escape/skills/x/SKILL.md")


@pytest.mark.parametrize("bad", ["../SKILL.md", "plugins/demo/SKILL.md", "/etc/passwd", "plugins/a/skills/b/c/SKILL.md"])
def test_read_skill_refuses_non_skill_paths(gen, pr_root, bad):
    with pytest.raises(ValueError, match="not a plugins"):
        gen.read_skill(pr_root, bad)


@pytest.mark.parametrize("raw", ["001-basic-usage.yaml", "006-negative-trigger.yaml"])
def test_safe_filename_keeps_well_formed_names(gen, raw):
    assert gen.safe_filename(raw, 1) == (raw, None)


@pytest.mark.parametrize("raw", ["../../.github/workflows/pwn.yaml", "/tmp/x.yaml", "sub/001-a.yaml", "001-a.yml", "001-A.yaml", None, 7])
def test_safe_filename_replaces_unsafe_names(gen, raw):
    name, warning = gen.safe_filename(raw, 3)
    assert name == "003-case.yaml"
    assert "unsafe filename" in warning


def test_write_testcases_never_leaves_evals_dir(gen, tmp_path):
    evals = tmp_path / "out" / "plugins/demo/skills/demo-skill/evals"
    cases = [
        {"filename": "001-ok.yaml", "content": GOOD_CASE},
        {"filename": "../../../../escape.yaml", "content": GOOD_CASE},
        "not-an-object",
        {"filename": "004-bad-yaml.yaml", "content": "name: [unclosed"},
    ]
    warnings = gen.write_testcases(evals, cases)
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.yaml"))
    assert written == [
        "out/plugins/demo/skills/demo-skill/evals/001-ok.yaml",
        "out/plugins/demo/skills/demo-skill/evals/002-case.yaml",
        "out/plugins/demo/skills/demo-skill/evals/004-bad-yaml.yaml",
    ]
    assert any("unsafe filename" in w for w in warnings)
    assert any("case 3: skipped" in w for w in warnings)
    assert any(w.startswith("004-bad-yaml.yaml:") and "written anyway" in w for w in warnings)


def test_extract_json_array_tolerates_fences(gen):
    text = 'Here you go:\n```json\n[{"filename": "001-a.yaml", "content": "x"}]\n```'
    assert gen.extract_json_array(text) == [{"filename": "001-a.yaml", "content": "x"}]


def test_main_keeps_warnings_out_of_output_dir(tmp_path, pr_root):
    """The warnings file must not land in the tree that gets copied into the testcases repo."""
    stub = tmp_path / "stub"
    (stub / "openai").mkdir(parents=True)
    (stub / "openai" / "__init__.py").write_text(
        "import json\n"
        "class _Msg:\n"
        "    content = json.dumps([{'filename': '../x.yaml', 'content': 'name: [bad'}])\n"
        "class _Choice:\n"
        "    message = _Msg()\n"
        "class _Resp:\n"
        "    choices = [_Choice()]\n"
        "class _Completions:\n"
        "    def create(self, **kwargs):\n"
        "        return _Resp()\n"
        "class _Chat:\n"
        "    completions = _Completions()\n"
        "class OpenAI:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.chat = _Chat()\n",
        encoding="utf-8",
    )
    out = tmp_path / "generated"
    warnings_file = tmp_path / "warnings.txt"
    script = Path(__file__).resolve().parents[1] / "generate-testcases.py"
    env = {**os.environ, "PYTHONPATH": str(stub), "LITELLM_API_KEY": "k", "LITELLM_PROXY_URL": "http://proxy"}
    subprocess.run(
        [sys.executable, str(script), "--skills", json.dumps([SKILL]), "--skill-root", str(pr_root),
         "--output-dir", str(out), "--warnings-file", str(warnings_file)],
        check=True, env=env,
    )
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "plugins/demo/skills/demo-skill/evals/001-case.yaml"
    ]
    assert "unsafe filename" in warnings_file.read_text(encoding="utf-8")
