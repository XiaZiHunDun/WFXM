# 灵文1号试点日志

| 日期 | 事件 | 备注 |
|------|------|------|
| 2026-05-21 | 微信验收通过 | workflow PHASE_COMPLETE, STEP_25（星陨纪元 v3.0 已发布，S级） |
| 2026-05-21 | 记忆模块 P0–P2 微信验收 | M1–M4 **真机全通过**（M4：同句 20–90s 内复问 → `/诊断` 上轮预取缓存命中）；pytest `test_memory_m3_m4_smoke`；`.env`：`SEMANTIC_MEMORY=1`、`QUEUE_PREFETCH=1` |
| 2026-05-21 | 记忆写入备忘 | `butler_remember` Notes：试点统一测试日 2026-05-22；流程：测试 → `/记忆待审` → `/批准记忆 全部` |
| 2026-05-21 | 项目 Lead 阶段 1 | ADR + Skill `lingwen-project-lead` + 厂长 `pre_llm_call`；**微信验收通过**（读 phase/step、content 委派写 docs、不直接改盘） |
| 2026-05-21 | 项目 Lead 阶段 2 | Lead AgentLoop + `/诊断` 对话引擎行；**微信验收通过**（切换厂长模式、多轮上下文、委派审计） |
| 2026-05-21 | 项目 Lead 阶段 3 | 运行时自动化 **设计方案** + `runtime/jobs.yaml` 草案；实施待 3a 开发 |
| 2026-05-21 | **稳上线**（记忆增强 + 开发工具） | `git push` → `351d41f`；`memory-reindex`；gateway restart；记忆守门脚本 + 推送摘要真机通过 |
| 2026-05-21 | **Runtime 运营 + 开发实战** | `butler-runtime-smoke.sh` 通过；timer enabled；`factory-status-daily` OK；`publish-preflight` 禁用拒绝；`consistency-weekly` 跑完 exit1（P1×3，有报告）；修复 runtime 微信推送 `PlatformConfig`；`butler-dev-tools-smoke.sh` patch/terminal/git 全绿 |
| 2026-05-21 | **一致性 / 预检策略** | 人物仅报「死后复活」；脚本 exit0 当 P0=0；runner `passed_with_warnings`；`publish-preflight` 改为 readonly + `preflight` 子命令并默认启用 |
| 2026-05-21 | **预检精度 + Agent Runtime** | preflight 第 7 步读最新 consistency JSON；Lead 可用 `run_runtime_job` / `list_runtime_jobs` |
| 2026-05-21 | **Live API + 推送限流** | live_llm 10/10 通过；runtime 推送冷却 + iLink 指数退避；`butler-wechat-push-verify.sh`；**真机收到 factory-status 摘要** |
| 2026-05-21 | **P0/P1 技术债批次** | 推送失败入队+`due` 重试；preflight 读 review_queue；`publish-archive` mutating job；微信守门 32+201 pytest；`character_waivers.yaml` |
| 2026-05-21 | **A–D 技术债清偿** | knowledge.db 同步；/诊断 推送队列；`drain-push`；逐步 workflow model；删 220424 报告；入站媒体+dev 委派守门脚本 |
| 2026-05-21 | **工程增强批次** | push-drain timer；`publish-merge` job；`gateway` config.yaml；logrotate 安装脚本；upgrade→reindex；`演示试点` 模板 |
| 2026-05-22 | **P1/P2 清偿** | prefer_ilink 接线；CI；`{workflow_version}`；多项目 due；推送去重；识图 fallback；auxiliary 入 Settings；/诊断 媒体耗时 |
| 2026-05-22 | **P2 运维/开发** | 运维快照；`/开发状态` `/开发验收`；ops-bundle；logrotate cron；模型展示统一 resolve |
| 2026-05-22 | **人工测试前准备** | `butler-pre-release-smoke.sh`；清单/`env.example` 同步；ops-bundle + gateway restart |
| 2026-05-22 | **P1/P2 工程** | runtime smoke 默认不推送；CI smoke job；连续失败告警+`/诊断`；preflight config/OCR；`wechat-ocr` extra；`setup-butler-config.sh` |

## 稳上线后微信补验（自动化已守门，真机可快速勾选）

| 步骤 | 发送 | 期望 | 守门 |
|------|------|------|------|
| M1 | `/诊断` | 含三元组条数、检索衰减、画像向量（若有） | `butler-wechat-memory-smoke.sh` |
| M1b | `/记忆图谱` | 列出三元组或空状态提示 | `test_memory_graph_command` |
| M2 | 「灵文试点统一测试是哪天？」 | 仍答 **2026-05-22** | recall fixtures |
| M4 | 同句连发两遍 → `/诊断` | 「上轮预取缓存: 命中」 | `test_memory_m3_m4_smoke` |