# ADR：DevEngine 验证边界防腐层（Dev ACL）

> **状态**：已采纳（2026-06-29）  
> **边界**：外部 verify 产物 / dict → `dev_loop.transition` → `DevState.verify_result`  
> **关联**：[`compaction-acl-adr-2026-07.md`](compaction-acl-adr-2026-07.md) · [`v4-dev-engine-theory.md`](../../architecture/v4-dev-engine-theory.md)

## 背景

`dev_verify`、auto-verify、`verify_layered` 输出可能为 `VerifyResult`、工具 JSON dict 或遗留形态。`dev_loop.transition` 应只依赖 **DevVerifyView** 不变契约，外部变种在适配器消化。

## 决策

1. **神圣契约**：`DevVerifyView`（`butler/contracts/dev_context_ports.py`）
2. **适配器**：`to_verify_result()` / `to_dev_verify_view()`（`butler/core/dev_context_adapter.py`）— 永不向调用方抛异常
3. **单入口接线**：`dev_loop.transition` 的 `verify_fail` / `verify_pass`（带 `verify_result` kwargs）
4. **Schema CI**：`schemas/dev/dev_verify_view.v1.json` + `check-schema-drift.sh`

## 非目标

- 全量 `DevState` Pydantic 化
- `PLAN→FIX` 转移表本身外置配置化

## 验收

- `tests/core/test_dev_context_adapter.py` 绿
- `bash scripts/check-schema-drift.sh` exit 0
