# Corpus Suite 数据约定 v1

机器校验逻辑见 `tests/corpus/harness/loader.py`（迁移后）。

## meta（必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `suite_id` | string | 与 `registry.yaml` 一致，如 `dev_assistant.v3` |
| `version` | string | 语料批次版本 |
| `live_model` | string | live 默认模型名 |
| `dimensions` | string[] | 分类维度，用于统计 |

可选：`live_provider`、`title`、`generation_doc`、`channel`（也可只在 registry）

## cases[] — 单轮

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 套件内唯一，如 `DA3-01` |
| `dimension` | ✅ | 属于 meta.dimensions 之一 |
| `title` | ✅ | 短标题 |
| `user` | ✅ | 用户原话（建议 `|` 块） |
| `must_contain` | | 硬词列表 |
| `must_contain_any` | | 第 1 组「任一命中」 |
| `must_contain_any2` … | | 编号连续 |
| `must_not_contain` | | 禁止出现 |
| `tags` | | 仅归档：`intent`、`difficulty`、`expected_route` |

## cases[] — 多轮

- 含 `turns:` 列表，每项含 `user` + rubric 字段，无顶层 `user`。

## live_smoke_ids

字符串数组，引用本文件 `cases[].id`（仅单轮或也可含 MT id，由 runner 定义）。

## Gateway 扩展（channel=gateway_wechat）

```yaml
- id: LW-REAL-01
  dimension: delegation
  user: ...
  setup: lingwen1_minimal
  expect:
    tools_called: [write_file]
    reply_contains_any: [完成]
```

详见 `docs/plans/corpus/corpus-testing-module-design-2026-05.md` 第三节。
