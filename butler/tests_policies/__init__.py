"""Static analysis policies for tests/.

This package holds AST-based policy scanners that enforce code quality
in the test suite. Each policy lives in its own module with a
``scan_*`` API and a CLI entry point. Sprint 23 TST-10-6 introduces
``scan_magicmock_spec`` — see that module for details.
"""
