#!/usr/bin/env bash
# T1 head-to-head (wrapper).
exec "$(dirname "$0")/butler-head-to-head.sh" t1 "$@"
