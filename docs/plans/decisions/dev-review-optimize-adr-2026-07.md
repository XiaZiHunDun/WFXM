# ADR：开发审查与优化三层（Verify / Review / Optimize）

> **状态**：已采纳（2026-06-30）  
> **边界**：DevEngine `dev_verify` / `dev_review` / optimize advisory  
> **关联**：[`v4-dev-engine-theory.md`](../../architecture/v4-dev-engine-theory.md) · [`dev-engine-acl-adr-2026-07.md`](dev-engine-acl-adr-2026-07.md)

## 背景

`dev_verify`（V1–V5）保证**能跑**；`coding_knowledge` 服务**生成**；`review_agent` 为 opt-in LLM 审查。缺少结构化 **Review Knowledge Layer** 与**优化建议**产品路径。

## 决策

1. **三层分离**：Verify（正确性）→ Review（质量 rubric）→ Optimize（advisory 建议）
2. **契约**：`DevReviewView`（`butler/contracts/review_ports.py`）+ `review_context_adapter`
3. **确定性审查**：`review_static.py` + `review_knowledge.py` rubric（H13，无 LLM）
4. **工具**：`dev_review`；`BUTLER_DEV_AUTO_REVIEW=0` 默认不自动跑；`=1` 时 verify 通过后进入 REVIEW 并自动 static review
5. **严格门控**：`BUTLER_DEV_REVIEW_STRICT=1` + pilot 类别 → `apply_dev_review_strict_gate`
6. **闭环**：`review_closure.py` → reflection / experience 候选；`nexus-sprint` 提示 follow-up review

## 非目标

- 全量自动 refactor
- IDE LSP 审查
- 默认阻断所有 dev 委派

## 验收

- `tests/core/test_review_context_adapter.py` ≥10 cases
- `tests/dev_engine/test_review_static.py` / `test_dev_review_tool.py` 绿
- `b11_review_static` benchmark 绿
- `bash scripts/check-schema-drift.sh` exit 0
