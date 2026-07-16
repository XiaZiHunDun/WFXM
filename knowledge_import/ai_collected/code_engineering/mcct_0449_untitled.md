# Write a Python function that merges multiple Parquet files based on a common key column.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python function that merges multiple Parquet files based on a common key column.

## Conversation
### Turn 1 (user)
Write a Python function that merges multiple Parquet files based on a common key column.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/merge_parquet.py",
  "content": "from pathlib import Path\n\nimport pandas as pd\n\n\ndef merge_parquet_files(\n    file_paths: list[str | Path],\n    key_column: str,\n    how: str = \"inner\",\n    output_path: str | Path | None = None,\n) -> pd.DataFrame:\n    \"\"\"Merge multiple Parquet files on a common key column.\n\n    Args:\n        file_paths: Paths to the Parquet files to merge.\n        key_column: Column name present in every file to merge on
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/merge_parquet.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/merge_parquet.py",
  "content": "from pathlib import Path\n\nimport pandas as pd\n\n\ndef merge_parquet_files(\n    file_paths: list[str | Path],\n    key_column: str,\n    how: str = \"inner\",\n    output_path: str | Path | None = None,\n) -> pd.DataFrame:\n    \"\"\"Merge multiple Parquet files on a common key column.\n\n    Args:\n        file_paths: Paths to the Parquet files to merge.\n        key_column: Column name present in every file to merge on
```

### Turn 5 (tool)
The file /data/agent/choucisan/merge_parquet.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 6 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/merge_parquet.py",
  "content": "from pathlib import Path\n\nimport pandas as pd\n\n\ndef merge_parquet_files(\n    file_paths: list[str | Path],\n    key_column: str,\n    how: str = \"inner\",\n    output_path: str | Path | None = None,\n) -> pd.DataFrame:\n    \"\"\"Merge multiple Parquet files on a common key column.\n\n    Args:\n        file_paths: Paths to the Parquet files to merge.\n        key_column: Column name present in every file to merge on
```

### Turn 7 (tool)
The file /data/agent/choucisan/merge_parquet.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 8 (assistant)
Written to `merge_parquet.py`. The function:

- **`merge_parquet_files(file_paths, key_column, how, output_path)`** — reads each Parquet file, progressively merges them on the shared `key_column` using pandas `merge`, and optionally writes the result.

**Usage as a library:**

```python
from merge_parquet_files import merge_parquet_files

df = merge_parquet_files(
    ["sales.parquet", "returns.parquet", "inventory.parquet"],
    key_column="product_id",
    how="outer",          # keep all keys from every file
    output_path="merged.parquet",
)
```

**Usage from the CLI:**

```bash
python merge_parquet.py sales.parquet returns.parquet inventory.parquet \
    -k product_id --how outer -o merged.parquet
```

Key details:
- Join types: `inner` (default), `outer`, `left`, `right`, `cross` — passed through to `pd.merge`.
- Raises `KeyError` if the key column is missing from any input file.
- Raises `ValueError` if fewer than two files are provided.

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