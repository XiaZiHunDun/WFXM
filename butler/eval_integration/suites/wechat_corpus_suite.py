"""WeChat gateway corpus eval suite (L-C)."""

from __future__ import annotations

import os

from butler.contracts.eval_ports import SuiteRunResult


class WechatCorpusSuite:
    suite_id = "wechat_corpus"
    layer = "L-C"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.ops.wechat_corpus_eval import run_and_push_wechat_corpus_eval

        if push_langfuse is None:
            push_langfuse = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in (
                "1",
                "true",
                "yes",
            )
        summary = run_and_push_wechat_corpus_eval(push_langfuse=push_langfuse)
        exit_code = int(summary.get("exit_code") or 0)
        ok = exit_code == 0
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "pass_rate": summary.get("pass_rate"),
                "passed": summary.get("passed"),
                "total": summary.get("total"),
            },
            error="" if ok else f"exit_code={exit_code}",
        )
