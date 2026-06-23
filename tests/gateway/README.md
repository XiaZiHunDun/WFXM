# Gateway / 微信 / 斜杠命令测试

> 域化迁移（2026-06-23）：自 `tests/test_gateway_*`、`tests/test_wechat_*` 等迁入。  
> Sprint 迁移测试（`test_sprint16_tst10_5_*`）仍留在 `tests/` 根目录。

```bash
PYTHONPATH=. pytest tests/gateway/ -q
```

**守门（改 `butler/gateway/` 后建议）**：

```bash
PYTHONPATH=. pytest tests/gateway/ tests/test_sprint16_tst10_5_*_migration.py -q
```
