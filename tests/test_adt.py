"""测试 butler.core.adt 模块的代数数据类型。

覆盖:
- Either/Left/Right 构造与方法 (map_right, map_left, flat_map, is_left, is_right)
- TaggedUnion 基类 (match, fold)
- Record (to_dict, from_dict, merge)
- traverse_either / partition_eithers
- Either 类型收窄
- Left/Right 相等性
- 链式操作 (map + flat_map + match)
"""

from __future__ import annotations

import pytest

from butler.core.adt import (
    Either,
    Left,
    Right,
    left,
    right,
    TaggedUnion,
    Record,
    match_either,
    traverse_either,
    partition_eithers,
)


# ---------------------------------------------------------------------------
# Either / Left / Right 构造
# ---------------------------------------------------------------------------


class TestEitherConstruction:
    """测试 Left 和 Right 的构造方式。"""

    def test_left_direct_construction(self):
        """直接构造 Left 值。"""
        l = Left(42)
        assert l.is_left()
        assert not l.is_right()
        assert l.left_value == 42
        assert l.tag == "left"

    def test_right_direct_construction(self):
        """直接构造 Right 值。"""
        r = Right(100)
        assert r.is_right()
        assert not r.is_left()
        assert r.right_value == 100
        assert r.tag == "right"

    def test_left_helper_function(self):
        """通过辅助函数 left() 构造。"""
        l = left("error msg")
        assert isinstance(l, Left)
        assert l.left_value == "error msg"

    def test_right_helper_function(self):
        """通过辅助函数 right() 构造。"""
        r = right(3.14)
        assert isinstance(r, Right)
        assert r.right_value == 3.14

    def test_left_value_is_none_when_right(self):
        """Right 的 left_value 属性返回 None。"""
        r = Right(42)
        assert r.left_value is None

    def test_right_value_is_none_when_left(self):
        """Left 的 right_value 属性返回 None。"""
        l = Left("err")
        assert l.right_value is None

    def test_left_accepts_none_value(self):
        """Left 可以接受 None 作为值。"""
        l = Left(None)
        assert l.is_left()
        assert l.left_value is None

    def test_right_accepts_complex_value(self):
        """Right 可以接受复杂对象作为值。"""
        data = {"key": [1, 2, 3]}
        r = Right(data)
        assert r.right_value == data


# ---------------------------------------------------------------------------
# Either 方法: is_left, is_right, map_right, map_left, flat_map
# ---------------------------------------------------------------------------


class TestEitherMethods:
    """测试 Either 上的各种方法。"""

    def test_is_left_true(self):
        """Left.is_left() 返回 True。"""
        assert Left(1).is_left() is True

    def test_is_left_false_for_right(self):
        """Right.is_left() 返回 False。"""
        assert Right(1).is_left() is False

    def test_is_right_true(self):
        """Right.is_right() 返回 True。"""
        assert Right(1).is_right() is True

    def test_is_right_false_for_left(self):
        """Left.is_right() 返回 False。"""
        assert Left(1).is_right() is False

    def test_map_right_transforms_value(self):
        """map_right 在 Right 上转换值。"""
        r = Right(5)
        result = r.map_right(lambda x: x * 2)
        assert result.is_right()
        assert result.right_value == 10

    def test_map_right_preserves_left(self):
        """map_right 在 Left 上不改变值。"""
        l: Either[str, int] = Left("error")
        result = l.map_right(lambda x: x * 2)
        assert result.is_left()
        assert l.left_value == "error"

    def test_map_left_transforms_value(self):
        """map_left 在 Left 上转换值。"""
        l: Either[str, int] = Left("bad")
        result = l.map_left(lambda s: s.upper())
        assert result.is_left()
        assert result.left_value == "BAD"

    def test_map_left_preserves_right(self):
        """map_left 在 Right 上不改变值。"""
        r: Either[str, int] = Right(42)
        result = r.map_left(lambda s: s.upper())
        assert result.is_right()
        assert result.right_value == 42

    def test_flat_map_returns_right_from_function(self):
        """flat_map 在 Right 上应用函数并返回新的 Either。"""
        r = Right(5)

        def check_positive(x: int) -> Either[str, int]:
            if x > 0:
                return Right(x * 10)
            return Left("not positive")

        result = r.flat_map(check_positive)
        assert result.is_right()
        assert result.right_value == 50

    def test_flat_map_returns_left_from_function(self):
        """flat_map 在 Right 上函数返回 Left 时正确传递。"""
        r = Right(-3)

        def check_positive(x: int) -> Either[str, int]:
            if x > 0:
                return Right(x * 10)
            return Left("not positive")

        result = r.flat_map(check_positive)
        assert result.is_left()
        assert result.left_value == "not positive"

    def test_flat_map_preserves_left(self):
        """flat_map 在 Left 上直接返回自身。"""
        l: Either[str, int] = Left("initial error")
        result = l.flat_map(lambda x: Right(x * 2))  # type: ignore[arg-type]
        assert result.is_left()
        assert l.left_value == "initial error"


# ---------------------------------------------------------------------------
# TaggedUnion 基类
# ---------------------------------------------------------------------------


class TestTaggedUnion:
    """测试 TaggedUnion 的 match 和 fold 方法。"""

    def test_match_with_correct_handler(self):
        """match 能正确匹配对应 tag 的处理器。"""
        result = Right(42)
        matched = result.match(
            left=lambda value: f"Left: {value}",
            right=lambda value: f"Right: {value}",
        )
        assert matched == "Right: 42"

    def test_match_with_left_handler(self):
        """match 在 Left 上匹配 left 处理器。"""
        result = Left("error")
        matched = result.match(
            left=lambda value: f"Left: {value}",
            right=lambda value: f"Right: {value}",
        )
        assert matched == "Left: error"

    def test_match_raises_on_missing_handler(self):
        """match 在缺少对应 tag 的处理器时抛出 ValueError。"""
        result = Right(42)
        with pytest.raises(ValueError, match="No handler for variant"):
            result.match(left=lambda value: f"Left: {value}")

    def test_match_passes_fields_except_tag(self):
        """match 将除 tag 之外的字段作为命名参数传递。"""
        from dataclasses import dataclass

        class MyUnion(TaggedUnion):
            pass

        @dataclass
        class VariantA(MyUnion):
            tag: str = "a"
            name: str = ""
            count: int = 0

        @dataclass
        class VariantB(MyUnion):
            tag: str = "b"
            value: float = 0.0

        a = VariantA(name="test", count=5)
        result = a.match(a=lambda name, count: f"{name}:{count}")
        assert result == "test:5"

    def test_fold_with_right_number_of_handlers(self):
        """fold 使用正确数量的处理器 (Either 子类需要 3 个)。"""
        result = Right(99)
        # _variant_index 对 Right 返回 2，需要至少 3 个处理器
        folded = result.fold(
            lambda r: "ignored 0",
            lambda r: "ignored 1",
            lambda r: r.right_value * 2,
        )
        assert folded == 198

    def test_fold_raises_on_missing_index(self):
        """fold 在处理器索引越界时抛出 ValueError。"""
        result = Right(1)
        with pytest.raises(ValueError):
            result.fold()  # 没有提供任何处理器

    def test_fold_with_simple_tagged_union(self):
        """fold 对直接继承 TaggedUnion 的简单类型使用索引 0。"""
        from dataclasses import dataclass

        @dataclass
        class Simple(TaggedUnion):
            tag: str = "simple"
            value: int = 0

        s = Simple(value=42)
        # Simple -> TaggedUnion -> object, TaggedUnion 在索引1, _variant_index 返回 0
        folded = s.fold(lambda x: x.value + 1)
        assert folded == 43


# ---------------------------------------------------------------------------
# Record 类型
# ---------------------------------------------------------------------------


class TestRecord:
    """测试 Record 的 to_dict, from_dict, merge 方法。"""

    def test_to_dict(self):
        """to_dict 将 Record 转换为字典。"""
        from dataclasses import dataclass

        @dataclass
        class Point(Record):
            x: float
            y: float

        p = Point(3.0, 4.0)
        d = p.to_dict()
        assert d == {"x": 3.0, "y": 4.0}

    def test_from_dict(self):
        """from_dict 从字典创建 Record。"""
        from dataclasses import dataclass

        @dataclass
        class Point(Record):
            x: float
            y: float

        p = Point.from_dict({"x": 1.0, "y": 2.0})
        assert p.x == 1.0
        assert p.y == 2.0

    def test_merge(self):
        """merge 合并两个 Record,后者优先。"""
        from dataclasses import dataclass

        @dataclass
        class Config(Record):
            timeout: int = 30
            retries: int = 3
            verbose: bool = False

        base = Config(timeout=30, retries=3, verbose=False)
        override = Config(verbose=True)
        merged = base.merge(override)
        assert merged.timeout == 30
        assert merged.retries == 3
        assert merged.verbose is True

    def test_merge_with_empty_record(self):
        """merge 与空 Record 合并时保持原值。"""
        from dataclasses import dataclass

        @dataclass
        class Data(Record):
            value: str = "default"

        base = Data(value="original")
        override = Data()
        merged = base.merge(override)
        assert merged.value == "default"

    def test_from_dict_returns_same_class(self):
        """from_dict 返回的实例与原类相同。"""
        from dataclasses import dataclass

        @dataclass
        class Point(Record):
            x: float
            y: float

        p = Point.from_dict({"x": 5.0, "y": 6.0})
        assert isinstance(p, Point)


# ---------------------------------------------------------------------------
# traverse_either / partition_eithers
# ---------------------------------------------------------------------------


class TestTraverseEither:
    """测试 traverse_either 和 partition_eithers。"""

    def test_traverse_all_rights(self):
        """traverse_either 在全部为 Right 时返回包含所有值的 Right。"""
        eithers: list[Either[str, int]] = [
            Right(1),
            Right(2),
            Right(3),
        ]
        result = traverse_either(eithers)
        assert result.is_right()
        assert result.right_value == [1, 2, 3]

    def test_traverse_returns_first_left(self):
        """traverse_either 在遇到第一个 Left 时返回该 Left。"""
        eithers: list[Either[str, int]] = [
            Right(1),
            Left("error #2"),
            Right(3),
        ]
        result = traverse_either(eithers)
        assert result.is_left()
        assert result.left_value == "error #2"

    def test_traverse_empty_list(self):
        """traverse_either 对空列表返回空列表的 Right。"""
        result = traverse_either([])
        assert result.is_right()
        assert result.right_value == []

    def test_partition_mixed(self):
        """partition_eithers 将混合列表分离为 lefts 和 rights。"""
        eithers: list[Either[str, int]] = [
            Right(1),
            Left("err1"),
            Right(2),
            Left("err2"),
            Right(3),
        ]
        lefts, rights = partition_eithers(eithers)
        assert lefts == ["err1", "err2"]
        assert rights == [1, 2, 3]

    def test_partition_all_lefts(self):
        """partition_eithers 全为 Left 时 rights 为空。"""
        eithers: list[Either[str, int]] = [
            Left("a"),
            Left("b"),
        ]
        lefts, rights = partition_eithers(eithers)
        assert lefts == ["a", "b"]
        assert rights == []

    def test_partition_all_rights(self):
        """partition_eithers 全为 Right 时 lefts 为空。"""
        eithers: list[Either[str, int]] = [
            Right(10),
            Right(20),
        ]
        lefts, rights = partition_eithers(eithers)
        assert lefts == []
        assert rights == [10, 20]

    def test_partition_empty_list(self):
        """partition_eithers 对空列表返回两个空列表。"""
        lefts, rights = partition_eithers([])
        assert lefts == []
        assert rights == []


# ---------------------------------------------------------------------------
# Either 类型收窄
# ---------------------------------------------------------------------------


class TestEitherTypeNarrowing:
    """测试 Either 的类型收窄能力。"""

    def test_is_left_narrowing(self):
        """通过 is_left() 进行类型收窄。"""
        value: Either[str, int] = Left("error")
        if value.is_left():
            # 此时 value 应该是 Left 类型
            assert value.left_value == "error"
            assert isinstance(value, Left)

    def test_is_right_narrowing(self):
        """通过 is_right() 进行类型收窄。"""
        value: Either[str, int] = Right(42)
        if value.is_right():
            assert value.right_value == 42
            assert isinstance(value, Right)

    def test_left_value_returns_none_for_right(self):
        """Right 的 left_value 总是 None。"""
        r: Either[str, int] = Right(10)
        assert r.left_value is None

    def test_right_value_returns_none_for_left(self):
        """Left 的 right_value 总是 None。"""
        l: Either[str, int] = Left("err")
        assert l.right_value is None


# ---------------------------------------------------------------------------
# Left / Right 相等性
# ---------------------------------------------------------------------------


class TestEitherEquality:
    """测试 Left 和 Right 的相等性比较。"""

    def test_left_equality_same_value(self):
        """两个 Left 具有相同值时相等。"""
        assert Left(42) == Left(42)

    def test_left_equality_different_value(self):
        """两个 Left 具有不同值时不相等。"""
        assert Left(42) != Left(99)

    def test_right_equality_same_value(self):
        """两个 Right 具有相同值时相等。"""
        assert Right("ok") == Right("ok")

    def test_right_equality_different_value(self):
        """两个 Right 具有不同值时不相等。"""
        assert Right("a") != Right("b")

    def test_left_not_equal_to_right(self):
        """Left 和 Right 即使值相同也不相等。"""
        assert Left(42) != Right(42)

    def test_left_equality_complex_values(self):
        """Left 对复杂值也能正确比较。"""
        assert Left([1, 2, 3]) == Left([1, 2, 3])
        assert Left({"a": 1}) == Left({"a": 1})

    def test_right_equality_complex_values(self):
        """Right 对复杂值也能正确比较。"""
        assert Right({"key": "val"}) == Right({"key": "val"})


# ---------------------------------------------------------------------------
# 链式操作: map + flat_map + match
# ---------------------------------------------------------------------------


class TestChainOperations:
    """测试 Either 的链式操作组合。"""

    def test_map_then_map(self):
        """连续两次 map_right。"""
        r = Right(2)
        result = r.map_right(lambda x: x + 1).map_right(lambda x: x * 3)
        assert result.is_right()
        assert result.right_value == 9  # (2+1)*3 = 9

    def test_map_then_flat_map(self):
        """先 map_right 再 flat_map。"""
        r = Right(5)
        result = (
            r.map_right(lambda x: x * 2)
            .flat_map(lambda x: Right(x + 1))
        )
        assert result.is_right()
        assert result.right_value == 11  # 5*2+1 = 11

    def test_flat_map_chain_success(self):
        """连续 flat_map 全部成功。"""
        r = Right(10)

        def half(x: int) -> Either[str, int]:
            if x % 2 == 0:
                return Right(x // 2)
            return Left(f"{x} is odd")

        def check_positive(x: int) -> Either[str, int]:
            if x > 0:
                return Right(x)
            return Left(f"{x} is not positive")

        result = r.flat_map(half).flat_map(check_positive)
        assert result.is_right()
        assert result.right_value == 5

    def test_flat_map_chain_with_failure(self):
        """连续 flat_map 中间出现失败。"""
        r = Right(7)

        def half(x: int) -> Either[str, int]:
            if x % 2 == 0:
                return Right(x // 2)
            return Left(f"{x} is odd")

        def check_positive(x: int) -> Either[str, int]:
            if x > 0:
                return Right(x)
            return Left(f"{x} is not positive")

        result = r.flat_map(half).flat_map(check_positive)
        assert result.is_left()
        assert result.left_value == "7 is odd"

    def test_match_after_chain(self):
        """链式操作后使用 match 终结。"""
        r = Right(3)
        final = (
            r.map_right(lambda x: x * x)
            .flat_map(lambda x: Right(x + 1))
            .match(
                left=lambda value: f"Error: {value}",
                right=lambda value: f"Success: {value}",
            )
        )
        assert final == "Success: 10"  # 3*3+1 = 10

    def test_match_after_chain_with_failure(self):
        """链式操作失败后使用 match 终结。"""
        r = Right(5)

        def fail_if_big(x: int) -> Either[str, int]:
            if x > 10:
                return Left("too big")
            return Right(x)

        final = (
            r.map_right(lambda x: x * 5)  # 25
            .flat_map(fail_if_big)
            .match(
                left=lambda value: f"Error: {value}",
                right=lambda value: f"Success: {value}",
            )
        )
        assert final == "Error: too big"

    def test_map_left_chain(self):
        """Left 上连续 map_left。"""
        l: Either[str, int] = Left("error")
        result = l.map_left(lambda s: s.upper()).map_left(lambda s: s + "!")
        assert result.is_left()
        assert result.left_value == "ERROR!"

    def test_match_either_convenience(self):
        """使用 match_either 便捷函数。"""
        r = Right(42)
        result = match_either(
            r,
            left_fn=lambda e: f"Left: {e}",
            right_fn=lambda v: v * 10,
        )
        assert result == 420

    def test_match_either_with_defaults(self):
        """match_either 使用默认值。"""
        l: Either[str, int] = Left("err")
        result = match_either(l, default_left=-1)
        assert result == -1

    def test_match_either_raises_without_handler(self):
        """match_either 在无处理器且无默认值时抛出异常。"""
        r = Right(42)
        with pytest.raises(ValueError, match="No handler for Right variant"):
            match_either(r, left_fn=lambda e: e)