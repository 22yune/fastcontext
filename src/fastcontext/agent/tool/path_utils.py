from __future__ import annotations

import os
from pathlib import Path


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def normalize_workspace_path(value: str | None, cwd: str) -> str | None:
    """
    Normalize model-generated file/directory paths to stay inside workspace.

    Handles common LLM mistakes:
    - "/src/foo.py" should mean "<cwd>/src/foo.py"
    - "/RuoYi-Vue3" should mean "<cwd>/RuoYi-Vue3"
    - "RuoYi-Vue3" should mean "<cwd>/RuoYi-Vue3"
    - real absolute paths inside cwd are preserved

    It does not silently allow paths outside cwd.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return raw

    cwd_path = Path(cwd).expanduser().resolve()

    # Expand "~" first.
    p = Path(raw).expanduser()

    # Case 1: absolute path.
    if p.is_absolute():
        resolved = p.resolve(strict=False)

        # Already inside workspace.
        if _is_relative_to(resolved, cwd_path):
            return resolved.as_posix()

        # Common model mistake:
        # "/RuoYi-Vue3/src" => "<cwd>/RuoYi-Vue3/src"
        repaired = (cwd_path / raw.lstrip("/")).resolve(strict=False)
        return repaired.as_posix()

    # Case 2: relative path.
    return (cwd_path / raw).resolve(strict=False).as_posix()


def normalize_glob_pattern(pattern: str | None, cwd: str) -> str | None:
    """
    Normalize glob patterns passed to rg --glob.

    Examples:
    - "/RuoYi-Vue3/**/*.java" -> "RuoYi-Vue3/**/*.java"
    - "<cwd>/RuoYi-Vue3/**/*.java" -> "RuoYi-Vue3/**/*.java"
    - "**/*.java" -> "**/*.java"
    """
    if pattern is None:
        return None

    raw = str(pattern).strip()
    if raw == "":
        return raw

    cwd_path = Path(cwd).expanduser().resolve()
    cwd_prefix = cwd_path.as_posix().rstrip("/") + "/"

    if raw.startswith(cwd_prefix):
        return os.path.relpath(raw, cwd_path)

    if raw.startswith("/") and not raw.startswith(cwd_prefix):
        return raw.lstrip("/")

    return raw


def ensure_within_workspace(path: str, cwd: str) -> tuple[bool, str]:
    cwd_path = Path(cwd).expanduser().resolve()
    target = Path(path).expanduser().resolve(strict=False)
    if _is_relative_to(target, cwd_path):
        return True, target.as_posix()
    return False, target.as_posix()
