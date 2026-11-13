"""validate-pr holds a ready PR to its Reuse: and Docs: lines.

The rules live in the scaffolded AGENTS.md; this step is what makes them more
than a wish. Each test runs the rendered step's shell, not its text.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from project_init.scaffold import scaffold
from tests.helpers import fallback_preset, fallback_variables

STEP_NAME = "Check reuse and docs lines"


@pytest.fixture
def target(tmp_target: Path) -> Path:
    scaffold(tmp_target, fallback_preset(), fallback_variables())
    return tmp_target


def _workflow(target: Path) -> dict:
    return yaml.safe_load((target / ".github" / "workflows" / "validate-pr.yml").read_text())


def _step(target: Path) -> dict:
    steps = _workflow(target)["jobs"]["pr-format-and-issue"]["steps"]
    return next(s for s in steps if s.get("name") == STEP_NAME)


def _run(target: Path, body: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is needed to run the step")
    return subprocess.run(
        [bash, "-c", _step(target)["run"]],
        env={**os.environ, "PR_BODY": body},
        capture_output=True,
        text=True,
        check=False,
    )


def test_ready_pr_with_both_lines_passes(target: Path) -> None:
    body = "Closes #4\n\nReuse: none\nDocs: n/a\n"
    out = _run(target, body)
    assert out.returncode == 0, out.stdout + out.stderr


def test_crlf_body_from_the_web_editor_passes(target: Path) -> None:
    body = "Closes #4\r\n\r\nReuse: none\r\nDocs: shipped docs, v16.4\r\n"
    assert _run(target, body).returncode == 0


@pytest.mark.parametrize(
    ("body", "named"),
    [
        ("Closes #4\n\nDocs: n/a\n", "Reuse:"),
        ("Closes #4\n\nReuse: none\n", "Docs:"),
        ("Closes #4\n\nReuse:\nDocs:   \n", "Reuse: Docs:"),
        ("Closes #4\n", "Reuse: Docs:"),
        ("", "Reuse: Docs:"),
    ],
)
def test_missing_or_empty_line_fails_and_names_it(target: Path, body: str, named: str) -> None:
    out = _run(target, body)
    assert out.returncode == 1
    assert f"filled in: {named}" in out.stdout


def test_unfilled_pr_template_fails(target: Path) -> None:
    """The shipped template, submitted as-is, must not pass its own check."""
    template = (target / ".github" / "pull_request_template.md").read_text()
    assert _run(target, template).returncode == 1


def test_filled_pr_template_passes(target: Path) -> None:
    template = (target / ".github" / "pull_request_template.md").read_text()
    filled = "\n".join(
        "Reuse: none"
        if line.startswith("Reuse:")
        else "Docs: n/a"
        if line.startswith("Docs:")
        else line
        for line in template.splitlines()
    )
    assert _run(target, filled).returncode == 0


def test_check_skips_drafts_and_reruns_when_ready(target: Path) -> None:
    """A draft opened by start-issue carries only the Closes line."""
    assert _step(target)["if"] == "${{ !github.event.pull_request.draft }}"
    # PyYAML reads the bare `on:` key as boolean True.
    triggers = _workflow(target)[True]["pull_request"]["types"]
    assert "ready_for_review" in triggers


def test_agents_md_points_at_a_guide_that_exists(target: Path) -> None:
    agents = (target / "AGENTS.md").read_text()
    assert "`.agents/docs/guides/reuse-and-docs.md`" in agents
    guide = (target / ".agents" / "docs" / "guides" / "reuse-and-docs.md").read_text()
    assert "## Reuse before you write" in guide
    assert "## Read the docs for the installed version" in guide
    assert "`validate-pr`" in guide  # lifecycle is on in this scaffold
