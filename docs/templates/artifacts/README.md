# `.butler/artifacts/` SOP（MetaGPT 主线 N P1 子集）

工作流与委派应优先读写以下路径（相对项目 workspace）：

| 文件 | 用途 |
|------|------|
| `REQUIREMENTS.md` | 需求与验收标准 |
| `TASKS.md` | 任务分解与状态 |
| `DESIGN.md` | UI/设计 token（可与根目录 `DESIGN.md` 并存） |

代码辅助：`butler/workflows/artifact_paths.py` — `ensure_artifact_scaffold(workspace)` 创建目录。

内置 `dev-qa-loop` / `ui-dev-qa-loop` 的 QA 步骤应 `read_file` 核对 `DESIGN.md`（若存在）。
