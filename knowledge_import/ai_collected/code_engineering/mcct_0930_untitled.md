# Create a systemd service file for a Django application with proper restart policies.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Create a systemd service file for a Django application with proper restart policies.

## Conversation
### Turn 1 (user)
Create a systemd service file for a Django application with proper restart policies.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/django-app.service",
  "content": "[Unit]\nDescription=Django Application\nAfter=network.target postgresql.service\nWants=postgresql.service\n\n[Service]\nType=notify\nUser=www-data\nGroup=www-data\nWorkingDirectory=/opt/django-app\nExecStart=/opt/django-app/venv/bin/gunicorn \\\n    --workers 3 \\\n    --bind unix:/run/django-app/gunicorn.sock \\\n    myproject.wsgi:application\nExecReload=/bin/kill -s HUP $MAINPID\n\n# Restart policy\nRestart=on-failure\
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/django-app.service (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
Created `django-app.service`. Key configuration:

**Restart policy:**
- `Restart=on-failure` — auto-restarts on non-zero exit (crashes, segfaults) but not on clean stop
- `RestartSec=5` — 5-second delay between restarts to avoid tight crash loops
- `StartLimitBurst=5` within `StartLimitIntervalSec=60` — max 5 restarts per minute, then systemd stops trying

**Dependencies:**
- `After=network.target postgresql.service` — waits for network and DB before starting
- `Wants=postgresql.service` — suggests (but doesn't require) PostgreSQL

**Security hardening:**
- `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true` — limits filesystem/process access
- Runs as `www-data` user/group

**To use:** adjust `WorkingDirectory`, `ExecStart` path, socket path, project name (`myproject.wsgi`), and `.env` location to match your setup. Install with:

```bash
sudo cp django-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now django-app
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