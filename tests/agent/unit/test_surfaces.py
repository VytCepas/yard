"""PI-366: canonical per-surface config rendering (ADR-017).

Pure-function tests for the surface table and hook renderers in
project_init.surfaces. No MCP rendering exists any more: the scaffold ships no
MCP servers (operator decision 2026-11-26).
"""

from __future__ import annotations

import json

from project_init import surfaces


def test_cursor_hooks_use_camelcase_events_and_adapter():
    cfg = json.loads(surfaces.render_cursor_hooks())
    assert cfg["version"] == 1
    assert "beforeShellExecution" in cfg["hooks"]
    # PI-385: beforeSubmitPrompt dropped (no command; different deny shape).
    assert "beforeSubmitPrompt" not in cfg["hooks"]
    cmd = cfg["hooks"]["beforeShellExecution"][0]["command"]
    assert "admission_agent_adapter.py cursor" in cmd
    # PI-537 #4: resolve from the git root so the hook fires from any subdir.
    assert "git rev-parse --show-toplevel" in cmd


def test_antigravity_hooks_safety_gate_pretooluse():
    cfg = json.loads(surfaces.render_antigravity_hooks())
    assert "safety-gate" in cfg
    assert "PreToolUse" in cfg["safety-gate"]
    cmd = cfg["safety-gate"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "admission_agent_adapter.py antigravity" in cmd
    assert "git rev-parse --show-toplevel" in cmd  # PI-537 #4


def test_antigravity_marked_experimental_cursor_not():
    assert surfaces.SURFACES["antigravity"]["experimental"] is True
    assert surfaces.SURFACES["cursor"]["experimental"] is False


def test_surfaces_render_no_mcp_machinery():
    """The MCP renderers and the per-surface mcp_file keys are gone, not dormant."""
    for name in ("render_mcp_json", "render_mcp_toml", "render_antigravity_mcp", "render_mcp_for"):
        assert not hasattr(surfaces, name), f"{name} resurrected"
    for name, spec in surfaces.SURFACES.items():
        assert "mcp_file" not in spec and "mcp_render" not in spec, name


def test_planned_files_for_selection():
    files = surfaces.planned_files(["claude", "cursor", "antigravity", "vscode", "codex", "amp"])
    assert set(files) == {".cursor/hooks.json", ".agents/hooks.json"}


def test_no_surface_files_for_native_only_selection():
    # Claude only (native .agents/) → nothing generated.
    assert surfaces.planned_files(["claude"]) == {}
