"""WeChat / CLI help text for Butler slash commands — grouped by topic."""

from __future__ import annotations


_HELP_GROUPS: dict[str, tuple[str, str]] = {
    "项目": ("项目管理", """
/项目            列出所有项目
/切换 <名称>     切换当前项目
/状态            当前项目与管家状态
/项目概况        项目概况（Owner）；/项目概况 详细 看运维统计
/项目待办        项目级待办事项"""),

    "模型": ("模型与预设", """
/模型            查看当前四角色模型
/模型 <角色> <provider/model>   临时切换
/模型 save <角色> <provider/model>   持久化到 YAML
/模型 reset [角色]              清除临时覆盖
/预设            列出 butler:// provider 预设"""),

    "对话": ("对话控制", """
/新对话          重置当前会话
/继续            恢复中断的任务
/steer <指令>    插入引导消息（不中断当前任务）
/停止            中断当前任务
/queue [模式]    入站队列模式（followup/collect/interrupt/steer）
/待办            查看/管理会话待办
/简报            管家简报（待办/提醒/待审汇总）
/今日            本项目今日优先事项
/分工            Butler 与 CC/Cursor 分工（/cc）
/inbox           管家收件箱详情
/委派质量         B9 基准与生产委派质量（/b9）
/本轮已读        本轮 read_file 路径清单
/本轮工具        本轮工具叙事（/本轮工具 raw 看原始参数）
/压缩报告        本会话压缩状态
/信任            信任与透明度（权限/Skill/记忆）
/记忆来源        上轮记忆预取来源（脱敏）"""),

    "记忆": ("记忆与知识", """
/记忆待审        查看待审批记忆
/记忆来源        上轮记忆预取来源
/批准记忆        批准待审记忆
/拒绝记忆        拒绝待审记忆
/记忆图谱        查看三元组关系图
/记忆提炼        从 transcript 提炼记忆"""),

    "权限": ("权限与安全", """
/权限            查看当前权限状态
/批准一次        放行一次被拦截的操作
/始终允许 <权限>  永久放行某类操作
/批准执行 <命令>  批准 terminal 命令
/批准沙箱外 <命令>  沙箱失败后无 bubblewrap 重试
/批准模式 <模式>  按模式批准（24h 有效）
/确认安装 <id>   确认 Skill/MCP 安装"""),

    "开发": ("开发工具", """
/git             Git 状态摘要
/测试            运行项目测试
/构建            运行项目构建
/开发状态        开发环境概况
/开发验收        跑开发冒烟测试
/沙箱            终端沙箱诊断与 sandbox.json
/cc-bridge       Claude Code CLI 重任务（opt-in）"""),

    "日常": ("日常生活", """
/备忘            查看备忘录
/通讯录          查看通讯录
/记账            查看记账概览
/打卡            查看习惯打卡
/pim              PIM 数据使用概览"""),

    "管理": ("系统管理", """
/config          查看/修改系统配置
/配置            同上
/诊断            简要健康（Owner 可读）
/诊断 详细        全量运维快照（记忆/模型/队列）
/health          同 /诊断
/doctor          仅安全审计（Owner；运维请用 /诊断 详细）
/成本             查看会话成本概览
/导出 [行数]     导出会话为 Markdown
/回滚 [行数]     回滚 transcript
/定时            查看定时任务
/runtime         同上
/工作流          工作流管理
/技能            Skill 搜索/安装/管理
/mcp             MCP 搜索/安装/管理"""),

    "规划": ("规划模式", """
/计划            进入规划模式
/执行            退出规划，开始执行
/确认            确认 workflow 步骤
/取消            取消 workflow 步骤"""),
}

# Aliases for group names
_GROUP_ALIASES: dict[str, str] = {
    "project": "项目", "projects": "项目",
    "model": "模型", "models": "模型",
    "chat": "对话", "session": "对话", "会话": "对话",
    "memory": "记忆",
    "permission": "权限", "permissions": "权限", "安全": "权限",
    "dev": "开发", "development": "开发",
    "daily": "日常", "life": "日常", "生活": "日常",
    "admin": "管理", "system": "管理", "系统": "管理",
    "plan": "规划", "planning": "规划",
}


def format_help_text(topic: str = "") -> str:
    """Return help text; if topic given, show that group only.

    Default (no topic): Owner tier-1 commands only.
    Topic ``高级`` / ``advanced``: full command index.
    """
    topic = topic.strip()

    if not topic:
        from butler.gateway.owner_surface import format_owner_help_default

        return format_owner_help_default()

    if topic.lower() in ("高级", "advanced", "all", "全部"):
        from butler.gateway.owner_surface import format_owner_help_advanced

        return format_owner_help_advanced()

    group = _GROUP_ALIASES.get(topic.lower(), topic)
    entry = _HELP_GROUPS.get(group)
    if entry:
        title, body = entry
        return f"Butler 帮助 — {title}\n{body.strip()}"
    try:
        from butler.gateway.command_registry import format_registry_help

        registry_result = format_registry_help(topic)
        if not registry_result.startswith("未找到"):
            return registry_result
    except Exception:
        pass
    return (
        f"未找到帮助主题: {topic}\n\n"
        f"可用主题: {', '.join(_HELP_GROUPS.keys())}\n"
        "或发 /帮助 高级 查看全部"
    )
