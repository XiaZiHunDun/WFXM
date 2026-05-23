# Live 跑批归档

设置 `CORPUS_ARCHIVE=1` 后，runner 会向 `runs/<CORPUS_RUN_ID>.jsonl` 追加每用例一行。

可选环境变量：

- `CORPUS_RUN_ID` — 默认 UTC 时间戳  
- `CORPUS_ARCHIVE=1` — 开启写入  

字段见 [`docs/plans/corpus-testing-module-design-2026-05.md`](../../../docs/plans/corpus-testing-module-design-2026-05.md) 第五节。

归纳多轮跑批后，人工整理到 `docs/plans/corpus-issue-map-YYYY-MM.md`。
