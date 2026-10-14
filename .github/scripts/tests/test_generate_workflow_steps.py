import json
import os
import subprocess

import pytest
import yaml
from conftest import WORKFLOWS, run_step, workflow_step

HOSTILE_TITLE = 'feat: $(touch pwned) `touch pwned2` "quoted" ; echo hi'

# Stub gh: log every call, answer /files with $GH_FILES and anything else with $GH_PR,
# and apply --jq with the real jq the way gh does (raw strings).
GH_STUB = r"""
printf '%s\0' "$@" >> "$RUNNER_TEMP/gh-calls"
printf '\n' >> "$RUNNER_TEMP/gh-calls"
filter=""
prev=""
for arg in "$@"; do
  [ "$prev" = "--jq" ] && filter="$arg"
  prev="$arg"
done
case "$*" in
  *"/files"*) data="$GH_FILES" ;;
  "pr create"*) exit 0 ;;
  *) data="$GH_PR" ;;
esac
if [ -n "$filter" ]; then jq -r "$filter" <<< "$data"; else printf '%s\n' "$data"; fi
"""


def gh_calls(tmp_path):
    raw = (tmp_path / "gh-calls").read_text(encoding="utf-8")
    return [line.split("\0")[:-1] for line in raw.split("\n") if line]


def test_find_added_skills_paginates_filters_and_keeps_title_inert(tmp_path):
    files = [{"filename": f"plugins/new/skills/s{i}/references/r.md", "status": "added"} for i in range(31)]
    files += [
        {"filename": "plugins/new/skills/s1/SKILL.md", "status": "added"},
        {"filename": "plugins/new/skills/s2/SKILL.md", "status": "added"},
        {"filename": "community-plugins/c/skills/g/SKILL.md", "status": "added"},
        {"filename": "plugins/old/skills/o/SKILL.md", "status": "modified"},
        {"filename": "plugins/new/skills/s3/nested/SKILL.md", "status": "added"},
    ]
    env = {"GH_TOKEN": "t", "PR_NUMBER": "125", "REPO": "uw-ssec/rse-plugins",
           "GH_FILES": json.dumps(files), "GH_PR": json.dumps({"head": {"sha": "abc123"}, "title": HOSTILE_TITLE})}
    script = workflow_step("generate-testcases.yml", "Find added SKILL.md files")
    proc, out = run_step(script, tmp_path, env, {"gh": GH_STUB})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out["skills"]) == [
        "plugins/new/skills/s1/SKILL.md", "plugins/new/skills/s2/SKILL.md", "community-plugins/c/skills/g/SKILL.md"]
    assert (out["count"], out["head-sha"]) == ("3", "abc123")
    files_call = next(c for c in gh_calls(tmp_path) if any("/files" in a for a in c))
    assert "--paginate" in files_call
    assert any("per_page=100" in a for a in files_call)
    assert (tmp_path / "pr-title.txt").read_text(encoding="utf-8").strip() == HOSTILE_TITLE
    assert not (tmp_path / "pwned").exists()


@pytest.fixture
def testcases_checkout(tmp_path):
    def git(*args, cwd=tmp_path):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                       env={"HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1", "PATH": os.environ["PATH"]})

    git("init", "--bare", "-b", "main", "origin.git")
    git("clone", "origin.git", "testcases-repo")
    repo = tmp_path / "testcases-repo"
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "--allow-empty", "-m", "init", cwd=repo)
    git("push", "origin", "HEAD:main", cwd=repo)
    generated = tmp_path / "generated-testcases/plugins/new/skills/s1/evals"
    generated.mkdir(parents=True)
    (generated / "001-basic.yaml").write_text("name: x\n", encoding="utf-8")
    (tmp_path / "pr-title.txt").write_text(HOSTILE_TITLE + "\n", encoding="utf-8")
    return tmp_path, git


def push_env():
    return {"GH_TOKEN": "t", "PR_NUMBER": "125", "REPO": "uw-ssec/rse-plugins",
            "TESTCASES_REPO": "uw-ssec/rse-plugins-testcases", "GH_FILES": "[]", "GH_PR": "{}"}


def test_push_uses_title_verbatim_and_opens_pr(testcases_checkout):
    tmp_path, _ = testcases_checkout
    script = workflow_step("generate-testcases.yml", "Push branch and open PR in testcases repo")
    proc, _ = run_step(script, tmp_path, push_env(), {"gh": GH_STUB})
    assert proc.returncode == 0, proc.stderr
    create = next(c for c in gh_calls(tmp_path) if c[:2] == ["pr", "create"])
    assert create[create.index("--title") + 1] == f"testcases: {HOSTILE_TITLE}"
    assert not (tmp_path / "testcases-repo/pwned").exists() and not (tmp_path / "pwned").exists()
    heads = subprocess.run(["git", "ls-remote", "--heads", str(tmp_path / "origin.git")], capture_output=True, text=True).stdout
    assert "refs/heads/auto/testcases-pr-125" in heads


def test_push_refuses_to_overwrite_existing_branch(testcases_checkout):
    tmp_path, git = testcases_checkout
    git("push", "origin", "main:auto/testcases-pr-125", cwd=tmp_path / "testcases-repo")
    script = workflow_step("generate-testcases.yml", "Push branch and open PR in testcases repo")
    proc, _ = run_step(script, tmp_path, push_env(), {"gh": GH_STUB})
    assert proc.returncode == 1
    assert "already exists" in proc.stdout
    calls = gh_calls(tmp_path) if (tmp_path / "gh-calls").exists() else []
    assert not any(c[:2] == ["pr", "create"] for c in calls)


def test_dry_run_upload_keeps_drafts_when_one_skill_fails():
    """generate-testcases.py exits 1 if any skill fails; the drafts of the others must still upload."""
    doc = yaml.safe_load((WORKFLOWS / "generate-testcases.yml").read_text(encoding="utf-8"))
    step = next(s for s in doc["jobs"]["generate"]["steps"] if s.get("name") == "Upload generated testcases (dry run)")
    assert "!cancelled()" in step["if"]
