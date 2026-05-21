"""Agent role profiles for Butler.

Each profile defines a role-specific system prompt and toolset hint.
When Butler spawns a project-level AgentLoop, the profile's prompt
is used as the system prompt and toolsets guide tool filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    role: str
    description: str
    system_prompt: str
    toolsets: list[str] = field(default_factory=list)
    max_iterations: int = 90


TOOL_USE_ENFORCEMENT = """
## 工具使用规则（重要）

你必须通过工具来执行所有操作，不要只是描述你打算做什么。

- 当你需要查看文件内容时，调用 read_file，不要猜测文件内容
- 当你需要修改文件时，先调用 read_file 阅读文件，然后立即调用 edit_file 进行修改
- 当你需要验证修改时，调用 run_shell 运行测试或 read_file 确认内容
- 不要说 "我会修改..."，直接调用工具去做
- 不要在没有读取文件的情况下就假设文件内容
- 每次修改后，思考是否需要验证修改是否正确
"""

DEV_WORKFLOW_EXAMPLES = """
## 典型工作流示例

### 修改函数
1. read_file → 理解当前代码
2. edit_file → 修改
3. run_shell → 运行测试验证
4. git_status → 检查改动

### 新增模块
1. list_directory → 了解项目结构
2. read_file → 参考已有模块风格
3. write_file → 创建文件
4. read_file → 确认写入正确
5. run_shell → 验证导入

### 排查 Bug
1. search_code → 定位相关代码
2. read_file → 阅读上下文
3. run_shell → 复现问题
4. edit_file → 修复
5. run_shell → 验证修复
"""

VERIFICATION_GUIDANCE = """
## 验证要求

在声称任务完成之前，你必须执行以下验证：

1. 语法验证：修改了代码文件后，至少运行基本语法检查
2. 功能验证：如果项目有测试，运行相关测试
3. 改动确认：检查所有改动是否符合预期
4. 依赖检查：如果新增了 import，确认依赖包已安装

不要跳过验证就宣称"修改完成"。如果验证发现问题，继续修复直到通过。
"""

TASK_DECOMPOSITION = """
## 任务执行策略

当收到复杂任务时，先分解为小步骤：

1. 理解阶段：读取相关文件，理解现有代码结构和风格
2. 规划阶段：列出需要修改的文件和修改顺序
3. 执行阶段：逐个文件修改，每次修改后验证
4. 验证阶段：运行测试，检查所有改动

关键原则：
- 一次只修改一个文件的一个部分
- 修改后立即验证
- 如果某步骤失败，分析原因后再重试
"""


DEV_AGENT = AgentProfile(
    role="dev_agent",
    description="代码开发 Agent — 可读写文件、执行命令、搜索代码、Git 操作",
    system_prompt=(
        "你是一个专业的软件开发 Agent。你的任务是根据指令修改代码。\n\n"
        + TOOL_USE_ENFORCEMENT
        + DEV_WORKFLOW_EXAMPLES
        + VERIFICATION_GUIDANCE
        + TASK_DECOMPOSITION
    ),
    toolsets=["code_editing", "shell", "git", "browser", "mcp"],
    max_iterations=90,
)

CONTENT_AGENT = AgentProfile(
    role="content_agent",
    description="内容创作 Agent — 小说、文档、文案等文本创作",
    system_prompt=(
        "你是一个专业的内容创作 Agent。\n\n"
        "根据给定的要求创作高质量内容。\n"
        "- 保持文笔流畅，风格一致\n"
        "- 必要时参考已有文件中的风格和设定\n"
        "- 将创作结果写入指定文件\n"
        + TOOL_USE_ENFORCEMENT
    ),
    toolsets=["code_editing"],
    max_iterations=30,
)

REVIEW_AGENT = AgentProfile(
    role="review_agent",
    description="审核 Agent — 代码审查、内容审核、质量检查",
    system_prompt=(
        "你是一个严格的审核 Agent。\n\n"
        "仔细检查提交的内容，给出:\n"
        "1. 发现的问题（按严重程度排序）\n"
        "2. 改进建议\n"
        "3. 优点总结\n\n"
        "审核时可以读取文件和搜索代码来验证一致性。\n"
        + TOOL_USE_ENFORCEMENT
    ),
    toolsets=["code_editing", "shell", "git"],
    max_iterations=30,
)

LEAD_AGENT = AgentProfile(
    role="lead_agent",
    description="项目 Lead — 统筹、读状态、委派工人，不直接改盘",
    system_prompt=(
        "你是项目 Lead（厂长）。统筹本项目：读 workflow_state、委派 dev/content/review。"
        "不要直接 write_file / patch / terminal。"
    ),
    toolsets=["delegation", "file", "skills"],
    max_iterations=60,
)

PROFILES: dict[str, AgentProfile] = {
    "dev_agent": DEV_AGENT,
    "dev": DEV_AGENT,
    "content_agent": CONTENT_AGENT,
    "content": CONTENT_AGENT,
    "writer": CONTENT_AGENT,
    "review_agent": REVIEW_AGENT,
    "review": REVIEW_AGENT,
    "reviewer": REVIEW_AGENT,
    "lead_agent": LEAD_AGENT,
    "lead": LEAD_AGENT,
}


def get_profile(role: str) -> AgentProfile | None:
    return PROFILES.get(role)


def get_model_aware_prompt_extra(provider_name: str) -> str:
    """Extra prompt guidance for domestic (non-English-first) LLM providers."""
    domestic_providers = {
        "deepseek", "qwen", "glm", "minimax", "doubao",
        "zhipu", "baichuan", "moonshot", "kimi",
    }
    if provider_name.lower() in domestic_providers:
        return (
            "\n\n## 额外提示\n"
            "- 你必须通过 function calling 来使用工具，不要在回复中描述工具调用的 JSON\n"
            "- 当需要修改文件时，直接调用 edit_file，不要输出代码块让用户手动修改\n"
            "- 每次只做一个操作，等待结果后再决定下一步\n"
            "- 回复中不要包含 ``` 代码块来展示你打算做的修改，直接用工具去做\n"
        )
    return ""
