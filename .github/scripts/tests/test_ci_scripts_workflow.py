import re
from pathlib import Path

import yaml
from conftest import WORKFLOWS

TESTS = Path(__file__).resolve().parent


def test_ci_scripts_workflow_runs_when_a_tested_workflow_changes():
    """The step tests run run: blocks taken from these workflows, so editing one must re-run the tests."""
    tested = set()
    for test_file in TESTS.glob("test_*.py"):
        tested |= set(re.findall(r'workflow_step\("([^"]+)"', test_file.read_text(encoding="utf-8")))
    assert tested
    doc = yaml.safe_load((WORKFLOWS / "test-ci-scripts.yml").read_text(encoding="utf-8"))
    triggers = doc.get("on", doc.get(True))  # PyYAML reads the bare key `on` as True
    for event in ("pull_request", "push"):
        missing = sorted(w for w in tested if f".github/workflows/{w}" not in triggers[event]["paths"])
        assert not missing, f"{event}.paths misses {missing}"
