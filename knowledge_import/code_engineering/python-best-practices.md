# Python开发最佳实践

## 代码风格

### PEP 8规范

**缩进**：
- 使用4个空格
- 不要使用Tab

**行长度**：
- 最大79字符
- 文档字符串72字符

**命名规范**：
- 模块名：小写，使用下划线
- 类名：大驼峰命名
- 函数名：小写，使用下划线
- 变量名：小写，使用下划线
- 常量名：全大写，使用下划线

### 文档字符串

```python
def calculate_area(radius):
    """Calculate the area of a circle.
    
    Args:
        radius (float): The radius of the circle.
        
    Returns:
        float: The area of the circle.
        
    Raises:
        ValueError: If radius is negative.
    """
    if radius < 0:
        raise ValueError("Radius cannot be negative")
    return 3.14159 * radius ** 2
```

**规范**：
- 使用Google风格或NumPy风格
- 包含参数、返回值、异常说明
- 添加示例代码（可选）

## 类型提示

### 基本类型

```python
def greet(name: str) -> str:
    return f"Hello, {name}"

def add(a: int, b: int) -> int:
    return a + b
```

### 复杂类型

```python
from typing import List, Dict, Optional, Union

def process_items(items: List[str]) -> Dict[str, int]:
    return {item: len(item) for item in items}

def find_user(user_id: int) -> Optional[dict]:
    # 返回None或用户字典
    pass

def format_value(value: Union[str, int]) -> str:
    return str(value)
```

### 泛型类型

```python
from typing import TypeVar, Generic

T = TypeVar('T')

class Container(Generic[T]):
    def __init__(self, item: T):
        self.item = item
    
    def get(self) -> T:
        return self.item
```

## 错误处理

### 异常捕获

```python
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Value error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
else:
    # 没有异常时执行
    process_result(result)
finally:
    # 无论是否异常都执行
    cleanup()
```

**原则**：
- 捕获特定异常，不要捕获所有异常
- 提供有意义的错误信息
- 记录异常日志

### 自定义异常

```python
class ValidationError(Exception):
    """Raised when validation fails."""
    pass

class DatabaseError(Exception):
    """Raised when database operation fails."""
    def __init__(self, message: str, error_code: int):
        super().__init__(message)
        self.error_code = error_code
```

## 测试

### 单元测试

```python
import unittest

class TestMathFunctions(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
    
    def test_add_negative(self):
        self.assertEqual(add(-1, 1), 0)
    
    def test_divide(self):
        self.assertEqual(divide(10, 2), 5)
        with self.assertRaises(ZeroDivisionError):
            divide(10, 0)

if __name__ == '__main__':
    unittest.main()
```

### 使用pytest

```python
def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0

def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)
```

### 测试覆盖率

```bash
coverage run -m pytest tests/
coverage report -m
coverage html
```

**目标**：
- 核心代码覆盖率>80%
- 关键路径100%覆盖
- 定期检查覆盖率

## 性能优化

### 算法优化

```python
# 不好：O(n^2)
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            if items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates

# 好：O(n)
def find_duplicates(items):
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        seen.add(item)
    return duplicates
```

### 使用内置函数

```python
# 使用列表推导式
result = [x * 2 for x in numbers if x > 0]

# 使用生成器表达式
total = sum(x for x in numbers if x > 0)

# 使用map和filter
result = list(map(lambda x: x * 2, filter(lambda x: x > 0, numbers)))
```

### 缓存优化

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```

**适用场景**：
- 重复计算的函数
- 计算成本高的操作
- 结果不变的查询

## 依赖管理

### requirements.txt

```
fastapi==0.100.0
uvicorn[standard]==0.23.2
pydantic>=2.0.0,<3.0.0
```

**规范**：
- 指定版本号
- 使用>=和<限制范围
- 分开生产和开发依赖

### pyproject.toml

```toml
[project]
name = "myproject"
version = "0.1.0"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.black]
line-length = 79
```

## 项目结构

### 标准结构

```
myproject/
├── myproject/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── user_service.py
│   └── models/
│       ├── __init__.py
│       └── user.py
├── tests/
│   ├── __init__.py
│   └── test_api.py
├── .gitignore
├── requirements.txt
└── README.md
```

**原则**：
- 按功能模块划分
- 保持扁平化结构
- 使用清晰的命名

## 日志记录

### 配置日志

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

**日志级别**：
- DEBUG：详细调试信息
- INFO：一般信息
- WARNING：警告信息
- ERROR：错误信息
- CRITICAL：严重错误

## 环境变量

### 使用python-dotenv

```python
from dotenv import load_dotenv
import os

load_dotenv()

database_url = os.getenv("DATABASE_URL")
api_key = os.getenv("API_KEY")
debug_mode = os.getenv("DEBUG", "false").lower() == "true"
```

**.env文件**：
```
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
API_KEY=your-api-key
DEBUG=false
```

**安全注意**：
- 将.env添加到.gitignore
- 不要提交敏感信息
- 在生产环境使用环境变量

## 并发编程

### 使用asyncio

```python
import asyncio

async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

async def main():
    results = await asyncio.gather(
        fetch_data("https://api.example.com/data1"),
        fetch_data("https://api.example.com/data2")
    )
    return results
```

### 使用线程池

```python
from concurrent.futures import ThreadPoolExecutor

def process_data(data):
    # 处理数据
    pass

with ThreadPoolExecutor(max_workers=4) as executor:
    results = executor.map(process_data, data_list)
```

## 代码审查清单

### 代码质量
- [ ] 命名清晰合理
- [ ] 注释充分准确
- [ ] 逻辑简洁明了
- [ ] 避免重复代码

### 安全性
- [ ] 输入验证
- [ ] SQL注入防护
- [ ] XSS防护
- [ ] 敏感数据保护

### 性能
- [ ] 算法复杂度合理
- [ ] 避免性能瓶颈
- [ ] 内存使用合理

### 可维护性
- [ ] 遵循编码规范
- [ ] 模块化设计
- [ ] 错误处理完善

## 总结

遵循Python最佳实践可以提高代码质量、可维护性和性能。通过持续学习和实践，可以成为一名优秀的Python开发者。