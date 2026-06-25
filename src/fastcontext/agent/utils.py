import os
import platform
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from jinja2 import Environment as JinjaEnvironment
from jinja2 import StrictUndefined


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemPromptArgs:
    OS_KIND: str
    SHELL_NAME: str
    WORK_DIR: str
    WORK_DIR_LS: str


def _load_system_prompt(path: Path, builtin_args: SystemPromptArgs) -> str:
    system_prompt = path.read_text(encoding="utf-8").strip()
    env = JinjaEnvironment(
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
        variable_start_string="${",
        variable_end_string="}",
        undefined=StrictUndefined,
    )
    try:
        template = env.from_string(system_prompt)
        return template.render(asdict(builtin_args))
    except Exception as e:
        raise RuntimeError(f"Failed to render system prompt template: {e}") from e


def load_system_prompt(work_dir: str) -> str:

    os_kind = platform.system()
    shell_name = os.getenv("SHELL", "bash")
    work_dir_ls = "\n".join(os.listdir(work_dir))

    return _load_system_prompt(
        path=Path(__file__).parent / "system.md",
        builtin_args=SystemPromptArgs(
            OS_KIND=os_kind,
            SHELL_NAME=shell_name,
            WORK_DIR=work_dir,
            WORK_DIR_LS=work_dir_ls,
        ),
    )


def parse_citations(text: str) -> list:
    final_answer = re.search(r"<final_answer>(.*?)</final_answer>", text, re.DOTALL)
    if final_answer is None:
        return []

    entries = final_answer.group(1).strip().splitlines()

    entries = [e for e in entries if e.strip()]

    citations = []
    for entry in entries:
        # /absolute/path/to/file_1.py:10-15
        # /absolute/path/to/file_1.py:10-15 (explanation 1)
        # /absolute/path/to/file_1.py:10 (explanation 2)
        match = re.match(r"(.+?):(\d+(?:-\d+)?)\s*(.*)", entry.strip())
        if match:
            file_path = match.group(1).strip()
            line_range = match.group(2).strip()
            explanation = match.group(3).strip() if match.group(3) else ""
            start_line, end_line = line_range.split("-") if "-" in line_range else (line_range, line_range)
            start_line = int(start_line.strip())
            end_line = int(end_line.strip())
            citations.append(
                {
                    "path": file_path,
                    "line_range": line_range,
                    "start_line": start_line,
                    "end_line": end_line,
                    "explanation": explanation,
                }
            )
    return citations


def _resolve_path(file_path: str, work_dir: str | None) -> str:
    """Convert a relative path to an absolute path using work_dir."""
    p = Path(file_path)
    if p.is_absolute():
        return p.as_posix()
    if work_dir:
        return (Path(work_dir) / file_path).as_posix()
    return file_path


def format_citations(citations: list, work_dir: str | None = None, validate: bool = True) -> str:

    if validate:
        validated_citations = []
        for c in citations:
            absolute_path = _resolve_path(c["path"], work_dir)
            if not os.path.isfile(absolute_path):
                continue
            c["path"] = absolute_path
            validated_citations.append(c)

        citations = validated_citations

    formatted = []
    for c in citations:
        if c["explanation"]:
            formatted.append(f"{c['path']}:{c['line_range']} {c['explanation']}")
        else:
            formatted.append(f"{c['path']}:{c['line_range']}")
    return "<final_answer>\n" + "\n".join(formatted) + "\n</final_answer>"


def get_final_answer(text: str, work_dir: str | None = None) -> str:
    final_answer_match = re.search(r"<final_answer>(.*?)</final_answer>", text, re.DOTALL)
    if final_answer_match is None:
        return text.strip()

    citations = parse_citations(text)
    final_answer = format_citations(citations, work_dir=work_dir)
    return final_answer


if __name__ == "__main__":
    print(load_system_prompt(os.getcwd()))
