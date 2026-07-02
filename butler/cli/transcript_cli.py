"""CLI: ``butler transcript index --rebuild``."""

from __future__ import annotations

import argparse


def register_transcript_parser(sub: argparse._SubParsersAction) -> None:
    transcript = sub.add_parser("transcript", help="会话 transcript 索引维护")
    sp = transcript.add_subparsers(dest="transcript_cmd", required=True)

    idx = sp.add_parser("index", help="重建 transcript FTS 索引")
    idx.add_argument("--rebuild", action="store_true", help="清空并全量重建")
    idx.set_defaults(func=_cmd_index_rebuild)


def _cmd_index_rebuild(ns: argparse.Namespace) -> int:
    from butler.core.transcript_fts import rebuild_all_transcripts

    stats = rebuild_all_transcripts()
    print(
        f"FTS rebuild done: sessions={stats.get('sessions', 0)} "
        f"lines={stats.get('lines', 0)}"
    )
    return 0
