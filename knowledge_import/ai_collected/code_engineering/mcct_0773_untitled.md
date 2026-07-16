# Refactor this code to use Template Method pattern:

```python
def handle_request(req):
    if req.me
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to use Template Method pattern:

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
Refactor this code to use Template Method pattern:

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
This is a standalone snippet, so I'll show the refactored code directly.

**Template Method approach**: The base class defines the algorithm skeleton (`handle`), and subclasses override the abstract steps (`match` and `execute`).

```python
from abc import ABC, abstractmethod


class RequestHandler(ABC):
    def handle(self, req):
        if not self.match(req):
            return None
        return self.execute(req)

    @abstractmethod
    def match(self, req):
        ...

    @abstractmethod
    def execute(self, req):
        ...


class GetUsersHandler(RequestHandler):
    def match(self, req):
        return req.method == 'GET' and req.path == '/users'

    def execute(self, req):
        return get_users()


class GetPostsHandler(RequestHandler):
    def match(self, req):
        return req.method == 'GET' and req.path == '/posts'

    def execute(self, req):
        return get_posts()


class GetCommentsHandler(RequestHandler):
    def match(self, req):
        return req.method == 'GET' and req.path == '/comments'

    def execute(self, req):
        return get_comments()


class CreateUserHandler(RequestHandler):
    def match(self, req):
        return req.method == 'POST' and req.path == '/users'

    def execute(self, req):
        return create_user(req.body)


class CreatePostHandler(RequestHandler):
    def match(self, req):
        return req.method == 'POST' and req.path == '/posts'

    def execute(self, req):
        return create_post(req.body)


handlers = [
    GetUsersHandler(),
    GetPostsHandler(),
    GetCommentsHandler(),
    CreateUserHandler(),
    CreatePostHandler(),
]


def handle_request(req):
    for handler in handlers:
        result = handler.handle(req)
        if result is not None:
            return result
    return 404
```

**What changed**:

- **Template method** (`handle`) defines the algorithm: try to match, then execute — subclasses can't change this flow
- **Abstract steps** (`match`, `execute`) are overridden by each concrete handler
- `handle_request` now iterates handlers instead of nested if/elif chains — adding a new route is just a new class + appending to `handlers`
- The 404 fallback is preserved at the dispatcher level

If you have an actual file you'd like this written into, let me know the path.

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