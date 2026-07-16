# Refactor this code to be more readable:

```python
def handle_request(req):
    if req.method == 'GE
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to be more readable:

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
Refactor this code to be more readable:

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
Here's a cleaner approach using a routing table:

```python
ROUTES = {
    ('GET', '/users'): lambda req: get_users(),
    ('GET', '/posts'): lambda req: get_posts(),
    ('GET', '/comments'): lambda req: get_comments(),
    ('POST', '/users'): lambda req: create_user(req.body),
    ('POST', '/posts'): lambda req: create_post(req.body),
}

def handle_request(req):
    handler = ROUTES.get((req.method, req.path))
    if handler:
        return handler(req)
    return 404
```

This eliminates the nested conditionals and makes adding new routes a single-line change.

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