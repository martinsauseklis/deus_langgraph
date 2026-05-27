"""Shell tool execution tests — no LLM required.

Verifies the tool works correctly and documents known security behaviour.
  make e2e-tools
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from langchain_community.tools import ShellTool


@pytest.fixture(scope="module")
def shell():
    return ShellTool()


@pytest.fixture
def tmp_workspace(tmp_path):
    """A disposable directory that acts as a workspace root."""
    return tmp_path


# ── Basic execution ────────────────────────────────────────────────────────────


def test_shell_echo(shell):
    result = shell.run({"commands": "echo hello"})
    assert "hello" in result


def test_shell_exit_code_success(shell):
    result = shell.run({"commands": "true"})
    # ShellTool returns stdout; zero-exit with no output is fine
    assert result is not None


def test_shell_exit_code_failure_captured(shell):
    result = shell.run({"commands": "false"})
    # ShellTool with handle_tool_errors captures the error
    assert result is not None


def test_shell_multiline_output(shell):
    result = shell.run({"commands": "printf 'line1\\nline2\\nline3'"})
    assert "line1" in result and "line3" in result


def test_shell_creates_file(shell, tmp_workspace):
    target = tmp_workspace / "out.txt"
    shell.run({"commands": f"echo written > {target}"})
    assert target.exists()
    assert "written" in target.read_text()


def test_shell_reads_file(shell, tmp_workspace):
    f = tmp_workspace / "input.txt"
    f.write_text("hello from file")
    result = shell.run({"commands": f"cat {f}"})
    assert "hello from file" in result


# ── Security documentation ─────────────────────────────────────────────────────
# These tests document known security properties rather than assert safety.
# They are marked xfail so CI passes while making the risks explicit.


@pytest.mark.xfail(
    reason="KNOWN SECURITY ISSUE: ShellTool has no sandbox — it can read env vars including secrets.",
    strict=False,
)
def test_shell_cannot_read_env_vars(shell):
    """DOCUMENTS: The agent can read ANTHROPIC_API_KEY via the shell tool."""
    result = shell.run({"commands": "echo $ANTHROPIC_API_KEY"})
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    # This assertion will PASS (xfail strict=False), confirming the leak exists.
    assert api_key and api_key in result


@pytest.mark.xfail(
    reason="KNOWN SECURITY ISSUE: ShellTool has no chroot — it can walk outside WORKSPACE_DIR.",
    strict=False,
)
def test_shell_cannot_escape_workspace(shell, tmp_workspace):
    """DOCUMENTS: The agent can cd .. to leave its designated workspace."""
    result = shell.run({"commands": f"cd {tmp_workspace} && cd .. && pwd"})
    # If the parent dir appears in output, the escape worked — this will xfail.
    assert str(tmp_workspace.parent) in result


@pytest.mark.xfail(
    reason="KNOWN SECURITY ISSUE: ShellTool can read files outside WORKSPACE_DIR.",
    strict=False,
)
def test_shell_cannot_read_etc_passwd(shell):
    """DOCUMENTS: The agent can read /etc/passwd with no restriction."""
    result = shell.run({"commands": "cat /etc/passwd"})
    assert "root" in result
