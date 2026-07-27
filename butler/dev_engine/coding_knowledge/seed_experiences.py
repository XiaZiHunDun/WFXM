"""Seed experiences for coding knowledge layer."""

from __future__ import annotations

from typing import Any, Dict, List

SEED_EXPERIENCES: List[Dict[str, Any]] = [
    {
        "id": "EXP_00000001",
        "title": "Python类型注解最佳实践",
        "domain": ["python", "type_safety"],
        "theorem_basis": ["T02", "T03"],
        "context": "为Python函数添加类型注解，提高代码可读性和IDE支持",
        "pattern": "def function_name(param: Type) -> ReturnType:\n    \"\"\"Docstring.\"\"\"\n    return result",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000002",
        "title": "异常处理模板",
        "domain": ["python", "error_handling"],
        "theorem_basis": ["T06"],
        "context": "Python异常处理的标准模式",
        "pattern": "try:\n    risky_operation()\nexcept SpecificError as e:\n    log.error(f\"Failed: {e}\")\n    handle_error(e)\nexcept AnotherError:\n    fallback()\nfinally:\n    cleanup()",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000003",
        "title": "资源管理上下文管理器",
        "domain": ["python", "resource"],
        "theorem_basis": ["T08"],
        "context": "使用with语句管理资源生命周期",
        "pattern": "with open(filename, 'r') as f:\n    content = f.read()\n\nwith contextlib.closing(resource):\n    resource.use()",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000004",
        "title": "幂等性操作模式",
        "domain": ["python", "state"],
        "theorem_basis": ["T07"],
        "context": "确保操作可以安全重复执行",
        "pattern": "def ensure_config(key: str, value: str) -> None:\n    config[key] = value\n\nseen = set()\nfor item in items:\n    seen.add(item)",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000005",
        "title": "循环终止条件",
        "domain": ["python", "control_flow"],
        "theorem_basis": ["T04"],
        "context": "确保循环有明确的终止条件",
        "pattern": "for item in iterable:\n    process(item)\n\nwhile condition and counter < max_iterations:\n    process()\n    counter += 1",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000006",
        "title": "输入验证模式",
        "domain": ["python", "security"],
        "theorem_basis": ["T10"],
        "context": "验证和清理外部输入",
        "pattern": "def validate_input(data: dict) -> None:\n    if not isinstance(data, dict):\n        raise ValueError(\"Expected dict\")\n    if 'key' not in data:\n        raise ValueError(\"Missing required key\")\n    sanitized = clean_data(data)",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000007",
        "title": "HTTP请求契约遵守",
        "domain": ["python", "api"],
        "theorem_basis": ["T09"],
        "context": "正确处理HTTP响应",
        "pattern": "response = requests.get(url)\nresponse.raise_for_status()\ndata = response.json()\n\nif response.status_code == 200:\n    process(data)\nelif response.status_code == 404:\n    handle_not_found()\nelse:\n    handle_error(response)",
        "benchmarks": {},
    },
    {
        "id": "EXP_00000008",
        "title": "状态隔离模式",
        "domain": ["python", "state"],
        "theorem_basis": ["T05"],
        "context": "最小化可变状态作用域",
        "pattern": "def calculate(items: list) -> int:\n    total = 0\n    for item in items:\n        total += item.value\n    return total\n\nclass Processor:\n    def __init__(self):\n        self._state = {}",
        "benchmarks": {},
    },
]