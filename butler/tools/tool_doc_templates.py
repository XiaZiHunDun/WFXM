"""Cursor/Claude Code–style tool description DSL (When to use / When NOT / Examples).

Patterns are original Chinese summaries — not copied vendor prompt text.
"""

from __future__ import annotations

_TOOL_DOC_BLOCKS: dict[str, str] = {
    "read_file": """\
读取工作区内文本文件内容（支持 offset/limit 分段）。

**何时使用**
- 需要查看具体实现、配置或文档原文
- 大文件已返回摘要后，按提示的 offset/limit 精读片段
- 委派前自行核对路径或接口签名

**何时不要用**
- 用 terminal 跑 cat/head/tail 代替本工具
- 在规划模式下修改代码（应只写 plan 文件）
- 已知可用 search_files 定位时仍全文通读超大文件

**示例**
- `{"path": "butler/orchestrator.py", "offset": 200, "limit": 80}`
- 大文件首次调用可省略 limit，由系统返回行数摘要后再分段读取""",
    "search_files": """\
用 ripgrep 在工作区内按正则搜索文件内容。

**何时使用**
- 不知道符号定义在哪个文件
- 需要批量匹配字符串、函数名、配置键

**何时不要用**
- 已知精确文件路径时（用 read_file）
- 用 terminal 跑 grep/find 代替（违反工具纪律）
- 搜索范围过大且无 include 过滤导致噪音过多

**示例**
- `{"pattern": "build_system_prompt", "path": "butler", "include": "*.py"}`""",
    "delegate_task": """\
把需要在项目 workspace 内动手的任务交给 dev/content/review 子代理。

**何时使用**
- 用户要求改项目代码、跑测试、写章节、做审查
- 任务超出管家层只读能力或需要隔离上下文

**何时不要用**
- 简单问答、状态查询、只读浏览
- 规划模式未退出时（先发 /执行）
- 可用 read_file 自行完成的极短查看

**示例**
- `{"role": "dev", "task": "修复 tests/test_foo.py 失败", "context": "不要改 butler/config.py"}`""",
    "terminal": """\
在启用 BUTLER_ENABLE_TERMINAL=1 时执行受限 shell 命令。

**何时使用**
- 跑测试、构建、包管理、git 状态等需真实进程的操作
- 子代理或用户已明确批准的一次性命令

**何时不要用**
- 用 cat/grep/find 读文件或搜代码（用 read_file / search_files）
- 规划模式下任何 shell
- 未获批准的破坏性命令（rm -rf、curl|bash 等）

**示例**
- `{"command": "pytest tests/test_plan_mode.py -q", "workdir": "."}`""",
    "patch": """\
在文件中精确替换一段文本（old_string 必须完全匹配）。

**何时使用**
- 局部修改已有文件且上下文明确
- 配合 read_file 确认 old_string 唯一匹配

**何时不要用**
- 新建文件（用 write_file）
- 规划模式（除非写入允许的 plan 路径）
- 未读文件就猜测替换内容

**示例**
- `{"path": "src/app.py", "old_string": "return False", "new_string": "return True"}`""",
    "write_file": """\
写入或覆盖工作区内的文件。

**何时使用**
- 创建新文件或整文件重写
- 规划模式下写入 `.butler/plan/`、`*plan.md`、`implementation_plan.md`

**何时不要用**
- 小范围编辑（优先 patch）
- 规划模式下写入源码目录
- 委派应由子代理完成的业务文件

**示例**
- 规划: `{"path": ".butler/plan/approach.md", "content": "# 方案\\n..."}`""",
    "list_directory": """\
列出目录下的文件与子目录。

**何时使用**
- 探索未知目录结构、确认文件是否存在

**何时不要用**
- 需要文件内容时（用 read_file）
- 深度遍历整个仓库（用 search_files 或限定 path）

**示例**
- `{"path": "butler/gateway"}`""",
}


def enrich_tool_description(name: str, base_description: str) -> str:
    """Append structured DSL block when a template exists."""
    block = _TOOL_DOC_BLOCKS.get(str(name or "").strip())
    if not block:
        return base_description
    base = (base_description or "").strip()
    if "何时不要用" in base or "When NOT" in base:
        return base
    if base:
        return f"{base}\n\n{block.strip()}"
    return block.strip()


def tool_description_has_not_section(description: str) -> bool:
    """True if description includes an explicit anti-pattern section."""
    text = str(description or "")
    return "何时不要用" in text or "When NOT" in text


__all__ = [
    "enrich_tool_description",
    "tool_description_has_not_section",
]
