# Write a bash script to automate monitors application health and restarts unhealthy services with rol
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a bash script to automate monitors application health and restarts unhealthy services with rollback support.

## Conversation
### Turn 1 (user)
Write a bash script to automate monitors application health and restarts unhealthy services with rollback support.

### Turn 2 (assistant)
**Tool**: `EnterPlanMode`

### Turn 3 (tool)
Entered plan mode. You should now focus on exploring the codebase and designing an implementation approach.

In plan mode, you should:
1. Thoroughly explore the codebase to understand existing patterns
2. Identify similar features and architectural approaches
3. Consider multiple approaches and their trade-offs
4. Use AskUserQuestion if you need to clarify the approach
5. Design a concrete implementation strategy
6. When ready, use ExitPlanMode to present your plan for approval

Remember: DO NOT write or edit any files yet. This is a read-only exploration and planning phase.

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls -la /data/agent/choucisan",
  "description": "List files in working directory"
}
```

### Turn 5 (tool)
<persisted-output>
Output too large (44.3KB). Full output saved to: /home/agent/.claude/projects/-data-agent-choucisan/4b2fa183-58e8-42d7-9443-a703e68da942/tool-results/bi8xtc8vo.txt

Preview (first 2KB):
total 6236724
drwxrwsr-x 101 agent agent      36864 6月  22 01:22 .
drwxr-sr-x   8 agent agent       4096 4月  21 14:20 ..
-rw-rw-r--   1 agent agent        851 6月  21 22:17 actix-app.service
drwxr-sr-x   2 agent agent       4096 5月  17 00:02 .agents
-rw-rw-r--   1 agent agent      15042 6月  22 00:09 aho_corasick.py
-rw-rw-r--   1 agent agent    4950608 3月  14 01:47 airscape_bench.jsonl
-rw-rw-r--   1 agent agent    2250812 3月  14 01:49 airscape_qa.jsonl
-rw-rw-r--   1 agent agent      50953 3月  21 14:51 AirScape_Train_list.txt
drwxrwsr-x   3 agent agent       4096 6月  21 18:58 airtable
drwxrwsr-x   2 agent agent       4096 6月  21 22:12 airtable_client
drwxrwsr-x   2 agent agent       4096 6月  21 21:48 airtable-proxy
drwxrwsr-x   4 agent agent       4096 6月  21 21:25 analytics-graphql-api
-rw-rw-r--   1 agent agent       4190 6月  22 01:03 analyze_excel.py
-rw-rw-r--   1 agent agent       4887 6月  21 23:13 analyze_jsonl.py
drwxrwsr-x   2 agent agent       4096 6月  21 21:06 api_codegen
-rw-rw-r--   1 agent agent      25214 6月  21 19:22 api_etl_pipeline.py
-rw-rw-r--   1 agent agent      31231 6月  21 21:14 arbitrary_precision.py
-rw-rw-r--   1 agent agent       7420 6月  21 19:49 astar.py
-rw-rw-r--   1 agent agent       1174 6月  21 21:39 backup_db.conf.example
-rwxrwxr-x   1 agent agent       9086 6月  21 21:39 backup_db.sh
drwxrwsr-x   2 agent agent       4096 6月  21 21:40 backup_logs
-rw-rw-r--   1 agent agent       4972 6月  21 23:24 base_converter.py
-rw-rw-r--   1 agent agent       1323 6月  21 23:42 batch_operations_sample.json
-rw-rw-r--   1 agent agent      16956 6月  21 23:26 batch_processor.py
-rw-rw-r--   1 agent agent       7101 6月  21 22:23 bellman_ford.py
-rw-rw-r--   1 agent agent        778 6月  21 21:58 bernoulli.py
-rw-rw-r--   1 agent agent       5018 6月  21 23:44 bfs.py
-rw-rw-r--   1 agent agent       4243 6月  22 00:53 binary_tree.py
-rw-rw-r--   1 agent agent        535 6月  21 18:56 binomial_coefficient.py
...
</persisted-output>

### Turn 6 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/*.sh 2>/dev/null; ls /data/agent/choucisan/*monitor* 2>/dev/null; ls /data/agent/choucisan/*health* 2>/dev/null",
  "description": "Check for existing scripts related to monitoring"
}
```

### Turn 7 (tool)
/data/agent/choucisan/backup_db.sh
/data/agent/choucisan/csv_loader.sh
/data/agent/choucisan/csv_remote_loader.sh
/data/agent/choucisan/csv_to_db_loader.sh
/data/agent/choucisan/db_backup.sh
/data/agent/choucisan/deploy.sh
/data/agent/choucisan/disk_monitor_cleanup.sh
/data/agent/choucisan/disk_monitor.sh
/data/agent/choucisan/health_monitor.sh
/data/agent/choucisan/log_report.sh
/data/agent/choucisan/logrotate_remote.sh
/data/agent/choucisan/logrotate.sh
/data/agent/choucisan/monitor_db_connections.sh
/data/agent/choucisan/network_bandwidth_monitor.sh
/data/agent/choucisan/queue_monitor.sh
/data/agent/choucisan/remote-dev-setup.sh
/data/agent/choucisan/renew-ssl.sh
/data/agent/choucisan/response_time_monitor.sh
/data/agent/choucisan/rotate_logs.sh
/data/agent/choucisan/run_all.sh
/data/agent/choucisan/setup-dev-rollback.sh
/data/agent/choucisan/setup-dev.sh
/data/agent/choucisan/ssl-renew.sh
/data/agent/choucisan/sync_dirs.sh
/data/agent/choucisan/system_monitor.sh
/data/agent/choucisan/disk_monitor_cleanup.sh
/data/agent/choucisan/disk_monitor.sh
/data/agent/choucisan/health_monitor.sh
/data/agent/choucisan/monitor_db_connections.sh
/data/agent/choucisan/network_bandwidth_monitor.sh
/data/agent/choucisan/queue_monitor.sh
/data/agent/choucisan/response_time_monitor.sh
/data/agent/choucisan/system_monitor.sh
/data/agent/choucisan/health_monitor.sh

### Turn 8 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/health_monitor.sh"
}
```
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/deploy.sh"
}
```
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/setup-dev-rollback.sh"
}
```

### Turn 9 (tool)
1	#!/usr/bin/env bash
2	set -euo pipefail
3	
4	# =============================================================================
5	# Health Monitor — monitors services and restarts unhealthy ones
6	#
7	# Features:
8	#   - Continuous monitoring loop with configurable interval
9	#   - Consecutive-failure tracking to avoid flapping restarts
10	#   - HTTP health endpoint checks and systemd service status
11	#   - Log rotation (keeps last N lines when file exceeds size limit)
12	#   - Graceful shutdown on SIGINT / SIGTERM
13	#   - Works locally or over SSH (toggle REMOTE_MODE)
14	# =============================================================================
15	
16	# --- Configuration -----------------------------------------------------------
17	
18	REMOTE_MODE="${REMOTE_MODE:-false}"               # true = SSH to remote hosts
19	
20	# Remote servers (only used when REMOTE_MODE=true)
21	# Format: "user@host:service1,service2"
22	SERVERS=(
23	    "deploy@10.0.1.10:nginx,app-server"
24	    "deploy@10.0.1.11:nginx,app-server"
25	    "deploy@10.0.1.12:postgres"
26	)
27	
28	# Local services (only used when REMOTE_MODE=false)
29	# Format: "service_name|health_url|restart_command"
30	LOCAL_SERVICES=(
31	    "webapp|http://localhost:8080/health|systemctl restart webapp"
32	    "api|http://localhost:3000/health|systemctl restart api"
33	    "worker|http://localhost:5000/health|systemctl restart worker"
34	)
35	
36	CHECK_INTERVAL=30                                   # Seconds between cycles
37	HEALTH_TIMEOUT=5                                    # HTTP request timeout (seconds)
38	MAX_CONSECUTIVE_FAILURES=3                          # Failures before restart
39	MAX_RESTART_ATTEMPTS=2                              # Restart retries per cycle
40	SSH_TIMEOUT=10                                      # SSH connect timeout
41	LOG_FILE="${LOG_FILE:-/var/log/health_monitor.log}"
42	LOG_MAX_SIZE=$((5 * 1024 * 1024))                   # Rotate at 5 MB
43	LOG_KEEP_LINES=5000                                 # Lines to keep after rotation
44	
45	# --- State -------------------------------------------------------------------
46	
47	declare -A FAILURE_COUNTS   # consecutive failures per service key
48	RUNNING=true
49	
50	# --- Helpers -----------------------------------------------------------------
51	
52	log() {
53	    local level="$1"; shift
54	    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$$] [$level] $*"
55	    echo "$msg" >&2
56	    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
57	}
58	
59	rotate_log() {
60	    [[ ! -f "$LOG_FILE" ]] && return
61	    local size
62	    size=$(stat -c%s "$LOG_FILE" 2>/dev/null) || return
63	    if (( size > LOG_MAX_SIZE )); then
64	        log "INFO" "Rotating log ($size bytes > $LOG_MAX_SIZE bytes)"
65	        local tmp="${LOG_FILE}.tmp"
66	        tail -n "$LOG_KEEP_LINES" "$LOG_FILE" > "$tmp" 2>/dev/null
67	        mv "$tmp" "$LOG_FILE"
68	    fi
69	}
70	
71	cleanup() {
72	    RUNNING=false
73	    log "INFO" "Shutting down (PID $$)"
74	}
75	trap cleanup SIGINT SIGTERM
76	
77	# --- Remote helpers ----------------------------------------------------------
78	
79	remote_exec() {
80	    local host="$1"; shift
81	    ssh -o ConnectTimeout="$SSH_TIMEOUT" \
82	        -o StrictHostKeyChecking=accept-new \
83	        -o BatchMode=yes \
84	        "$host" "$@"
85	}
86	
87	is_remote_service_active() {
88	    local host="$1" service="$2"
89	    remote_exec "$host" "systemctl is-active --quiet '$service'" 2>/dev/null
90	}
91	
92	check_remote_http() {
93	    local host="$1"
94	    remote_exec "$host" \
95	        "curl -sf --max-time $HEALTH_TIMEOUT 'http://localhost:8080/health' >/dev/null 2>&1"
96	}
97	
98	restart_remote_service() {
99	    local host="$1" service="$2"
100	    log "INFO" "$host: restarting '$service'..."
101	    remote_exec "$host" "sudo systemctl restart '$service'" 2>&1
102	}
103	
104	# --- Local helpers -----------------------------------------------------------
105	
106	check_local_http() {
107	    local url="$1"
108	    local code
109	    code=$(curl -sf -o /dev/null -w '%{http_code}' --max-time "$HEALTH_TIMEOUT" "$url" 2>/dev/null) || return 1
110	    [[ "$code" =~ ^2 ]]
111	}
112	
113	restart_local_service() {
114	    local cmd="$1"
115	    log "INFO" "Running: $cmd"
116	    eval "$cmd" >> "$LOG_FILE" 2>&1
117	}
118	
119	# --- Core logic --------------------------------------------------------------
120	
121	# $1 = key (for failure tracking)
122	# $2 = human-readable label
123	# $3.. = check command (eval'd)
124	run_check() {
125	    local key="$1" label="$2"; shift 2
126	    local failures=${FAILURE_COUNTS[$key]:-0}
127	
128	    if "$@"; then
129	        if (( failures > 0 )); then
130	            log "INFO" "$label recovered after $failures failed check(s)"
131	        fi
132	        FAILURE_COUNTS[$key]=0
133	        return 0
134	    fi
135	
136	    failures=$((failures + 1))
137	    FAILURE_COUNTS[$key]=$failures
138	    log "WARN" "$label health check failed ($failures/$MAX_CONSECUTIVE_FAILURES)"
139	
140	    if (( failures >= MAX_CONSECUTIVE_FAILURES )); then
141	        return 1
142	    fi
143	    return 0
144	}
145	
146	monitor_remote() {
147	    local entry="$1"
148	    IFS=':' read -r host service_list <<< "$entry"
149	    IFS=',' read -ra services <<< "$service_list"
150	
151	    log "INFO" "Checking $host (services: ${services[*]})"
152	
153	    for svc in "${services[@]}"; do
154	        local key="${host}:${svc}"
155	        if ! run_check "$key" "$host/$svc" is_remote_service_active "$host" "$svc"; then
156	            local attempt=0
157	            while (( attempt < MAX_RESTART_ATTEMPTS )); do
158	                ((attempt++))
159	                restart_remote_service "$host" "$svc"
160	                if is_remote_service_active "$host" "$svc"; then
161	                    log "INFO" "$host/$svc recovered after restart (attempt $attempt)"
162	                    FAILURE_COUNTS[$key]=0
163	                    break
164	                fi
165	                log "WARN" "$host/$svc still down after attempt $attempt"
166	            done
167	            if (( attempt >= MAX_RESTART_ATTEMPTS )) && ! is_remote_service_active "$host" "$svc"; then
168	                log "ERROR" "$host/$svc failed to recover after $MAX_RESTART_ATTEMPTS restart(s)"
169	                FAILURE_COUNTS[$key]=$((MAX_CONSECUTIVE_FAILURES - 1))
170	            fi
171	        fi
172	    done
173	}
174	
175	monitor_local() {
176	    local entry="$1"
177	    IFS='|' read -r name url cmd <<< "$entry"
178	
179	    if ! run_check "$name" "$name" check_local_http "$url"; then
180	        local attempt=0
181	        while (( attempt < MAX_RESTART_ATTEMPTS )); do
182	            ((attempt++))
183	            restart_local_service "$cmd"
184	            sleep 3
185	            if check_local_http "$url"; then
186	                log "INFO" "$name recovered after restart (attempt $attempt)"
187	                FAILURE_COUNTS[$name]=0
188	                break
189	            fi
190	            log "WARN" "$name still unhealthy after attempt $attempt"
191	        done
192	        if (( attempt >= MAX_RESTART_ATTEMPTS )) && ! check_local_http "$url"; then
193	            log "ERROR" "$name failed to recover after $MAX_RESTART_ATTEMPTS restart(s)"
194	            FAILURE_COUNTS[$name]=$((MAX_CONSECUTIVE_FAILURES - 1))
195	        fi
196	    fi
197	}
198	
199	# --- Main --------------------------------------------------------------------
200	
201	main() {
202	    mkdir -p "$(dirname "$LOG_FILE")"
203	    log "INFO" "=== Health monitor started (PID $$, interval=${CHECK_INTERVAL}s) ==="
204	
205	    # Init failure counters
206	    if [[ "$REMOTE_MODE" == "true" ]]; then
207	        for entry in "${SERVERS[@]}"; do
208	            IFS=':' read -r host service_list <<< "$entry"
209	            IFS=',' read -ra services <<< "$service_list"
210	            for svc in "${services[@]}"; do
211	                FAILURE_COUNTS["${host}:${svc}"]=0
212	            done
213	        done
214	    else
215	        for entry in "${LOCAL_SERVICES[@]}"; do
216	            IFS='|' read -r name _ _ <<< "$entry"
217	            FAILURE_COUNTS["$name"]=0
218	        done
219	    fi
220	
221	    while $RUNNING; do
222	        rotate_log
223	
224	        if [[ "$REMOTE_MODE" == "true" ]]; then
225	            for entry in "${SERVERS[@]}"; do
226	                monitor_remote "$entry" &
227	            done
228	        else
229	            for entry in "${LOCAL_SERVICES[@]}"; do
230	                monitor_local "$entry" &
231	            done
232	        fi
233	        wait
234	
235	        # Interruptible sleep
236	        local i=0
237	        while $RUNNING && (( i < CHECK_INTERVAL )); do
238	            sleep 1
239	            ((i++))
240	        done
241	    done
242	
243	    log "INFO" "=== Health monitor stopped ==="
244	}
245	
246	main "$@"
247	

### Turn 10 (tool)
1	#!/usr/bin/env bash
2	#
3	# deploy.sh — Zero-downtime rolling deploy to multiple servers via SSH.
4	#
5	# Usage:
6	#   ./deploy.sh [options]
7	#
8	# Options:
9	#   -c, --config FILE       Server config file (default: deploy.conf)
10	#   -a, --app NAME          Application name
11	#   -d, --deploy-dir DIR    Remote deployment directory
12	#   -s, --source DIR        Local source directory to deploy
13	#   -u, --user USER         SSH user (default: deploy)
14	#   -i, --identity FILE     SSH private key file
15	#   -p, --port PORT         SSH port (default: 22)
16	#   -t, --health-url URL    Health check URL path (default: /health)
17	#   -w, --wait SECONDS      Health check timeout in seconds (default: 60)
18	#   -b, --batch-size N      Number of servers to deploy at a time (default: 1)
19	#   -r, --rollback          Rollback to the previous release on all servers
20	#   -n, --dry-run           Show what would be done without executing
21	#   -v, --verbose           Enable verbose output
22	#   -h, --help              Show this help message
23	#
24	# Config file format (deploy.conf), one server per line:
25	#   server1.example.com
26	#   server2.example.com:2222
27	#   server3.example.com   weight=2
28	#
29	# Environment variables (override config file):
30	#   DEPLOY_SERVERS          Comma-separated list of servers
31	#   DEPLOY_USER             SSH user
32	#   DEPLOY_DIR              Remote deployment directory
33	#   DEPLOY_HEALTH_URL       Health check URL path
34	#
35	
36	set -euo pipefail
37	
38	# ── Defaults ─────────────────────────────────────────────────────────────────
39	
40	APP_NAME=""
41	DEPLOY_DIR=""
42	SOURCE_DIR=""
43	SSH_USER="${DEPLOY_USER:-deploy}"
44	SSH_IDENTITY=""
45	SSH_PORT=22
46	HEALTH_URL="${DEPLOY_HEALTH_URL:-/health}"
47	HEALTH_TIMEOUT=60
48	BATCH_SIZE=1
49	CONFIG_FILE="deploy.conf"
50	DRY_RUN=false
51	VERBOSE=false
52	ROLLBACK=false
53	
54	# Directories on the remote server (under DEPLOY_DIR):
55	#   releases/<timestamp>/   — each release
56	#   current -> releases/<timestamp>/  — symlink to active release
57	#   shared/                 — persistent data (logs, uploads, .env)
58	
59	RED='\033[0;31m'
60	GREEN='\033[0;32m'
61	YELLOW='\033[1;33m'
62	CYAN='\033[0;36m'
63	NC='\033[0m'
64	
65	# ── Helpers ──────────────────────────────────────────────────────────────────
66	
67	log()   { printf "${CYAN}[deploy]${NC} %s\n" "$*"; }
68	ok()    { printf "${GREEN}[  ok  ]${NC} %s\n" "$*"; }
69	warn()  { printf "${YELLOW}[ warn ]${NC} %s\n" "$*"; }
70	err()   { printf "${RED}[error ]${NC} %s\n" "$*" >&2; }
71	debug() { $VERBOSE && printf "[debug] %s\n" "$*" || true; }
72	
73	usage() {
74	    sed -n '2,/^$/s/^# \?//p' "$0"
75	    exit 0
76	}
77	
78	die() { err "$@"; exit 1; }
79	
80	# Run a command or print it in dry-run mode.
81	run() {
82	    if $DRY_RUN; then
83	        printf "  (dry-run) %s\n" "$*"
84	    else
85	        debug "exec: $*"
86	        "$@"
87	    fi
88	}
89	
90	# SSH wrapper that respects identity, port, and user.
91	ssh_cmd() {
92	    local host="$1"; shift
93	    local -a args=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
94	    [[ -n "$SSH_IDENTITY" ]] && args+=(-i "$SSH_IDENTITY")
95	    args+=(-p "$SSH_PORT" -l "$SSH_USER" "$host" --)
96	    debug "ssh ${args[*]} $*"
97	    ssh "${args[@]}" "$@"
98	}
99	
100	# SCP wrapper.
101	scp_cmd() {
102	    local -a args=()
103	    [[ -n "$SSH_IDENTITY" ]] && args+=(-i "$SSH_IDENTITY")
104	    args+=(-P "$SSH_PORT" -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
105	    debug "scp ${args[*]} $*"
106	    scp "${args[@]}" "$@"
107	}
108	
109	# ── Parse arguments ──────────────────────────────────────────────────────────
110	
111	parse_args() {
112	    while [[ $# -gt 0 ]]; do
113	        case "$1" in
114	            -c|--config)     CONFIG_FILE="$2"; shift 2 ;;
115	            -a|--app)        APP_NAME="$2"; shift 2 ;;
116	            -d|--deploy-dir) DEPLOY_DIR="$2"; shift 2 ;;
117	            -s|--source)     SOURCE_DIR="$2"; shift 2 ;;
118	            -u|--user)       SSH_USER="$2"; shift 2 ;;
119	            -i|--identity)   SSH_IDENTITY="$2"; shift 2 ;;
120	            -p|--port)       SSH_PORT="$2"; shift 2 ;;
121	            -t|--health-url) HEALTH_URL="$2"; shift 2 ;;
122	            -w|--wait)       HEALTH_TIMEOUT="$2"; shift 2 ;;
123	            -b|--batch-size) BATCH_SIZE="$2"; shift 2 ;;
124	            -r|--rollback)   ROLLBACK=true; shift ;;
125	            -n|--dry-run)    DRY_RUN=true; shift ;;
126	            -v|--verbose)    VERBOSE=true; shift ;;
127	            -h|--help)       usage ;;
128	            *) die "Unknown option: $1" ;;
129	        esac
130	    done
131	}
132	
133	# ── Load server list ─────────────────────────────────────────────────────────
134	
135	SERVERS=()
136	
137	load_servers() {
138	    # Environment variable takes priority.
139	    if [[ -n "${DEPLOY_SERVERS:-}" ]]; then
140	        IFS=',' read -ra SERVERS <<< "$DEPLOY_SERVERS"
141	        return
142	    fi
143	
144	    if [[ ! -f "$CONFIG_FILE" ]]; then
145	        die "Config file not found: $CONFIG_FILE (create it or use -c / DEPLOY_SERVERS)"
146	    fi
147	
148	    while IFS= read -r line || [[ -n "$line" ]]; do
149	        line="${line%%#*}"           # strip comments
150	        line="${line// /}"           # strip spaces
151	        [[ -z "$line" ]] && continue
152	        SERVERS+=("$line")
153	    done < "$CONFIG_FILE"
154	}
155	
156	# Extract hostname (strip port/weight annotations).
157	server_host() {
158	    echo "${1%%:*}"
159	}
160	
161	# Extract port override if present (format: host:port).
162	server_port() {
163	    local entry="$1"
164	    if [[ "$entry" == *:* ]]; then
165	        local after="${entry#*:}"
166	        after="${after%% *}"
167	        echo "$after"
168	    else
169	        echo "$SSH_PORT"
170	    fi
171	}
172	
173	# ── Validation ───────────────────────────────────────────────────────────────
174	
175	validate() {
176	    [[ ${#SERVERS[@]} -gt 0 ]] || die "No servers configured."
177	    if ! $ROLLBACK; then
178	        [[ -n "$SOURCE_DIR" ]] || die "Source directory (-s) is required for deploy."
179	        [[ -d "$SOURCE_DIR" ]] || die "Source directory does not exist: $SOURCE_DIR"
180	    fi
181	    [[ -n "$DEPLOY_DIR" ]] || die "Deployment directory (-d) is required."
182	    [[ -n "$APP_NAME" ]]  || die "Application name (-a) is required."
183	}
184	
185	# ── Health check ─────────────────────────────────────────────────────────────
186	
187	health_check() {
188	    local host="$1"
189	    local port="$2"
190	    local url="http://localhost:${port}${HEALTH_URL}"
191	    local elapsed=0
192	
193	    log "  Health-checking $host ($url) — timeout ${HEALTH_TIMEOUT}s"
194	
195	    while (( elapsed < HEALTH_TIMEOUT )); do
196	        local status
197	        status=$(ssh_cmd "$host" "curl -sf -o /dev/null -w '%{http_code}' '$url' 2>/dev/null" || true)
198	
199	        if [[ "$status" == "200" ]]; then
200	            ok "  $host is healthy (HTTP 200)"
201	            return 0
202	        fi
203	
204	        debug "  $host returned HTTP ${status:-timeout}, retrying in 3s..."
205	        sleep 3
206	        elapsed=$((elapsed + 3))
207	    done
208	
209	    err "  Health check failed for $host after ${HEALTH_TIMEOUT}s"
210	    return 1
211	}
212	
213	# ── Core deploy logic (per server) ───────────────────────────────────────────
214	
215	deploy_to_server() {
216	    local host
217	    host=$(server_host "$1")
218	    local port
219	    port=$(server_port "$1")
220	    local timestamp
221	    timestamp=$(date +%Y%m%d%H%M%S)
222	    local release_dir="${DEPLOY_DIR}/releases/${timestamp}"
223	    local current_link="${DEPLOY_DIR}/current"
224	    local prev_release=""
225	
226	    log "[$host] Starting deploy (release: $timestamp)"
227	
228	    # Save reference to the current release for rollback.
229	    prev_release=$(ssh_cmd "$host" "readlink -f '$current_link' 2>/dev/null || true")
230	    debug "  Previous release: ${prev_release:-<none>}"
231	
232	    # 1. Prepare remote directory structure.
233	    run ssh_cmd "$host" "mkdir -p '${DEPLOY_DIR}/releases' '${DEPLOY_DIR}/shared'"
234	
235	    # 2. Upload the release archive.
236	    log "[$host] Uploading source..."
237	    local tmp_archive
238	    tmp_archive=$(mktemp "/tmp/deploy-${APP_NAME}-XXXXXX.tar.gz")
239	    tar -czf "$tmp_archive" -C "$SOURCE_DIR" .
240	    run scp_cmd "$tmp_archive" "${SSH_USER}@${host}:/tmp/release-${timestamp}.tar.gz"
241	    rm -f "$tmp_archive"
242	
243	    # 3. Extract release on the remote server.
244	    log "[$host] Extracting release..."
245	    run ssh_cmd "$host" "mkdir -p '${release_dir}' && tar -xzf '/tmp/release-${timestamp}.tar.gz' -C '${release_dir}' && rm -f '/tmp/release-${timestamp}.tar.gz'"
246	
247	    # 4. Link shared resources (e.g. .env, logs, uploads).
248	    #    Shared files/dirs are expected in ${DEPLOY_DIR}/shared/.
249	    run ssh_cmd "$host" "
250	        if [ -d '${DEPLOY_DIR}/shared' ]; then
251	            for item in '${DEPLOY_DIR}/shared'/*; do
252	                [ -e \"\$item\" ] || continue
253	                link_name='${release_dir}/\$(basename \"\$item\")'
254	                rm -rf \"\$link_name\"
255	                ln -s \"\$item\" \"\$link_name\"
256	            done
257	        fi
258	    "
259	
260	    # 5. Run pre-activation hook (e.g. install deps, build assets, migrations).
261	    log "[$host] Running pre-activation hook..."
262	    run ssh_cmd "$host" "
263	        if [ -x '${release_dir}/deploy/hooks/pre-activate' ]; then
264	            '${release_dir}/deploy/hooks/pre-activate' '${release_dir}'
265	        fi
266	    "
267	
268	    # 6. Swap the symlink (the zero-downtime moment).
269	    log "[$host] Swapping symlink to new release..."
270	    run ssh_cmd "$host" "
271	        ln -sfn '${release_dir}' '${current_link}.new' &&
272	        mv -Tf '${current_link}.new' '${current_link}'
273	    "
274	
275	    # 7. Restart the applic

### Turn 11 (tool)
1	#!/usr/bin/env bash
2	#
3	# setup-dev-rollback.sh — Development environment setup with full rollback support
4	#
5	# Usage:
6	#   ./setup-dev-rollback.sh                    # Full setup (all components)
7	#   ./setup-dev-rollback.sh --core             # Core only: Python, Node, Docker
8	#   ./setup-dev-rollback.sh --component python # Single component
9	#   ./setup-dev-rollback.sh --rollback         # Roll back the last setup
10	#   ./setup-dev-rollback.sh --rollback --component python  # Roll back one component
11	#   ./setup-dev-rollback.sh --status           # Show what was installed
12	#   ./setup-dev-rollback.sh --dry-run          # Preview without changes
13	#   ./setup-dev-rollback.sh --help
14	#
15	set -euo pipefail
16	
17	# ── Constants ─────────────────────────────────────────────────────────────────
18	SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
19	LOG_FILE="${SCRIPT_DIR}/setup-dev.log"
20	STATE_DIR="${SCRIPT_DIR}/.setup-state"
21	ROLLBACK_LOG="${STATE_DIR}/rollback.log"
22	SNAPSHOT_DIR="${STATE_DIR}/snapshots"
23	LOCK_FILE="${STATE_DIR}/setup.lock"
24	
25	REQUIRED_PYTHON="3.11"
26	REQUIRED_NODE="20"
27	REQUIRED_PNPM="10"
28	REQUIRED_GO="1.21"
29	REQUIRED_JAVA="21"
30	
31	# ── Globals set by flags ─────────────────────────────────────────────────────
32	DRY_RUN=false
33	SKIP_DOCKER=false
34	COMPONENTS=()
35	MODE="install"  # install | rollback | status
36	
37	# ── Logging ───────────────────────────────────────────────────────────────────
38	_log() {
39	    local level="$1"; shift
40	    local ts
41	    ts="$(date '+%Y-%m-%d %H:%M:%S')"
42	    local msg="[${ts}] [${level}] $*"
43	    echo "$msg" >> "$LOG_FILE"
44	    case "$level" in
45	        ERROR)   echo -e "\033[1;31m${msg}\033[0m" ;;
46	        WARN)    echo -e "\033[1;33m${msg}\033[0m" ;;
47	        SUCCESS) echo -e "\033[1;32m${msg}\033[0m" ;;
48	        INFO)    echo -e "\033[1;34m${msg}\033[0m" ;;
49	        STEP)    echo -e "\033[1;36m${msg}\033[0m" ;;
50	        ROLL)    echo -e "\033[1;35m${msg}\033[0m" ;;
51	        *)       echo "$msg" ;;
52	    esac
53	}
54	
55	log_info()    { _log INFO    "$@"; }
56	log_step()    { _log STEP    "$@"; }
57	log_success() { _log SUCCESS "$@"; }
58	log_warn()    { _log WARN    "$@"; }
59	log_error()   { _log ERROR   "$@"; }
60	log_roll()    { _log ROLL    "$@"; }
61	
62	die() { log_error "$@"; exit 1; }
63	
64	run() {
65	    if $DRY_RUN; then
66	        log_info "[dry-run] $*"
67	        return 0
68	    fi
69	    log_info "Running: $*"
70	    if ! "$@" >> "$LOG_FILE" 2>&1; then
71	        log_error "Command failed: $*"
72	        log_error "See ${LOG_FILE} for details"
73	        return 1
74	    fi
75	}
76	
77	version_gte() {
78	    local current="$1" required="$2"
79	    printf '%s\n%s' "$required" "$current" | sort -V -C
80	}
81	
82	command_exists() { command -v "$1" &>/dev/null; }
83	ensure_dir() { mkdir -p "$1" 2>/dev/null || true; }
84	
85	# ── Rollback infrastructure ──────────────────────────────────────────────────
86	#
87	# Every install step calls record_change() to log what it did. The rollback
88	# reads this log in reverse and undoes each entry.
89	#
90	# Change types:
91	#   venv        — created a Python venv at <path>
92	#   pip_pkg     — installed pip packages (rollback: uninstall)
93	#   node_modules — installed node_modules at <path>
94	#   go_mod      — downloaded Go modules at <path>
95	#   cargo_build — built a Rust project at <path>
96	#   ruby_bundle — ran bundle install at <path>
97	#   docker_svc  — started docker compose at <path>
98	#   apt_pkg     — installed apt packages (rollback: remove)
99	#   file_bak    — backed up <original> to <backup> before overwriting
100	#   dir_created — created directory at <path>
101	#   npm_global  — installed an npm global package <name>
102	#   gem_installed — installed a gem <name>
103	
104	record_change() {
105	    local type="$1"; shift
106	    local ts
107	    ts="$(date '+%s')"
108	    echo "${ts}|${type}|$*" >> "${STATE_DIR}/changes.log"
109	}
110	
111	snapshot_file() {
112	    # Back up a file before modifying it
113	    local filepath="$1"
114	    if [ -f "$filepath" ]; then
115	        local bak="${SNAPSHOT_DIR}/$(basename "$filepath").${RANDOM}.$(date +%s).bak"
116	        cp "$filepath" "$bak"
117	        record_change file_bak "$filepath" "$bak"
118	        log_info "Snapshot: ${filepath} -> ${bak}"
119	    fi
120	}
121	
122	begin_setup() {
123	    ensure_dir "$STATE_DIR"
124	    ensure_dir "$SNAPSHOT_DIR"
125	
126	    # Lock to prevent concurrent runs
127	    if [ -f "$LOCK_FILE" ]; then
128	        local lock_pid
129	        lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
130	        if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
131	            die "Another setup is running (PID ${lock_pid}). Wait or remove ${LOCK_FILE}."
132	        fi
133	        log_warn "Removing stale lock file."
134	        rm -f "$LOCK_FILE"
135	    fi
136	    echo $$ > "$LOCK_FILE"
137	
138	    # Reset changes log for this run
139	    : > "${STATE_DIR}/changes.log"
140	}
141	
142	end_setup() {
143	    # Archive this run's changes into a named snapshot
144	    local run_id
145	    run_id="$(date '+%Y%m%d_%H%M%S')"
146	    if [ -s "${STATE_DIR}/changes.log" ]; then
147	        cp "${STATE_DIR}/changes.log" "${STATE_DIR}/run_${run_id}.log"
148	        log_info "Change log archived: run_${run_id}.log"
149	    fi
150	    rm -f "$LOCK_FILE"
151	}
152	
153	# ── Rollback engine ──────────────────────────────────────────────────────────
154	
155	rollback_component() {
156	    local target_component="$1"
157	    local change_log=""
158	
159	    # Find the most recent run log that contains this component
160	    local latest_log
161	    latest_log="$(ls -t "${STATE_DIR}"/run_*.log 2>/dev/null | head -1)"
162	
163	    if [ -z "$latest_log" ]; then
164	        # Fall back to current changes.log
165	        if [ -s "${STATE_DIR}/changes.log" ]; then
166	            change_log="${STATE_DIR}/changes.log"
167	        else
168	            log_warn "No change logs found. Nothing to roll back."
169	            return 0
170	        fi
171	    else
172	        change_log="$latest_log"
173	    fi
174	
175	    log_roll "Rolling back component: ${target_component}"
176	    log_roll "Using change log: ${change_log}"
177	
178	    # Read changes in reverse order, filter by component context
179	    local count=0
180	    local skipped=0
181	
182	    while IFS='|' read -r ts type args; do
183	        [ -z "$ts" ] && continue
184	
185	        local should_rollback=false
186	
187	        case "$type" in
188	            venv)
189	                [[ "$target_component" == "python" || "$target_component" == "all" ]] && should_rollback=true
190	                ;;
191	            pip_pkg)
192	                [[ "$target_component" == "python" || "$target_component" == "all" ]] && should_rollback=true
193	                ;;
194	            node_modules)
195	                [[ "$target_component" == "node" || "$target_component" == "all" ]] && should_rollback=true
196	                ;;
197	            npm_global)
198	                [[ "$target_component" == "node" || "$target_component" == "all" ]] && should_rollback=true
199	                ;;
200	            go_mod)
201	                [[ "$target_component" == "go" || "$target_component" == "all" ]] && should_rollback=true
202	                ;;
203	            cargo_build)
204	                [[ "$target_component" == "rust" || "$target_component" == "all" ]] && should_rollback=true
205	                ;;
206	            ruby_bundle)
207	                [[ "$target_component" == "ruby" || "$target_component" == "all" ]] && should_rollback=true
208	                ;;
209	            gem_installed)
210	                [[ "$target_component" == "ruby" || "$target_component" == "all" ]] && should_rollback=true
211	                ;;
212	            docker_svc)
213	                [[ "$target_component" == "docker" || "$target_component" == "all" ]] && should_rollback=true
214	                ;;
215	            apt_pkg)
216	                [[ "$target_component" == "cpp" || "$target_component" == "java" || "$target_component" == "all" ]] && should_rollback=true
217	                ;;
218	            file_bak)
219	                should_rollback=true  # always restore backups
220	                ;;
221	            *)
222	                should_rollback=true
223	                ;;
224	        esac
225	
226	        if ! $should_rollback; then
227	            skipped=$((skipped + 1))
228	            continue
229	        fi
230	
231	        case "$type" in
232	            venv)
233	                local venv_path="$args"
234	                if [ -d "$venv_path" ]; then
235	                    log_roll "Removing virtual environment: ${venv_path}"
236	                    if $DRY_RUN; then
237	                        log_info "[dry-run] rm -rf ${venv_path}"
238	                    else
239	                        rm -rf "$venv_path"
240	                    fi
241	                    count=$((count + 1))
242	                fi
243	                ;;
244	
245	            pip_pkg)
246	                log_roll "Note: pip packages left installed (no destructive uninstall)"
247	                log_info "  To manually uninstall: pip uninstall -y ${args}"
248	                count=$((count + 1))
249	                ;;
250	
251	            node_modules)
252	                local nm_path="$args"
253	                if [ -d "$nm_path" ]; then
254	                    log_roll "Removing node_modules: ${nm_path}"
255	                    if $DRY_RUN; then
256	                        log_info "[dry-run] rm -rf ${nm_path}"
257	                    else
258	                        rm -rf "$nm_path"
259	                    fi
260	                    count=$((count + 1))
261	                fi
262	                ;;
263	
264	            npm_global)
265	                log_roll "Uninstalling global npm package: ${args}"
266	       

### Turn 12 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/home/agent/.claude/plans/composed-kindling-widget.md",
  "content": "# Plan: Application Health Monitor with Rollback Support\n\n## Context\n\nThe user wants a bash script that monitors application health, restarts unhealthy services, and supports rollback. The project already has `health_monitor.sh` (basic monitoring + restart, no rollback) and `deploy.sh` / `setup-dev-rollback.sh` (rich rollback patterns). The new script will be a standalone tool combining health monitoring 
```

### Turn 13 (tool)
File created successfully at: /home/agent/.claude/plans/composed-kindling-widget.md (file state is current in your context — no need to Read it back)

### Turn 14 (assistant)
**Tool**: `ExitPlanMode`
```json
{
  "allowedPrompts": [
    {
      "tool": "Bash",
      "prompt": "run syntax check and shellcheck on the script"
    },
    {
      "tool": "Bash",
      "prompt": "run the script with --help or --dry-run flags"
    }
  ],
  "plan": "# Plan: Application Health Monitor with Rollback Support\n\n## Context\n\nThe user wants a bash script that monitors application health, restarts unhealthy services, and supports rollback. The project already has `health_monitor.sh` (basic monitoring + restart, n
```

### Turn 15 (tool)
Exit plan mode?

### Turn 16 (assistant)
The plan creates `service_health_monitor.sh` — a single bash script that:

- **Monitors** services via HTTP health endpoints and systemd status, with consecutive-failure tracking to avoid flapping restarts
- **Restarts** unhealthy services with configurable retry attempts
- **Rolls back** automatically if restarts fail — executes a per-service rollback command (e.g., revert symlink, restore previous config) and verifies health after rollback
- **Tracks state** in `~/.service-health-monitor/` with timestamped event logs for audit
- Supports `--dry-run`, `--once`, `--config FILE`, `--status`, and graceful shutdown

## Available Tools
- **Bash**: Run a shell command.
- **BashOutput**: Read output from a running background shell command.
- **Edit**: Replace text in an existing file.
- **EnterPlanMode**: Enter Claude Desktop plan mode.
- **ExitPlanMode**: Exit Claude Desktop plan mode.
- **Glob**: Find files by glob pattern.
- **Grep**: Search file contents by pattern.
- **KillBash**: Stop a running background shell command.
- **LS**: List files and directories.
- **MultiEdit**: Apply multiple text replacements to one file.

## Execution Trace