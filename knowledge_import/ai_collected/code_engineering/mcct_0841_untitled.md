# Refactor this code to be more composable:

```python
def handle_request(req):
    if req.method == '
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to be more composable:

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
Refactor this code to be more composable:

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
```python
ROUTES = {}

def route(method, path):
    def decorator(fn):
        ROUTES[(method, path)] = fn
        return fn
    return decorator

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

def handle_request(req):
    handler = ROUTES.get((req.method, req.path))
    if handler is None:
        return 404
    if req.method == 'POST':
        return handler(req.body)
    return handler()
```

**What changed:**

- Replaced the nested if/elif chain with a `ROUTES` dictionary keyed by `(method, path)` tuples — O(1) lookup instead of linear branching.
- Added a `@route` decorator so each handler self-registers. Adding a new endpoint is one decorated function, not another `elif` clause.
- `handle_request` is now a thin dispatcher that doesn't need to know about individual routes.

This is the same pattern most lightweight frameworks (Flask, FastAPI) use. Each handler is independently testable and adding routes never touches the dispatcher.

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