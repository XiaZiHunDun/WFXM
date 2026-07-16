# Write a Python function that merges multiple CSV files based on a common key column.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python function that merges multiple CSV files based on a common key column.

## Conversation
### Turn 1 (user)
Write a Python function that merges multiple CSV files based on a common key column.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/merge_csv.py",
  "content": "import pandas as pd\nfrom pathlib import Path\n\n\ndef merge_csv_files(file_paths: list[str], key_column: str, how: str = \"inner\") -> pd.DataFrame:\n    \"\"\"Merge multiple CSV files on a common key column.\n\n    Args:\n        file_paths: List of paths to CSV files.\n        key_column: Column name to merge on.\n        how: Join type — 'inner', 'outer', 'left', or 'right'.\n\n    Returns:\n        Merged DataFrame.\n    \
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/merge_csv.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
Written to `merge_csv.py`. Here's what it does:

**`merge_csv_files(file_paths, key_column, how)`**
- Reads each CSV via pandas
- Validates that `key_column` exists in every file
- Sequentially merges on that column using the specified join type (`inner`, `outer`, `left`, `right`)
- Auto-appends the source filename as a suffix when columns collide (excluding the first file)

**CLI usage:**
```bash
python merge_csv.py id inner users.csv orders.csv
```

**Programmatic usage:**
```python
from merge_csv_files import merge_csv_files

df = merge_csv_files(["users.csv", "orders.csv", "products.csv"], key_column="id", how="outer")
```

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