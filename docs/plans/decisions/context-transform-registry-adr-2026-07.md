# ADR：Context Transform Registry + Eval 反馈调参

> **状态**：已采纳（2026-06-29）· **Phase 2–3 落地**  
> **理论**：[`v4.5-modular-eval-context-theory.md`](../../architecture/v4.5-modular-eval-context-theory.md)

## 背景

模型差异散落于 `thinking_protocol`、`prepare_tools_for_llm`、`model_capabilities`；无 per-model 注册表与热加载。

## 决策

1. `ContextTransformRegistry`：按 `(provider, model_glob)` 匹配 transform 链
2. 配置：`~/.butler/model-transforms.yaml`（version + mtime 热载）
3. 管线挂载：`repair_sanitize` 之后、`pre_llm_transform` 之前
4. `thinking_protocol` 迁入 registry 内置 transform
5. **Eval 反馈**：`transform_overrides.json` + `transform_feedback.py`；有界 \(\Delta\)，独立于 `eval_overrides.json`

## 热加载触发

- YAML mtime 变化
- `/model`、preset apply → `refresh_model_binding()`
- LLM fallback 换 client

## 非目标

- 不引入训练栈或 Model Profile 自动学习
- 不做全自动 A/B（仅 bounded override）

## 验收

- `tests/test_context_transform_registry.py` 绿
- `/诊断` 详细模式可见 transform profile 行
