"""Butler skill lifecycle: flat `name.md` files with YAML frontmatter.

Deprecated: Use `butler.skills.manager` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.skills.manager module is deprecated, "
    "use butler.skills.manager package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.skills.manager import (
    SKILL_LOAD_ERR_ENCODING,
    SKILL_LOAD_ERR_IO,
    SKILL_LOAD_ERR_NO_FRONTMATTER,
    SKILL_LOAD_ERR_PATH_TRAVERSAL,
    SKILL_LOAD_ERR_UNTERMINATED,
    SkillLoadError,
    SkillManager,
    recent_skill_load_errors,
    _clear_recent_skill_load_errors,
    _parse_skill_md,
    _read_frontmatter_only,
)

__all__ = [
    "SKILL_LOAD_ERR_NO_FRONTMATTER",
    "SKILL_LOAD_ERR_UNTERMINATED",
    "SKILL_LOAD_ERR_ENCODING",
    "SKILL_LOAD_ERR_IO",
    "SKILL_LOAD_ERR_PATH_TRAVERSAL",
    "SkillLoadError",
    "SkillManager",
    "recent_skill_load_errors",
    "_clear_recent_skill_load_errors",
    "_parse_skill_md",
    "_read_frontmatter_only",
]
