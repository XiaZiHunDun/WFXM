# Restructure this code to follow open/closed principle:

```python
def handle_request(req):
    if re
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow open/closed principle:

```python
def handle_request(req):
    if req.method == 'GET':
        if req.path == '/users':
            return get_users()
        elif req.path == '/posts':
            return get_posts()
        elif req.path == '/comments':
            return get_comments()
    elif req.method == 'POST':
        if req.path == '/users':
            return create_user(req.body)
        elif req.path == '/posts':
            return create_post(req.body)
    return 404
```

## Conversation
### Turn 1 (user)
Restructure this code to follow open/closed principle:

```python
def handle_request(req):
    if req.method == 'GET':
        if req.path == '/users':
            return get_users()
        elif req.path == '/posts':
            return get_posts()
        elif req.path == '/comments':
            return get_comments()
    elif req.method == 'POST':
        if req.path == '/users':
            return create_user(req.body)
        elif req.path == '/posts':
            return create_post(req.body)
    return 404
```

### Turn 2 (assistant)
The code violates OCP because adding a new route requires modifying `handle_request`. Here's a registry-based approach:
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/router.py",
  "content": "from functools import wraps\n\n# Registry: maps (method, path) -> handler\n_routes = {}\n\n\ndef route(method, path):\n    \"\"\"Register a handler for a method/path combination.\"\"\"\n    def decorator(func):\n        _routes[(method, path)] = func\n        @wraps(func)\n        def wrapper(*args, **kwargs):\n            return func(*args, **kwargs)\n        return wrapper\n    return decorator\n\n\ndef handle_request(req):\n   
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
Here's the restructured code following OCP — `handle_request` is closed for modification, and new routes are added by decorating new functions:

```python
from functools import wraps

# Registry: maps (method, path) -> handler
_routes = {}


def route(method, path):
    """Register a handler for a method/path combination."""
    def decorator(func):
        _routes[(method, path)] = func
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def handle_request(req):
    handler = _routes.get((req.method, req.path))
    if handler is None:
        return 404
    return handler(req.body) if req.method == 'POST' else handler()


# --- Handlers (add new routes here without touching handle_request) ---

@route('GET', '/users')
def get_users():
    ...

@route('GET', '/posts')
def get_posts():
    ...

@route('GET', '/comments')
def get_comments():
    ...

@route('POST', '/users')
def create_user(body):
    ...

@route('POST', '/posts')
def create_post(body):
    ...
```

**What changed:**

- **Before:** Adding a route meant editing `handle_request` (modifying the closed part).
- **After:** `handle_request` is a generic dispatcher — it never changes. New routes are added by defining a new function and decorating it with `@route(method, path)`. The system is open for extension (new routes) but closed for modification (no existing code changes needed).

The `POST` handler signature distinction (`body` arg) is a minor asymmetry — if that bothers you, all handlers could uniformly accept `(req)` and extract what they need.

## Available Tools
- **Bash**: Run a shell command.
- **BashOutput**: Read output from a running background shell command.
- **Edit**: Replace text in an existing file.
- **Glob**: Find files by glob pattern.
- **Grep**: Search file contents by pattern.
- **KillBash**: Stop a running background shell command.
- **LS**: List files and directories.
- **MultiEdit**: Apply multiple text replacements to one file.
- **NotebookEdit**: Edit a Jupyter notebook cell.
- **NotebookRead**: Read a Jupyter notebook.

## Execution Trace