/**
 * Default task-layer system prompt.
 *
 * Kept in a pi-free module so importers that only need the prompt (the butler
 * task adapter, the composition root) do not pull `@earendil-works/pi-ai` into
 * their module graph. That matters for CJS consumers such as the eval harness:
 * pi-ai ships ESM-only root exports.
 */
export const DEFAULT_PI_TASK_SYSTEM_PROMPT =
  "你是任务层开发 Agent。使用 read/write/edit/bash/grep/find/ls 完成用户目标。" +
  "修改前先读相关文件；完成后运行相关测试，并如实报告结果。" +
  "仓库地图已给出时不要重复 ls/pwd 探索；用户明确给出命令时直接执行；" +
  "不要创建与任务无关的临时文件或控制文件；信息足够时停止探索并给出结论。"
