"""The scaffold ships NO third-party MCP servers (operator decision 2026-11-26).

Why: the vendoring standard refuses MCP servers referenced unpinned (@latest) or
run resident, `@playwright/mcp` by name; browser automation is a pinned CLI.
These tests fail if context7 or @playwright/mcp reappear in anything a scaffold
renders, in a wizard prompt, or as a silently accepted flag.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from project_init.__main__ import main

# What must never reach a scaffolded project again. "playwright" alone is not
# listed: the vendored naming registry legitimately carries unrelated rows for it.
_BANNED = ("context7", "@playwright/mcp", "@upstash")
_MCP_CONFIG_FILES = (
    ".mcp.json",
    ".vscode/mcp.json",
    ".cursor/mcp.json",
    ".codex/config.toml",
    ".agents/mcp_config.json",
    ".amp/settings.json",
    ".junie/mcp/mcp.json",
)
_ALL_AGENTS = "claude,codex,ollama,cursor,antigravity,vscode,amp,junie"


def _args(target: Path, *extra: str, language: str = "python") -> list[str]:
    return [
        str(target),
        "--non-interactive",
        "--preset",
        "obsidian-only",
        "--name",
        "mcp-test",
        "--description",
        "test",
        "--language",
        language,
        *extra,
    ]


def _offenders(root: Path) -> list[str]:
    hits: list[str] = []
    for f in sorted(p for p in root.rglob("*") if p.is_file() and ".git/" not in p.as_posix()):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for word in _BANNED:
            if word in text.lower():
                hits.append(f"{f.relative_to(root)}: {word}")
    return hits


@pytest.mark.parametrize("language", ["python", "node", "go", "rust", "none"])
def test_scaffold_renders_no_banned_mcp_server(tmp_path: Path, language: str):
    """Every toolchain, every agent surface, governance on: nothing banned renders."""
    target = tmp_path / "p"
    rc = main(
        _args(
            target,
            "--agents",
            _ALL_AGENTS,
            "--governance",
            "--no-plugin",
            language=language,
        )
    )
    assert rc == 0
    assert _offenders(target) == []
    for rel in _MCP_CONFIG_FILES:
        assert not (target / rel).exists(), f"MCP config rendered: {rel}"
    assert "installed: []" in (target / ".agents" / "config.yaml").read_text()


def test_mcp_decision_record_states_the_position(tmp_path: Path):
    target = tmp_path / "p"
    assert main(_args(target)) == 0
    adr = (target / ".agents" / "docs" / "decisions" / "mcp-choices.md").read_text()
    assert "No third-party MCP servers ship" in adr
    assert "context7" not in adr.lower()


def test_catalog_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("project_init.mcps")


@pytest.mark.parametrize(
    "flag",
    [["--mcps", "context7"], ["--mcps", ""], ["--browser"], ["--mcps", "context7", "--browser"]],
)
def test_retired_flags_fail_loudly_and_create_nothing(tmp_path: Path, capsys, flag: list[str]):
    """Removed flags must error naming the decision — never be silently accepted."""
    target = tmp_path / "should-not-exist"
    with pytest.raises(SystemExit) as exc:
        main(_args(target, *flag))
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "removed" in err and "2026-11-26" in err and "MCP" in err
    assert not target.exists()


def test_retired_flags_fail_in_interactive_mode_too(tmp_path: Path, capsys):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "p"), "--name", "x", "--mcps", "context7"])
    assert "2026-11-26" in capsys.readouterr().err


def test_retired_flags_are_hidden_from_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "--mcps" not in out and "--browser" not in out


def test_wizard_offers_no_mcp_or_browser_prompt():
    import project_init.wizard_prompts as wiz

    for name in (
        "_choose_mcps_interactive",
        "_choose_browser_interactive",
        "_gather_mcps_interactive",
    ):
        assert not hasattr(wiz, name), f"{name} resurrected"
    groups = " ".join(f"{k} {t} {d}" for k, t, d in wiz._GATEWAY_GROUPS).lower()
    assert "mcp" not in groups and "playwright" not in groups and "browser" not in groups


def test_unknown_preset_does_not_create_target_dir(tmp_path: Path):
    """A typo in --preset must fail BEFORE the target directory is created."""
    target = tmp_path / "should-not-exist"
    with pytest.raises(SystemExit):
        main(
            [
                str(target),
                "--non-interactive",
                "--preset",
                "definitely-not-a-real-preset",
                "--name",
                "x",
                "--description",
                "x",
            ]
        )
    assert not target.exists(), f"target dir {target} was created despite invalid preset"


def test_db_flag_removed():
    """PI-387: --db is gone; passing it must be a CLI error."""
    with pytest.raises(SystemExit):
        main(_args(Path("x"), "--db", "postgres"))


def _legacy_mcp_project(tmp_path: Path) -> tuple[Path, Path]:
    """A project scaffolded when context7/playwright still shipped: a generated
    .mcp.json recorded in the manifest, and `mcps.installed` naming both."""
    import hashlib
    import json
    import re

    target = tmp_path / "p"
    assert main(_args(target)) == 0
    legacy = '{"mcpServers": {"context7": {"command": "npx", "args": ["@upstash/context7-mcp"]}, "playwright": {"command": "npx", "args": ["@playwright/mcp"]}}}\n'
    mcp = target / ".mcp.json"
    mcp.write_text(legacy)
    config = target / ".agents" / "config.yaml"
    text = config.read_text().replace("installed: []", 'installed: ["context7", "playwright"]')
    # A legacy scaffold record carries the selection in its recorded variables.
    text = text.replace('"installed_mcps": "none"', '"installed_mcps": "context7, playwright"')
    text = text.replace('"installed_mcps_yaml": "[]"', '"installed_mcps_yaml": "[\\"context7\\"]"')
    assert "context7, playwright" in text
    m = re.search(r"(?m)^(\s*manifest:\s*)(\{.*\})\s*$", text)
    assert m, "scaffold record manifest line missing"
    manifest = json.loads(m.group(2))
    manifest[".mcp.json"] = hashlib.sha256(legacy.encode()).hexdigest()
    config.write_text(
        text[: m.start()] + m.group(1) + json.dumps(manifest, sort_keys=True) + text[m.end() :]
    )
    return target, mcp


def test_upgrade_of_a_legacy_mcp_project_leaves_the_files_and_says_so(tmp_path: Path, capsys):
    """Upgrade never crashes on recorded context7/playwright. It does not remove
    or rewrite the generated MCP files: they are reported as no longer rendered
    (left in place), and a note names the retired servers."""
    target, mcp = _legacy_mcp_project(tmp_path)
    before = mcp.read_bytes()
    capsys.readouterr()

    assert main(["upgrade", str(target), "--apply"]) == 0
    cap = capsys.readouterr()

    assert mcp.read_bytes() == before, "upgrade must not touch the generated MCP file"
    assert ".mcp.json" in cap.out and "no longer rendered (left in place)" in cap.out
    assert "no longer ships" in cap.err and "context7" in cap.err
    # Nothing new is rendered for the retired servers.
    project_doc = (target / ".agents" / "project-init.md").read_text()
    assert "context7" not in project_doc and "playwright" not in project_doc
    assert not (target / ".mcp.json.new").exists()


def test_rescaffold_of_a_legacy_mcp_project_does_not_crash_or_touch_mcp_files(tmp_path: Path):
    target, mcp = _legacy_mcp_project(tmp_path)
    before = mcp.read_bytes()
    assert main(_args(target)) == 0
    assert mcp.read_bytes() == before
    assert not (target / ".mcp.json.new").exists()
