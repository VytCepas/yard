"""Release-age hold: every scaffolded resolver waits 7 days for a new version.

A lockfile pins whatever was newest when it was written, poisoned or not, so the
hold lives in the resolver configs the scaffold ships, and Renovate asks for
nothing the resolver would refuse.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

SEVEN_DAYS_S = 7 * 24 * 60 * 60


def _scaffold_language(target: Path, language: str) -> Path:
    flags = {lang: "true" if lang == language else "" for lang in ("python", "node", "go", "rust")}
    scaffold(target, fallback_preset(), fallback_variables(language=language, **flags))
    return target


def test_uv_holds_new_versions_for_seven_days(tmp_target: Path) -> None:
    target = _scaffold_language(tmp_target, "python")
    config = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["uv"]["exclude-newer"] == "7 days"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_uv_records_the_hold_in_the_lock(tmp_target: Path) -> None:
    """The text is not the behaviour: uv must parse the value and lock with it."""
    target = _scaffold_language(tmp_target, "python")
    pyproject = target / "pyproject.toml"
    config = pyproject.read_text(encoding="utf-8")
    # Offline lock needs no registry: drop the dev group, keep the [tool.uv] hold.
    start = config.index("[dependency-groups]")
    end = config.index("]\n", config.index("dev = [")) + 2
    pyproject.write_text(config[:start] + config[end:], encoding="utf-8")
    # conftest moves UV_PYTHON_INSTALL_DIR, so a runner with only a managed Python finds none.
    cmd = ["uv", "lock", "--offline", "--python", sys.executable]
    subprocess.run(cmd, cwd=target, check=True, capture_output=True)
    lock = (target / "uv.lock").read_text(encoding="utf-8")
    assert 'exclude-newer-span = "P7D"' in lock


def test_bun_holds_new_versions_for_seven_days(tmp_target: Path) -> None:
    target = _scaffold_language(tmp_target, "node")
    config = tomllib.loads((target / "bunfig.toml").read_text(encoding="utf-8"))
    assert config["install"]["minimumReleaseAge"] == SEVEN_DAYS_S


def test_renovate_waits_as_long_as_the_resolvers(tmp_target: Path) -> None:
    target = _scaffold_language(tmp_target, "python")
    config = json.loads((target / "renovate.json").read_text(encoding="utf-8"))
    assert config["minimumReleaseAge"] == "7 days"
