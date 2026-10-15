import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
WORKFLOWS = SCRIPTS.parent / "workflows"


def workflow_step(workflow: str, name: str) -> str:
    """Return the `run:` script of the step called name in .github/workflows/<workflow>."""
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == name:
                return step["run"]
    raise KeyError(f"{workflow}: no step named {name!r}")


def run_step(script: str, cwd: Path, env: dict[str, str], stubs: dict[str, str] | None = None):
    """Run a workflow step the way the runner does (`bash -e`), with stub commands first on PATH.

    Returns (completed_process, outputs) where outputs holds the key=value lines the step
    appended to $GITHUB_OUTPUT.
    """
    bin_dir = cwd / ".stub-bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (stubs or {}).items():
        stub = bin_dir / name
        stub.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    output_file = cwd / ".github-output"
    output_file.write_text("", encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(cwd),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GITHUB_OUTPUT": str(output_file),
        "RUNNER_TEMP": str(cwd),
        **env,
    }
    proc = subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=full_env, capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in output_file.read_text(encoding="utf-8").splitlines() if "=" in line)
    return proc, outputs


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def gen():
    return _load("generate-testcases")


@pytest.fixture(scope="session")
def record():
    return _load("tessl-review-record")
