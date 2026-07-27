from __future__ import annotations

import re

VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)

SKILL_LOAD_ERR_NO_FRONTMATTER = "no_frontmatter"
SKILL_LOAD_ERR_UNTERMINATED = "unterminated_frontmatter"
SKILL_LOAD_ERR_ENCODING = "frontmatter_encoding"
SKILL_LOAD_ERR_IO = "skill_io_error"
SKILL_LOAD_ERR_PATH_TRAVERSAL = "path_traversal_attempt"

_SKILL_LOAD_ERROR_BUFFER_MAX = 64