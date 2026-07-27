"""Seed data for code_engineering domain."""

from __future__ import annotations

from typing import Any, Dict, List

CODE_ENGINEERING_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "代码审查清单",
        "content": """代码审查清单：

1. 代码质量：
   - 命名清晰
   - 注释充分
   - 逻辑简洁
   - 避免重复

2. 安全性：
   - 输入验证
   - 敏感数据保护
   - SQL注入防护
   - XSS防护

3. 性能：
   - 算法复杂度
   - 内存使用
   - 避免性能陷阱

4. 可维护性：
   - 遵循编码规范
   - 模块化设计
   - 错误处理完善

5. 测试覆盖：
   - 单元测试覆盖
   - 集成测试覆盖
   - 边界条件测试""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "重构技巧",
        "content": """代码重构技巧：

1. 重构原则：
   - 保持行为不变
   - 小步前进
   - 有测试保护

2. 常见重构：
   - 提取函数
   - 提取类
   - 拆分复杂方法
   - 消除重复代码

3. 代码异味：
   - 过长函数
   - 过大类
   - 重复代码
   - 魔法数字

4. 重构工具：
   - IDE重构功能
   - Python: refactor, rope
   - 代码审查工具

5. 重构流程：
   - 识别问题
   - 制定计划
   - 实施重构
   - 运行测试
   - 验证效果""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "测试策略",
        "content": """软件测试策略：

1. 测试分层：
   - 单元测试：测试单个函数/类
   - 集成测试：测试模块间交互
   - 系统测试：测试完整系统
   - 验收测试：验证业务需求

2. 测试类型：
   - 功能测试：验证功能正确性
   - 性能测试：验证系统性能
   - 安全测试：验证系统安全
   - 兼容性测试：验证多环境兼容

3. 测试技术：
   - 黑盒测试：不关心实现
   - 白盒测试：基于代码结构
   - 灰盒测试：结合两者

4. 测试工具：
   - Python: pytest, unittest
   - 覆盖率：coverage.py
   - 性能：locust, k6

5. 测试管理：
   - 测试用例管理
   - 测试执行计划
   - 缺陷追踪""",
        "priority": 2,
    },]
