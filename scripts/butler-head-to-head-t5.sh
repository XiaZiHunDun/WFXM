#!/usr/bin/env bash
# T5 head-to-head: LingWen demo logic fix vs CC CLI.
exec "$(dirname "$0")/butler-head-to-head.sh" t5 "$@"
