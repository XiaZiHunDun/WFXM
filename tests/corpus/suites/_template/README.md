# 新语料套件模板

1. 复制本目录为 `suites/<your_suite>/v1/`  
2. 编辑 `corpus.yaml`、`meta.yaml`  
3. 在 [`../../registry.yaml`](../../registry.yaml) 注册 `suite_id`  
4. 实现或挂接 `runners/` 中对应 `channel`  

数据约定：[`../../schemas/corpus-suite-v1.md`](../../schemas/corpus-suite-v1.md)
