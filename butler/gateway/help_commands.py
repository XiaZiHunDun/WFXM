"""WeChat / CLI help text for Butler slash commands."""

from __future__ import annotations


def format_help_text() -> str:
    return """Butler 常用命令

项目: /项目 /切换 /model
状态: /状态 /诊断 /health /任务
对话: /新对话 /steer /queue /待办
权限: /批准一次 /始终允许 <权限> /权限
      /批准执行 <命令> /确认安装 <id>
委派: delegate_task（微信下默认后台，完成后单独通知）
导出: /导出 [行数]（会话 Markdown + 微信发 .md，Owner）
回滚: /回滚 [保留行数]（仅 transcript，Owner）
规划: /计划 /执行 /确认 /取消
记忆: /记忆待审 /批准记忆 /拒绝记忆
其它: /workflow /定时 /runtime /开发状态

环境要点:
· BUTLER_DELEGATE_ASYNC=1 微信后台委派
· BUTLER_DOOM_LOOP_MODE=ask 需 Owner 批准重复工具
· BUTLER_PROJECT_WORKTREE=1 + project.yaml worktree:"""
