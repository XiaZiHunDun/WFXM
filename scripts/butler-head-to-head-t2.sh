#!/usr/bin/env bash
# T2 head-to-head: butler-style logic bug vs CC CLI.
exec "$(dirname "$0")/butler-head-to-head.sh" t2 "$@"
