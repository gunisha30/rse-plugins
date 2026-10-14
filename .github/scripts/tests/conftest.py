import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


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
