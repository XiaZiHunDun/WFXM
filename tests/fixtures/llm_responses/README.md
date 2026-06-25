# LLM response fixtures（编排层确定性测试）

> **用途**：给 `AgentLoop` / 工具编排写 **不调用真 API** 的多轮脚本。  
> **原则**：见 [`docs/plans/decisions/agent-testing-strategy-2026-06.md`](../../../docs/plans/decisions/agent-testing-strategy-2026-06.md)

## 格式

```json
{
  "description": "人类可读说明",
  "turns": [
    {
      "content": "可选文本",
      "finish_reason": "stop | tool_calls",
      "tool_calls": [
        {"id": "call_1", "name": "read_file", "arguments": {"path": "x"}}
      ]
    }
  ]
}
```

## 加载

```python
from tests.fixtures.llm_responses import load_llm_script, mock_client_from_script

script = load_llm_script("text_only.json")
client = mock_client_from_script(script)
```

## 新增夹具

1. 在本目录添加 `*.json`
2. 在 `tests/test_llm_response_fixtures.py` 增加对应用例（Loop 或 client 播放）
3. **不要**把真机微信措辞写进断言；断言工具名、轮次、`LoopStatus`、文件契约

## 与 corpus / live_llm 的关系

| 层 | 目录 / marker |
|----|----------------|
| 编排 replay（本目录） | 默认 CI，`module_test` |
| 语料 mock 管道 | `tests/corpus` · `corpus_mock` |
| 真模型质量 | `live_llm` · `corpus_live` |
