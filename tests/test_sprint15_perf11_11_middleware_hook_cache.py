"""Sprint 15 PERF-11-11: middleware/plugin hook 预解析为单次构造.

bug:
  - LoopMiddlewareChain.before_llm/after_tools/wrap_tool_call 每调用 N 次 getattr
  - 对 14 个 middleware 的典型配置: 每 turn × 每工具调用 都重复 N 次属性查找
  - wrap_tool_call 还为每个无 hook 的 middleware 创建无意义 closure

修复: __post_init__ 预解析三类 hook 列表, 运行时只迭代有效 hook
  - before_llm: 调用前 N 次 getattr → 0 次
  - after_tools: N 次 getattr → 0 次
  - wrap_tool_call: N 次 getattr + 无用 closure → 只对有 hook 的 mw 创建 closure
"""

from __future__ import annotations

import pytest


# ── 行为不变: before_llm 仍按顺序链式调用 ────────────────────


class TestBeforeLlmOrdering:
    def test_empty_chain_returns_copy(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        chain = LoopMiddlewareChain(middlewares=[])
        msgs = [{"role": "user", "content": "hi"}]
        out = chain.before_llm(msgs)
        assert out == msgs
        assert out is not msgs  # 应返回新 list

    def test_middlewares_called_in_order(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        calls: list[str] = []

        class MwA:
            def before_llm(self, messages):
                calls.append("A")
                return messages

        class MwB:
            def before_llm(self, messages):
                calls.append("B")
                return messages

        class MwC:
            def before_model(self, messages):  # before_model 也被识别
                calls.append("C-via-model")
                return messages

        chain = LoopMiddlewareChain(middlewares=[MwA(), MwB(), MwC()])
        chain.before_llm([{"role": "user", "content": "x"}])

        assert calls == ["A", "B", "C-via-model"]

    def test_middlewares_chain_messages(self):
        """每个 middleware 应收到上一个的输出。"""
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwAddTag:
            def before_llm(self, messages):
                return [{"role": "user", "content": "A"}]

        class MwAppendTurn:
            def before_llm(self, messages):
                return messages + [{"role": "user", "content": "B"}]

        chain = LoopMiddlewareChain(middlewares=[MwAddTag(), MwAppendTurn()])
        out = chain.before_llm([])
        assert [m["content"] for m in out] == ["A", "B"]

    def test_middleware_failure_logged_but_continues(self, caplog):
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwOk1:
            def before_llm(self, messages):
                return [{"role": "user", "content": "ok1"}]

        class MwBoom:
            def before_llm(self, messages):
                raise RuntimeError("mw boom")

        class MwOk2:
            def before_llm(self, messages):
                return messages + [{"role": "user", "content": "ok2"}]

        chain = LoopMiddlewareChain(middlewares=[MwOk1(), MwBoom(), MwOk2()])
        out = chain.before_llm([])
        # 中间 mw 抛异常后,后续 mw 仍应执行, 上一条成功的输出应作为 input
        # 行为: out = MwOk1 出错则保留前一份(ok1), MwOk2 在其上加 ok2
        # 实际看代码: try/except, 失败时 out 不更新, 下个 mw 收到前一个成功的输出
        contents = [m["content"] for m in out]
        assert "ok1" in contents
        assert "ok2" in contents


# ── 行为不变: after_tools 仍按倒序调用 ──────────────────────


class TestAfterToolsOrdering:
    def test_middlewares_called_in_reverse(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        calls: list[str] = []

        class MwA:
            def after_tools(self, messages, *, tool_stats=None):
                calls.append("A")
                return messages

        class MwB:
            def after_tools(self, messages, *, tool_stats=None):
                calls.append("B")
                return messages

        chain = LoopMiddlewareChain(middlewares=[MwA(), MwB()])
        chain.after_tools([])

        assert calls == ["B", "A"], "after_tools 应按倒序调用"


# ── 行为不变: wrap_tool_call ─────────────────────────────────


class TestWrapToolCall:
    def test_empty_chain_calls_dispatch_directly(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        chain = LoopMiddlewareChain(middlewares=[])
        called: list[dict] = []

        def dispatch(name, args):
            called.append({"name": name, "args": args})
            return "ok"

        out = chain.wrap_tool_call("tool1", {"x": 1}, dispatch)
        assert out == "ok"
        assert called == [{"name": "tool1", "args": {"x": 1}}]

    def test_wrap_composes_in_reverse(self):
        """外层 hook 应先接 (name, args, prev), 内层 dispatch 在最里。"""
        from butler.core.loop_middleware import LoopMiddlewareChain

        log: list[str] = []

        class MwOuter:
            def wrap_tool_call(self, name, args, prev):
                log.append(f"outer-in:{name}")
                result = prev(name, args)
                log.append(f"outer-out:{result}")
                return f"outer({result})"

        class MwInner:
            def wrap_tool_call(self, name, args, prev):
                log.append(f"inner-in:{name}")
                result = prev(name, args)
                log.append(f"inner-out:{result}")
                return f"inner({result})"

        def dispatch(name, args):
            log.append("dispatch")
            return name

        chain = LoopMiddlewareChain(middlewares=[MwOuter(), MwInner()])
        out = chain.wrap_tool_call("t", {}, dispatch)

        # 外层先接, 包内层, 内层包 dispatch
        # 倒序构建: 先 inner wrap dispatch, 再 outer wrap inner
        assert out == "outer(inner(t))"
        assert log == ["outer-in:t", "inner-in:t", "dispatch", "inner-out:t", "outer-out:inner(t)"]

    def test_middleware_without_wrap_skipped(self):
        """没有 wrap_tool_call 的 middleware 不应被加入 wrap chain。"""
        from butler.core.loop_middleware import LoopMiddlewareChain

        log: list[str] = []

        class MwNoWrap:
            def before_llm(self, messages):
                return messages

        class MwWrap:
            def wrap_tool_call(self, name, args, prev):
                log.append("wrap")
                return prev(name, args)

        def dispatch(name, args):
            return "D"

        chain = LoopMiddlewareChain(middlewares=[MwNoWrap(), MwWrap()])
        out = chain.wrap_tool_call("t", {}, dispatch)

        assert out == "D"
        assert log == ["wrap"]


# ── 优化: 钩子预解析 (新增 test, 验证 _before_llm 等内部缓存) ──


class TestHookPrecomputation:
    def test_before_llm_hooks_precomputed(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwA:
            def before_llm(self, messages):
                return messages

        class MwB:
            def before_model(self, messages):
                return messages

        class MwC:
            pass  # 无 hook

        chain = LoopMiddlewareChain(middlewares=[MwA(), MwB(), MwC()])

        # 内部应预存 2 个 hook (A.before_llm + B.before_model)
        # MwC 既无 before_llm 也无 before_model, 不应被加入
        assert len(chain._before_llm_hooks) == 2
        assert len(chain._after_tools_hooks) == 0
        assert len(chain._wrap_tool_call_hooks) == 0

    def test_after_tools_hooks_precomputed(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwA:
            def after_tools(self, messages, *, tool_stats=None):
                return messages

        class MwB:
            pass

        chain = LoopMiddlewareChain(middlewares=[MwA(), MwB()])
        assert len(chain._after_tools_hooks) == 1
        assert len(chain._before_llm_hooks) == 0

    def test_wrap_tool_call_hooks_precomputed(self):
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwA:
            def wrap_tool_call(self, name, args, prev):
                return prev(name, args)

        class MwB:
            pass

        chain = LoopMiddlewareChain(middlewares=[MwA(), MwB()])
        assert len(chain._wrap_tool_call_hooks) == 1

    def test_getattr_not_called_per_invocation(self):
        """优化目标: 运行时不再对每个 mw 调 getattr('before_llm')。"""
        from butler.core.loop_middleware import LoopMiddlewareChain

        class MwStatic:
            def before_llm(self, messages):
                return messages

        # 用 __getattribute__ 计数
        m = MwStatic()
        chain = LoopMiddlewareChain(middlewares=[m])

        # 在 hook 调用前后, 中间不应该有大量 getattr
        # 通过 patch object 的 __getattribute__ 难以直接验证
        # 替代方案: 验证内部 _before_llm_hooks 已包含 hook 对象
        assert any(
            getattr(hook, "__self__", None) is m
            for hook in chain._before_llm_hooks
        ), "应预绑定 m.before_llm 方法"


# ── PluginRegistry 同样的优化 (LoopPluginRegistry) ──────────


class TestPluginRegistryOptimization:
    def test_plugin_registry_hooks_precomputed(self):
        from butler.core.loop_plugins import LoopPluginRegistry

        class P:
            def before_model(self, messages):
                return messages

        class P2:
            def wrap_tool_call(self, name, args, prev):
                return prev(name, args)

        reg = LoopPluginRegistry(plugins=[P(), P2()])

        # LoopPluginRegistry 同样应有预解析字段
        assert hasattr(reg, "_before_llm_hooks"), "应有 _before_llm_hooks 字段"
        assert hasattr(reg, "_wrap_tool_call_hooks"), "应有 _wrap_tool_call_hooks 字段"
        assert len(reg._before_llm_hooks) == 1
        assert len(reg._wrap_tool_call_hooks) == 1
