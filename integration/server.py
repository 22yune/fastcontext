#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fastcontext")


def find_git_root(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).resolve()
    except Exception:
        pass

    return path.resolve()


@mcp.tool()
def fastcontext_search(
    query: str,
    repo_path: str = "",
    max_turns: int = 3,
) -> str:
    """
    Search a local code repository with FastContext.

    Use this tool before broad manual exploration when the user asks to find,
    locate, inspect, or understand code, files, routes, configs, packages,
    APIs, business logic, parsing logic, auth logic, database logic, or
    bug-related code.

    Input:
    - query: concise natural-language search query derived from the user request.
    - repo_path: repository root. If omitted, use the current workspace/repo root.
    - max_turns: search depth, default 3.

    Output:
    - exact file paths and line ranges as evidence.

    Rules:
    - Read returned files before editing.
    - This tool is read-only and must not modify files.
    """
    if not query.strip():
        return "ERROR: query is empty."

    if repo_path.strip():
        repo = Path(repo_path).expanduser().resolve()
    else:
        repo = find_git_root(Path.cwd())

    if not repo.exists() or not repo.is_dir():
        return f"ERROR: repo_path does not exist or is not a directory: {repo}"

    max_turns = max(1, min(int(max_turns), 8))

    env = os.environ.copy()
    env["PATH"] = (
        "/opt/homebrew/bin:"
        "/usr/local/bin:"
        f"{Path.home()}/bin:"
        f"{Path.home()}/.local/bin:"
        + env.get("PATH", "")
    )

    cmd = [
        "fc-find",
        "-m",
        str(max_turns),
        query,
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
    except FileNotFoundError:
        return (
            "ERROR: fc-find command not found. "
            "Run `which fc-find` in terminal and make sure it is in PATH."
        )
    except subprocess.TimeoutExpired:
        return "ERROR: fc-find timed out after 180 seconds."

    if result.returncode != 0:
        return (
            "ERROR: fc-find failed.\n\n"
            f"Repo: {repo}\n\n"
            f"STDERR:\n{result.stderr}\n\n"
            f"STDOUT:\n{result.stdout}"
        )

    return result.stdout.strip()


if __name__ == "__main__":
    mcp.run()