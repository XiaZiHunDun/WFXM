"""灵文1号（LingWen1）项目 demo 文件。

用途：
- 仅用于 Butler 管家委派流程的最小可运行示例。
- 不依赖 novel-factory / runtime / docs，便于在干净环境下做冒烟测试。
- 文件可以随时清理，不属于项目正式产物。

包含两个示例函数：
- greet(name)：返回中文问候语。
- add(a, b)  ：返回两数之和。
"""

from __future__ import annotations


def greet(name: str) -> str:
    """返回中文问候语。"""
    return f"你好，{name}！欢迎使用灵文1号。"


def add(a: float, b: float) -> float:
    """返回 a + b 的结果。"""
    return a + b


def main() -> None:
    """演示入口：依次打印问候与加法结果。"""
    print(greet("主公"))
    print(greet("灵文1号"))
    print(f"add(1, 2) = {add(1, 2)}")
    print(f"add(3.5, 4.5) = {add(3.5, 4.5)}")


if __name__ == "__main__":
    main()
