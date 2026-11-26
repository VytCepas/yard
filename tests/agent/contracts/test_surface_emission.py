"""PI-366: the scaffold engine emits per-surface config matching the canonical
source (ADR-017). Scaffold-into-temp + drift guard. Hooks only: the scaffold
ships no MCP servers (operator decision 2026-11-26).
"""

from __future__ import annotations

from pathlib import Path

from project_init import surfaces
from project_init.scaffold import load_preset, scaffold
from tests.helpers import make_variables


def _scaffold(target: Path, *, agents: str) -> Path:
    preset = load_preset("obsidian-only")
    # codex overlay carries the guard adapter the GUI hooks invoke.
    preset = {**preset, "layers": [*preset["layers"], "codex"]}
    scaffold(
        target,
        preset,
        make_variables(
            plugin_mode="true",
            no_plugin="",
            agents=agents,
            codex="true",
            multi_agent="true",
        ),
        strict=True,
    )
    return target


def test_selected_surfaces_emit_expected_files(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex,cursor,antigravity,vscode")
    for rel in (".cursor/hooks.json", ".agents/hooks.json"):
        assert (t / rel).is_file(), f"missing generated surface file: {rel}"


def test_emitted_content_matches_canonical_source(tmp_path: Path):
    """Drift guard: every generated file equals what surfaces.planned_files
    would render — so editing a renderer without regenerating can't pass."""
    agents = ["claude", "codex", "cursor", "antigravity", "vscode"]
    t = _scaffold(tmp_path / "p", agents=",".join(agents))
    for rel, content in surfaces.planned_files(agents).items():
        assert (t / rel).read_text() == content, f"{rel} drifted from canonical source"


def test_no_emission_for_native_only(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude")
    for rel in (".cursor/hooks.json", ".agents/hooks.json"):
        assert not (t / rel).exists(), f"unexpected file for native-only scaffold: {rel}"


def test_rescaffold_surfaces_changes_as_new_sibling(tmp_path: Path):
    """A re-scaffold must neither clobber a user's edit nor silently leave a
    stale config — the change lands as a .new sibling (PI-366 review)."""
    t = _scaffold(tmp_path / "p", agents="claude,cursor")
    hooks = t / ".cursor/hooks.json"
    hooks.write_text('{"version": 1, "hooks": {"mine": []}}\n')
    _scaffold(t, agents="claude,cursor")
    # Original preserved …
    assert "mine" in hooks.read_text(), "re-scaffold clobbered a user-edited file"
    # … and the canonical render is surfaced for review.
    sibling = t / ".cursor/hooks.json.new"
    assert sibling.is_file()
    assert "beforeShellExecution" in sibling.read_text()


def test_rescaffold_no_sibling_when_unchanged(tmp_path: Path):
    """Re-running with the same selection is a no-op (no spurious .new)."""
    t = _scaffold(tmp_path / "p", agents="claude,cursor")
    _scaffold(t, agents="claude,cursor")
    assert not (t / ".cursor/hooks.json.new").exists()


def test_vscode_agent_generates_no_vscode_dir(tmp_path: Path):
    """vscode as an agent surface emits nothing (it was MCP-only)."""
    t = _scaffold(tmp_path / "p", agents="claude,vscode")
    assert not (t / ".vscode/mcp.json").exists()


def test_guard_adapter_has_gui_dialects(tmp_path: Path):
    t = _scaffold(tmp_path / "p", agents="claude,codex,cursor,antigravity")
    adapter = (t / ".agents/hooks/admission_agent_adapter.py").read_text()
    assert 'dialect == "cursor"' in adapter
    assert 'dialect == "antigravity"' in adapter
