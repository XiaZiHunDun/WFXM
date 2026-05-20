# 遗留测试（默认不跑）

`test_butler_v3.py` 覆盖 Butler v3 与 Hermes `AIAgent` 嵌入路径，含已废弃的 `PostSessionProcessor.from_hermes_agent`。

默认 `pytest` 通过 `norecursedirs = archive` 跳过本目录。需要时：

```bash
PYTHONPATH=. pytest tests/archive/test_butler_v3.py -q
```
