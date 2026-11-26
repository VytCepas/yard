"""Per-surface agent-config generation (ADR-017, PI-366).

One canonical source — the surface table here plus the shared guard adapter —
rendered outward to each non-CLI
agent surface's native files. Pure, deterministic functions only (ADR-001: no
LLM, no I/O in this module); the scaffold engine writes the rendered strings.

Confidence (from the #365 spike, `docs/development/non-cli-surface-matrix.md`):
- **Hooks** file paths + event names are validated, but the exact blocking
  stdin/stdout contract for Cursor/Antigravity was not live-verified, so the
  emitted hooks are **best-effort and fail-open** — git/CI remain the real
  enforcement boundary (ADR-007). Antigravity is flagged experimental.

Claude Code (CLI + VS Code extension) reads its config from `.claude/`, which the
scaffolder keeps as a delete-aware mirror of the canonical `.agents/` tree (plain
files, portable across OSes — see `_generate_claude_projection`), so it needs no
per-surface emission here; Codex/Gemini already have overlays. This module adds
the GUI hook configs (Cursor, Antigravity). It renders no MCP config: the
scaffold ships no MCP servers (operator decision 2026-11-26).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# The shared, fail-open guard adapter (reused across surfaces); the scaffolder
# already ships it at this path for codex/antigravity.
def _guard_command(surface: str) -> str:
    """Command-guard invocation that resolves from the git repo root (PI-537).

    Agent surfaces run hooks in the session's working directory, which may be a
    subdirectory of the project; a bare relative ``.agents/hooks/python-resolve.sh …`` then
    exits 127 from there and fails open. Wrap it so it ``cd``s to the git toplevel
    first (falling back to the current dir outside a repo — the old behavior),
    then ``exec``s the guard so stdin (the tool-call JSON) is inherited.
    """
    return (
        'sh -c \'cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && '
        f"exec .agents/hooks/python-resolve.sh .agents/hooks/admission_agent_adapter.py {surface}'"
    )


# --- canonical hook rendering (best-effort, fail-open) -----------------------


def render_cursor_hooks() -> str:
    """Render `.cursor/hooks.json` (version 1).

    Wires the shared command guard onto Cursor's ``beforeShellExecution`` event
    (top-level ``command`` stdin → ``{"permission": "deny", ...}`` stdout; PI-385,
    confirmed from docs). No ``beforeSubmitPrompt`` hook: that event carries no
    shell command and uses a different deny shape (``{"continue": false}``), so the
    command guard can't act on it. Fail-open (no ``failClosed``) — git/CI is the
    real boundary (ADR-007).
    """
    config = {
        "version": 1,
        "hooks": {
            "beforeShellExecution": [{"command": _guard_command("cursor"), "type": "command"}],
        },
    }
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def render_antigravity_hooks() -> str:
    """Render `.agents/hooks.json` for Antigravity's ``safety-gate`` model.

    PI-385: the ``PreToolUse`` path + stdout deny shape (``{"decision":"deny"}``)
    and the stdin command location (``toolCall.args.CommandLine``) are confirmed
    from Google's migration docs, and the adapter parses/emits them. Still flagged
    ``experimental`` because the official rendered docs were un-fetchable and this
    isn't verified against a live ``agy`` binary; adapter stays fail-open.
    """
    config = {
        "safety-gate": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": _guard_command("antigravity")}],
                }
            ]
        }
    }
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


# --- the surface table -------------------------------------------------------
# One entry per surface that needs project-scoped hook emission. Claude
# (CLI/ext), Codex (overlay), Amp and Junie (template layers only) are intentionally
# absent. Antigravity also ships its skills via a template layer (PI-386).
# Each entry declares what files to write; the scaffold engine consumes this.
# (ADR-017 §2.)

SURFACES: dict[str, dict[str, Any]] = {
    "cursor": {
        "label": "Cursor",
        "experimental": False,
        "hooks_file": ".cursor/hooks.json",
        "hooks_render": render_cursor_hooks,
        # skills cross-read from .agents/skills — no emission needed.
    },
    "antigravity": {
        "label": "Antigravity",
        "experimental": True,
        "hooks_file": ".agents/hooks.json",
        "hooks_render": render_antigravity_hooks,
        # skills come from the antigravity template layer's .agents/skills.
    },
}


def surface_files(surface: str) -> dict[str, str]:
    """All files to write for a selected *surface*: {relpath: content}."""
    spec = SURFACES[surface]
    files: dict[str, str] = {}
    if spec.get("hooks_file") and spec.get("hooks_render"):
        files[spec["hooks_file"]] = spec["hooks_render"]()
    return files


def planned_files(agents: list[str]) -> dict[str, str]:
    """Map a selection to ``{relpath: content}``.

    The single place that maps selected *agents* to files, so the scaffold step
    and the drift contract test share one source of truth.
    """
    files: dict[str, str] = {}
    for surface in agents:
        if surface in SURFACES:
            files.update(surface_files(surface))
    return files


def emit(
    target: Path,
    *,
    agents: list[str],
    conflicts: list[tuple[Path, Path]] | None = None,
) -> list[Path]:
    """Write the per-surface config files into *target*.

    Three cases per file (mirrors the engine's PI-179 protection so a
    re-scaffold neither clobbers a user's edits nor silently leaves a stale
    server list):

    - absent → write it;
    - present and identical to the fresh render → no-op (already current);
    - present but different → never overwrite; write a ``.new`` sibling and, when
      a *conflicts* list is given, record ``(original, sibling)`` so ``upgrade``
      reports it. (We can't tell a stale prior render from a user edit without
      storing the previous render, so the change is always surfaced for review.)

    Returns the relative paths written (originals and/or siblings).
    """
    from project_init.scaffold import _new_sibling

    written: list[Path] = []
    for rel, content in planned_files(agents).items():
        dest = target / rel
        encoded = content.encode("utf-8")
        # Compare bytes, not decoded text: a non-UTF-8 existing file must not
        # crash the scaffold (read_text would raise UnicodeDecodeError), and a
        # CRLF file must register as *different* from the LF render rather than
        # read-normalize to "identical" and silently drift (PI-535).
        if dest.exists() and dest.read_bytes() == encoded:
            continue
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
            written.append(Path(rel))
            continue
        # Exists and differs — surface a .new sibling, never clobber.
        sibling = _new_sibling(dest, encoded)
        sibling.write_text(content, encoding="utf-8", newline="\n")
        rec = Path(rel).parent / sibling.name
        written.append(rec)
        if conflicts is not None:
            conflicts.append((Path(rel), rec))
    return written
