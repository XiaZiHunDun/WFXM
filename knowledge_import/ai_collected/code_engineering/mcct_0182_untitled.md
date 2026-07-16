# Implement a Python class called `MetricsCollector` that allows subscribing to and emitting events wi
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Implement a Python class called `MetricsCollector` that allows subscribing to and emitting events with wildcard support. It should support: add_weighted_edge, shortest_path, and minimum_spanning_tree. Include type hints and docstrings.

## Conversation
### Turn 1 (user)
Implement a Python class called `MetricsCollector` that allows subscribing to and emitting events with wildcard support. It should support: add_weighted_edge, shortest_path, and minimum_spanning_tree. Include type hints and docstrings.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/metrics_collector.py",
  "content": "\"\"\"MetricsCollector: Event-driven graph metrics with wildcard subscriptions.\"\"\"\n\nfrom __future__ import annotations\n\nimport heapq\nfrom collections import defaultdict\nfrom fnmatch import fnmatch\nfrom typing import Any, Callable\n\n\nclass MetricsCollector:\n    \"\"\"Collects weighted graph metrics and emits events with wildcard support.\n\n    Supports subscribing to events using fnmatch-style wildcards (e.
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/metrics_collector.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
Let me verify it works with a quick smoke test.
**Tool**: `Bash`
```json
{
  "command": "python3 -c \"\nfrom metrics_collector import MetricsCollector\n\nmc = MetricsCollector()\n\n# Test event system\nlog = []\nmc.subscribe('edge.*', lambda **kw: log.append(kw))\nmc.emit('edge.added', u='A', v='B', weight=3)\nassert len(log) == 1\n\n# Test wildcard doesn't match unrelated events\nmc.emit('path.found', source='A', target='B', cost=3, path=['A','B'])\nassert len(log) == 1  # still 1\n\n# Test graph operations\nmc2 = MetricsCollector()\nevents = []\nmc2.subscribe('*', 
```

### Turn 5 (tool)
Shortest path A->D: ['A', 'B', 'C', 'D'], cost=4.0
MST edges: [('A', 'B', 1), ('C', 'D', 1), ('B', 'C', 2)]
Events emitted: 6
All tests passed.

### Turn 6 (assistant)
All tests pass. Here's what's in `metrics_collector.py`:

**Event system**
- `subscribe(pattern, callback)` — register a callback for events matching an fnmatch pattern (e.g., `"edge.*"`, `"*"`)
- `unsubscribe(pattern, callback)` — remove a specific callback
- `emit(event, **kwargs)` — fire an event, invoking all matching subscribers

**Graph algorithms**
- `add_weighted_edge(u, v, weight)` — add an undirected edge (rejects negative weights)
- `shortest_path(source, target)` — Dijkstra's algorithm, returns `(path, cost)`
- `minimum_spanning_tree()` — Kruskal's algorithm with Union-Find, returns list of `(u, v, weight)` edges

Each graph operation automatically emits an event (`edge.added`, `path.found`, `mst.computed`) that subscribers can react to.

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