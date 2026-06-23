import json
import subprocess
from pathlib import Path

from .tool import Tool
from .path_utils import normalize_workspace_path, normalize_glob_pattern, ensure_within_workspace

def run(directory: str, pattern: str, cwd: str) -> str:
    command = ["rg", "--files", directory, "--glob", pattern]
    timeout = 10  # seconds
    try:
        output = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"Tool `Glob` timed out after {timeout}s."
    if output.returncode == 0:
        return output.stdout if isinstance(output.stdout, str) else output.stdout.decode("utf-8")
    else:
        return output.stderr if isinstance(output.stderr, str) else output.stderr.decode("utf-8")


class GlobTool(Tool):
    name = "Glob"
    description: str = Tool.load_desc(Path(__file__).parent / "glob.md")
    parameters = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "The absolute path of the directory to search in. If not provided, the current working directory will be used.",
            },
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files or directories.",
            },
        },
        "required": ["pattern"],
    }

    async def call(self, parameters: str, **kwargs) -> str:
        cwd = kwargs.get("cwd", Path.cwd().as_posix())
        params: dict = json.loads(parameters)
        # Support both official "directory" and model hallucinated "path".
        directory = params.get("directory") or params.get("path") or cwd
        directory = normalize_workspace_path(directory, cwd)
        pattern = normalize_glob_pattern(params.get("pattern"), cwd)

        p = Path(directory)
        if not p.is_dir():
            return f"<system-reminder>Error: directory `{directory}` does not exist or is not a directory.</system-reminder>"
        ok, normalized = ensure_within_workspace(directory, cwd)
        if not ok:
            return f"<system-reminder>Permission error: `{directory}` is not within the working directory `{cwd}`</system-reminder>"
        directory = normalized

        output = run(directory, pattern, cwd=cwd)

        limit = 100
        matched_files = output.splitlines()
        if len(matched_files) > limit:
            matched_files = matched_files[:limit]
            matched_files.append(
                f"Results are truncated: showing first {limit} results. Consider using a more specific path or pattern."
            )

        if not matched_files:
            return "No files found"
        return "\n".join(matched_files)
