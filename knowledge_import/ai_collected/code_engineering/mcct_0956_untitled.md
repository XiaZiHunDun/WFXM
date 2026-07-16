# Write a Python function that finds the maximum flow in a network using Ford-Fulkerson. Save to max_f
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python function that finds the maximum flow in a network using Ford-Fulkerson. Save to max_flow.py.

## Conversation
### Turn 1 (user)
Write a Python function that finds the maximum flow in a network using Ford-Fulkerson. Save to max_flow.py.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/max_flow.py",
  "content": "from collections import deque\n\n\ndef ford_fulkerson(graph, source, sink):\n    \"\"\"Find the maximum flow from source to sink in a flow network.\n\n    Args:\n        graph: Adjacency matrix where graph[u][v] is the capacity of edge u->v.\n        source: Source vertex index.\n        sink: Sink vertex index.\n\n    Returns:\n        The value of the maximum flow.\n    \"\"\"\n    n = len(graph)\n    residual = [row[:] for ro
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/max_flow.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
Saved to `max_flow.py`. The implementation uses the Edmonds-Karp variant (BFS for augmenting paths), which guarantees O(VE^2) time complexity. The `ford_fulkerson(graph, source, sink)` function takes an adjacency matrix of capacities and returns the max flow value. The `__main__` block runs a classic 6-node example that should output `23`.

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