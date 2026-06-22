"""CLI for G1-13 secrets contract check."""

from __future__ import annotations

import argparse
import json
import sys

from butler.ops.secrets_contract import (
    check_all_secrets_contracts,
    detect_gateway_expected,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Butler secrets contract check (G1-13)")
    parser.add_argument(
        "--gateway-expected",
        action="store_true",
        help="Treat gateway as required (WeChat token hard checks)",
    )
    parser.add_argument(
        "--no-gateway-detect",
        action="store_true",
        help="Do not auto-detect systemd butler-gateway.service",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--no-extensions",
        action="store_true",
        help="Skip .butler/extensions manifest secrets",
    )
    args = parser.parse_args(argv)

    gateway = bool(args.gateway_expected)
    if not args.no_gateway_detect:
        gateway = gateway or detect_gateway_expected()

    report = check_all_secrets_contracts(
        gateway_expected=gateway,
        include_extensions=not args.no_extensions,
    )

    if args.json:
        payload = report.to_dict()
        payload["gateway_expected"] = gateway
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        scope = "gateway+extensions" if gateway else "extensions+platform"
        print(f"secrets-contract check ({scope})")
        for ext_id in report.extension_ids:
            print(f"  [ext] {ext_id}")
        for err in report.errors:
            print(f"  [fail] {err}")
        for warn in report.warnings:
            print(f"  [warn] {warn}")
        print(
            f"summary: ok={1 if report.ok else 0} "
            f"errors={len(report.errors)} warnings={len(report.warnings)}"
        )

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
