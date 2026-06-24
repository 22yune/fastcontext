
## 文件清单
- fc-find 命令行
- server.py mcp服务
- config.toml codex mcp配置
- AGENTS.md codex 全局指导文件

## 使用
- codex 中 提示词示例
  - 这个 bug 先别全局乱翻，先用 FastContext 找相关文件。
  - 先用 FastContext 找一下 RuoYi-Vue3 里的 package.json 和 router 文件。
  - 先用 FastContext 定位发票 PDF 解析、金额识别、销售方/购买方识别相关代码。


# FastContext MCP 接入 Codex App 与 Claude Code 说明文档

## 1. 目标

将本地已经封装好的 `fc-find` 命令接入 Codex App 和 Claude Code，使它们可以通过 MCP 工具自然调用 FastContext 做代码库搜索。

最终效果：

```text
用户只需要说：
“先用 FastContext 找一下 RuoYi-Vue3 里的 package.json 和 router 文件。”

Codex / Claude Code 自动调用：
fastcontext_search(query, repo_path, max_turns)

FastContext 返回：
相关文件路径、行号范围、代码定位结果。
```

FastContext 的定位是：**只读代码库搜索工具**。
它不负责修改代码，只负责帮助主 Agent 快速定位相关文件和行号。

---

## 2. 前置条件

已经具备：

```bash
fc-find -m 3 'Search /RuoYi-Vue3 for package.json and router files. Return exact file paths.'
```

并且该命令在普通终端中可以正常执行。

确认命令路径：

```bash
which fc-find
```

建议保证以下路径中能找到 `fc-find`：

```bash
$HOME/bin
$HOME/.local/bin
/opt/homebrew/bin
/usr/local/bin
```

---

## 3. 整体结构

```text
Codex App
   └── MCP 配置
        └── 启动 ~/.local/share/fc-find-mcp/server.py
              └── 调用 fc-find 命令

Claude Code
   └── MCP 配置
        └── 启动 ~/.local/share/fc-find-mcp/server.py
              └── 调用 fc-find 命令
```

注意：

```text
Codex 和 Claude Code 复用同一个 server.py 文件。
但它们不会共享同一个 MCP 进程，而是各自启动一个 MCP server 进程。
```

---

## 4. 创建 MCP wrapper

### 4.1 创建目录

```bash
mkdir -p ~/.local/share/fc-find-mcp
cd ~/.local/share/fc-find-mcp

uv init --bare
uv add "mcp[cli]"
```

---

### 4.2 写入 server.py

```bash
cat > ~/.local/share/fc-find-mcp/server.py <<'PY'
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


def resolve_repo_path(repo_path: str) -> Path:
    if repo_path.strip():
        return Path(repo_path).expanduser().resolve()

    # Claude Code 会注入当前项目目录
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        return Path(claude_project_dir).expanduser().resolve()

    # 兜底：使用当前工作目录的 git root
    return find_git_root(Path.cwd())


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

    repo = resolve_repo_path(repo_path)

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
PY
```

---

### 4.3 测试 MCP server

```bash
cd ~/.local/share/fc-find-mcp
uv run python server.py
```

正常情况：
命令不会立即退出，而是等待 MCP stdio 输入。

按 `Ctrl + C` 退出即可。

---

## 5. Codex App 用户级配置

### 5.1 编辑 Codex 配置文件

```bash
mkdir -p ~/.codex
nano ~/.codex/config.toml
```

加入：

```toml
[mcp_servers.fastcontext]
command = "/bin/bash"
args = [
  "-lc",
  "cd \"$HOME/.local/share/fc-find-mcp\" && exec uv run python server.py"
]
startup_timeout_sec = 20
tool_timeout_sec = 180
enabled = true
default_tools_approval_mode = "auto"
```

说明：

```text
command:
  用 bash 启动本地 MCP server。

args:
  进入 MCP server 目录，然后用 uv 运行 server.py。

startup_timeout_sec:
  MCP server 启动超时时间。

tool_timeout_sec:
  单次 FastContext 搜索超时时间。

default_tools_approval_mode:
  对这个只读搜索工具尽量减少确认弹窗。
```

---

### 5.2 Codex 全局 AGENTS.md

创建或编辑：

```bash
nano ~/.codex/AGENTS.md
```

加入极简提示词：

```md
## FastContext

Before broad codebase search, use `fastcontext_search` to locate relevant files and line ranges. Use the current repo root, default `max_turns = 3`, then read returned files before editing. FastContext is read-only.
```

这段不需要太长。
主要调用说明已经写在 MCP tool 的 docstring 里了，`AGENTS.md` 只负责提醒 Codex 优先使用 FastContext。

---

### 5.3 Codex 中的自然用法

以后不用手动写参数，只需要说：

```text
先用 FastContext 找一下 RuoYi-Vue3 里的 package.json 和 router 文件。
```

或者：

```text
先用 FastContext 定位发票 PDF 解析、金额识别、销售方/购买方识别相关代码。
```

或者：

```text
这个 bug 先别全局乱翻，先用 FastContext 找相关文件。
```

Codex 应该会自动调用：

```text
fastcontext_search(
  query = "...",
  repo_path = 当前仓库根目录,
  max_turns = 3
)
```

---

## 6. Claude Code 用户级配置

### 6.1 添加 MCP server

执行：

```bash
claude mcp add --scope user --transport stdio fastcontext -- /bin/bash -lc 'cd "$HOME/.local/share/fc-find-mcp" && exec uv run python server.py'
```

说明：

```text
--scope user:
  用户级配置，所有项目可用。

--transport stdio:
  本地 stdio MCP server。

fastcontext:
  MCP server 名称。

--:
  后面是真正启动 MCP server 的命令。
```

---

### 6.2 查看 MCP 配置

```bash
claude mcp list
```

查看详情：

```bash
claude mcp get fastcontext
```

进入项目后：

```bash
cd /path/to/your/project
claude
```

在 Claude Code 内输入：

```text
/mcp
```

应该能看到 `fastcontext` MCP server，以及工具：

```text
fastcontext_search
```

---

### 6.3 Claude Code 全局 CLAUDE.md

创建或编辑：

```bash
mkdir -p ~/.claude
nano ~/.claude/CLAUDE.md
```

加入：

```md
## FastContext

Before broad codebase search, use the `fastcontext_search` MCP tool to locate relevant files and line ranges. Use the current repo root, default `max_turns = 3`, then read returned files before editing. FastContext is read-only.
```

---

### 6.4 Claude Code 中的自然用法

以后可以直接说：

```text
先用 FastContext 找一下 RuoYi-Vue3 里的 package.json 和 router 文件。
```

或者：

```text
先用 FastContext 定位发票 PDF 解析、金额识别、销售方/购买方识别相关代码。
```

或者：

```text
这个 bug 先别全局乱翻，先用 FastContext 找相关文件。
```

Claude Code 会根据 MCP tool 的 docstring 和 `CLAUDE.md`，自动选择调用 `fastcontext_search`。

---

## 7. 推荐使用习惯

### 7.1 适合用 FastContext 的场景

```text
- 找 package.json
- 找 router 文件
- 找接口定义
- 找业务逻辑入口
- 找权限 / 登录 / token 校验
- 找数据库 / mapper / migration
- 找发票解析 / PDF 解析 / OCR 解析规则
- 找 bug 相关文件
- 在大项目里先缩小搜索范围
```

### 7.2 不适合用 FastContext 的场景

```text
- 直接让它改代码
- 直接让它跑测试
- 直接让它做完整重构
- 普通聊天问答
```

FastContext 的职责是：

```text
搜索代码 → 返回路径和行号 → 主 Agent 再读取文件 → 主 Agent 修改代码
```

---

## 8. 排错

### 8.1 Codex / Claude Code 找不到 fc-find

终端先确认：

```bash
which fc-find
```

如果有输出，但 MCP 里找不到，通常是 GUI App 或 MCP 进程的 `PATH` 不完整。

解决方式：
确认 `server.py` 里有这段：

```python
env["PATH"] = (
    "/opt/homebrew/bin:"
    "/usr/local/bin:"
    f"{Path.home()}/bin:"
    f"{Path.home()}/.local/bin:"
    + env.get("PATH", "")
)
```

如果 `fc-find` 在其他目录，把目录追加进去。

---

### 8.2 MCP server 启动失败

手动测试：

```bash
cd ~/.local/share/fc-find-mcp
uv run python server.py
```

如果这里报错，先修复 Python / uv / mcp 依赖。

重新安装依赖：

```bash
cd ~/.local/share/fc-find-mcp
uv add "mcp[cli]"
```

---

### 8.3 Codex 看不到 MCP 工具

检查配置：

```bash
cat ~/.codex/config.toml
```

确认包含：

```toml
[mcp_servers.fastcontext]
command = "/bin/bash"
args = [
  "-lc",
  "cd \"$HOME/.local/share/fc-find-mcp\" && exec uv run python server.py"
]
startup_timeout_sec = 20
tool_timeout_sec = 180
enabled = true
```

然后重启 Codex App。

---

### 8.4 Claude Code 看不到 MCP 工具

检查：

```bash
claude mcp list
claude mcp get fastcontext
```

必要时删除后重建：

```bash
claude mcp remove fastcontext
claude mcp add --scope user --transport stdio fastcontext -- /bin/bash -lc 'cd "$HOME/.local/share/fc-find-mcp" && exec uv run python server.py'
```

---

### 8.5 repo_path 不正确

Claude Code 会注入：

```text
CLAUDE_PROJECT_DIR
```

所以 `server.py` 里需要优先读取这个环境变量：

```python
claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
```

Codex 如果没有自动传当前仓库，可以在提示词里说：

```text
在当前项目根目录使用 FastContext 搜索。
```

也可以在 Codex 任务开始时明确说：

```text
当前仓库根目录是 /path/to/project，先用 FastContext 搜索相关文件。
```

---

## 9. 最终推荐工作流

### Codex App

```text
1. 打开项目
2. 提需求
3. 说“先用 FastContext 找相关文件”
4. Codex 调用 fastcontext_search
5. Codex 读取返回文件
6. Codex 修改代码
```

### Claude Code

```text
1. cd /path/to/project
2. claude
3. 提需求
4. 说“先用 FastContext 找相关文件”
5. Claude Code 调用 fastcontext_search
6. Claude Code 读取返回文件
7. Claude Code 修改代码
```

---

## 10. 一句话总结

```text
fc-find 是底层命令；
server.py 是 MCP wrapper；
Codex 和 Claude Code 都通过 MCP 调用 server.py；
server.py 再调用 fc-find；
用户只需要自然说“先用 FastContext 找相关文件”。
```
