# Write a Python function that merges multiple Excel files based on a common key column.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python function that merges multiple Excel files based on a common key column.

## Conversation
### Turn 1 (user)
Write a Python function that merges multiple Excel files based on a common key column.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/merge_excel.py",
  "content": "import pandas as pd\nfrom pathlib import Path\n\n\ndef merge_excel_files(\n    file_paths: list[str | Path],\n    key_column: str,\n    how: str = \"inner\",\n    sheet_name: str | int = 0,\n) -> pd.DataFrame:\n    \"\"\"Merge multiple Excel files on a common key column.\n\n    Args:\n        file_paths: Paths to Excel files.\n        key_column: Column name to merge on (must exist in all files).\n        how: Join type — 'in
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/merge_excel.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
The function is in `merge_excel.py`. It:

- Reads each Excel file with `pandas.read_excel`
- Validates that the key column exists in every file
- Iteratively merges all DataFrames using the specified join type (`inner`, `outer`, `left`, `right`)

**Usage:**

```python
from merge_excel import merge_excel_files

df = merge_excel_files(
    file_paths=["sales.xlsx", "inventory.xlsx", "customers.xlsx"],
    key_column="product_id",
    how="left",
)
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