# Write a bash script that monitors queue depth and sends alerts when thresholds are exceeded.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a bash script that monitors queue depth and sends alerts when thresholds are exceeded.

## Conversation
### Turn 1 (user)
Write a bash script that monitors queue depth and sends alerts when thresholds are exceeded.

### Turn 2 (assistant)
Let me check the project structure first to understand the context.
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan",
  "description": "List project directory contents"
}
```

### Turn 3 (tool)
actix-app.service
aho_corasick.py
airscape_bench.jsonl
airscape_qa.jsonl
AirScape_Train_list.txt
airtable
airtable_client
airtable-proxy
analytics-graphql-api
api_codegen
api_etl_pipeline.py
arbitrary_precision.py
astar.py
backup_db.conf.example
backup_db.sh
backup_logs
base_converter.py
bellman_ford.py
bernoulli.py
binomial_coefficient.py
blog-graphql-api
blog-ws-api
bloom_filter.go
bloom_filter.js
bloom_filter.py
bloom_filter_test.go
boyer_moore.py
btree.py
cache_with_ttl.go
cache_with_ttl.js
cache_with_ttl.py
cache_with_ttl.rs
cache_with_ttl_test.go
calculate.py
calculator.py
call_tracer.py
cam_motion
CamReasoner
Cargo.lock
Cargo.toml
catalan.py
chunk.go
chunk_iterator.go
chunk_iterator.js
chunk_iterator.py
chunk_iterator_test.go
chunk_iterator.test.js
chunk_test.go
circuit_breaker.py
circuit_graph.py
circular_buffer.go
circular_buffer.js
circular_buffer.py
circular_buffer_test.go
circular_buffer.test.js
cleaned_output.html
code
coin_change.py
compress_string.go
compress_string.py
compress_string_test.go
concatenate.py
config_parser.py
connection_pool.py
continued_fraction.py
convex_hull.py
count_min_sketch.py
csv_fuzzy_dedup.py
csv_html_pipeline.py
csv_sampler.py
csv_to_db_loader.sh
csv_to_json_pipeline.py
csv_to_markdown.py
csv_to_sql_pipeline.py
cuda_12.8.0_570.86.10_linux.run
data
data_processor.py
db_etl_pipeline.py
db_parquet_etl.py
debounce
debounce.js
debounce.py
debounce.rs
deep_merge.py
default_dict.py
deploy
deploy.conf.example
deploy.sh
determinant.py
dfs.py
digital_root.py
dijkstra.py
disjoint_set
disjoint_set.js
disjoint_set.py
disjoint_set.rs
disjoint_set_test
disjoint_set.test.js
disk_monitor_cleanup.sh
disk_monitor.sh
distributed_lock.rb
distributed_lock_test.rb
docker-compose.yml
Dockerfile
Dockerfile.go
docs
Dog100K
email-module
email_utils.py
env_batch.py
etl_output.db
etl_output_source.db
etl_pipeline.py
euler_totient.py
event_emitter.py
examples
excel_data_validator.py
excel_to_markdown_pipeline.py
excel_to_sql.py
factorial.py
fastapi-app.service
fdagent
fdagent.tar.gz
fenwick_tree.py
fibonacci_gen.py
fibonacci.py
file_uploaded_email_webhook.py
file_uploaded_webhook.py
find_duplicates.js
find_duplicates.py
find_min_max.py
fix_min_max.py
flash-attention-2.7.4
flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp310-cp310-linux_x86_64.whl
flatten_nested_dict.py
floyd_warshall.py
format_converter.py
fraction_period.py
function_logger.py
gaussian_elimination.py
gcd_lcm.py
Gemfile
gen_table.py
github_pr_webhook.py
go
go.Dockerfile
go-http-server.service
go.mod
google-sheets-proxy
gpt1
graphql-auth-middleware
health_monitor.sh
heapsort.py
hyper_log_log.py
hyperloglog.py
infix_to_postfix.js
infix_to_postfix.py
jacobi.py
jira-proxy
jobmanager.py
json_dedup.py
jsonl_to_html.py
jsonl_validator.py
json_schema_validator.py
json_to_sql_pipeline.py
json_to_sql.py
jwt-auth-module
kadane.py
kahn_topological_sort.py
kmp.py
kruskal.py
line_intersection.py
linked_list_sort.py
log_aggregator.py
loganalyzer
log_etl_pipeline.py
log_report.sh
longest_palindrome.py
lru_cache.go
lru_cache.js
lru_cache.py
lru_cache_test.go
main.py
majority_vote.py
Makefile
max_subarray.py
median_sorted_arrays.py
mediator_refactor.py
memoize_context.py
memoize_lru.py
memory_profiler_examples.py
memory_profiler.py
merge_csv.py
merge_jsonl.py
merge.py
merge_sorted_lists.go
merge_sorted_lists.js
merge_sorted_lists_test.go
message_queue.py
message_sent_events.db
message_sent_webhook.py
metrics_collector.py
mimo-claude-code-traces
min_heap.py
min_max.py
min_stack.py
mo_algorithm.cpp
mo_algorithm.py
mobius.py
modular_exponentiation.py
motion-mllm
motion-mllms
motion-mllmss
motion-mllm-v1
network_bandwidth_monitor.sh
newton.py
nginx.conf
nginx-flask.conf
nlp_tokenizer.rb
nlp_tokenizer_test.rb
node_modules
notion
optimized.py
ordered_dict.py
package.json
package-lock.json
paginate_results.go
paginate_results.js
paginate_results_test.go
paper.tex
parquet_sampler.py
parquet_to_html.py
parse_excel.py
parse_expression.go
parse_expression.js
parse_expression.py
parse_expression_test.go
parse_expression.test.js
parse_jsonl.py
partition_function.py
pascals_triangle.py
pascal_triangle.py
payment_webhook.py
pipeline_output.html
pipeline_sample.csv
pivot.py
plan.md
point_segment_distance.py
pollard_rho.py
polygon_area.py
pricing.py
prim.py
prims_mst.py
priority_queue.js
priority_queue.py
process.py
pubsub_segment_tree.py
__pycache__
pythagorean_triples.py
quadratic_solver.py
quicksort.py
rabin_karp.py
rate_limiter.js
rate_limiter.py
rate_limiter.test.js
rate_limit_middleware
rebuttal
red_black_tree.py
renew-ssl.sh
request_facade.py
request_handler.py
request_logging_middleware
requirements-dev.txt
requirements.txt
response_time_monitor.sh
retry_context.py
retry.js
retry.test.js
retry_with_backoff.go
retry_with_backoff.py
retry_with_backoff_test.go
right_triangle.py
roman_converter.js
roman_converter.py
roman_converter.rs
router.py
routes.py
routing.py
ruff.toml
run_all.sh
run_length_encoding.go
run_length_encoding_test.go
s3_ws_client
sample.csv
sample_data.json
sample_data.parquet
sample_data.report.txt
sample_data.xml
sample_employees.csv
sample_employees.json
sample_employees.md
sample_employees.sql
sample_employees.xlsx
sample.json
sample.jsonl
sample_logs
sample_schema.json
sample.xml
sample.yaml
scc.py
scraper_elasticsearch_etl.py
scraper.py
segment_intersection.py
segment_tree_config.py
segment_tree_metrics.py
segment_tree.py
sendgrid-proxy
serialize_tree.js
serialize_tree.py
serialize_tree.test.js
servers.conf
servers.conf.example
setup-dev.sh
shoelace.py
sieve_of_atkin.py
skip_list.py
slack_api
sliding_window_maximum.py
sliding_window_max.py
sort_by_second.py
spring-boot.Dockerfile
sql_to_pg_pipeline.py
src
ssl-renew.sh
strategies.py
streaming_jsonl_parser.py
streaming_xml_parser.py
stripe_wrapper
suffix_array.py
suffix_tree_bruteforce.py
suffix_tree_compare.py
suffix_tree.py
svd.py
sync_dirs.sh
system_monitor.sh
t2v_metrics
target
tarjan_scc.py
task_scheduler.go
task_scheduler.py
task_scheduler.rb
task_scheduler_test.go
task_scheduler_test.rb
task-ws-api
test_aho_corasick.py
test_api_codegen.py
test_astar.py
test_bellman_ford.py
test_compress_string.py
test_connection_pool.py
test_email_utils.py
test_env1.env
test_env2.env
test_excel_data_validator.py
test_find_duplicates.py
test_function_logger.py
test_heapsort.py
test_json_dedup.py
test_jsonl_validator.py
test_json_schema_validator.py
test_kmp.py
test_kruskal.py
test_memoize_context.py
test_memory_profiler.py
test_quicksort.py
test_retry_context.py
test_retry_with_backoff.py
tests
test_schema.json
test_scraper.py
test_streaming_jsonl_parser.py
test_suffix_array.py
test_tarjan_scc.py
test_three_sum.py
test_topological_sort.py
test_tree_map.py
test_trie.py
test_ttl_cache.py
test_validate_schema.py
test_web_scraper.py
test_yaml_fuzzy_dedup.py
test_yaml_schema_validator.py
th.md
threadpool
thread_pool.js
thread_pool.test.js
three_sum.py
throttle_function.go
throttle_function.py
throttle_function_test.go
timeout_context.py
topological_sort.py
trainingfree
transformations_2d.py
tree
tree_map.py
trie_graph.py
trie_node.py
trie.py
tsp_dp.py
ttl_cache.py
twilio_client
twilio-graphql
twilio-ws-client
two_sum.js
two_sum.py
uav_accuracy_comparison.png
uavdown
UAVideo
UAVideo-Bench
uav-train-lora
url_shortener.js
url_shortener.test.js
user_registered_webhook.py
validate_schema.js
validate_schema.py
videoRL
webhook_receiver.py
web_scraper_etl.py
web_scraper.py
ws_api_key_middleware
ws_validation_middleware
xml_analyzer.py
xml_pivot.py
xml_sampler.py
xml_to_markdown.py
xml_to_sql.py
yaml_fuzzy_dedup.py
yaml_merger.py
yaml_schema_validator.py
yaml_to_html.py
yaml_to_json.py

### Turn 4 (assistant)
I'll create a queue depth monitoring script with configurable thresholds, multiple alert channels, and a clean structure.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/system_monitor.sh"
}
```
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/disk_monitor.sh"
}
```

### Turn 5 (tool)
1	#!/usr/bin/env bash
2	#
3	# System Resource Monitor
4	# Monitors CPU, memory, and disk usage; sends alerts when thresholds are exceeded.
5	
6	set -euo pipefail
7	
8	# --- Configuration (override via environment) ---
9	CPU_THRESHOLD="${CPU_THRESHOLD:-80}"
10	MEM_THRESHOLD="${MEM_THRESHOLD:-80}"
11	DISK_THRESHOLD="${DISK_THRESHOLD:-90}"
12	CHECK_INTERVAL="${CHECK_INTERVAL:-60}"   # seconds between checks
13	LOG_FILE="${LOG_FILE:-/var/log/system_monitor.log}"
14	ALERT_METHOD="${ALERT_METHOD:-log}"      # log | email | slack
15	SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
16	ALERT_EMAIL="${ALERT_EMAIL:-}"
17	
18	# Cooldown: avoid spamming the same alert every cycle
19	declare -A LAST_ALERTED
20	COOLDOWN=300  # seconds before the same alert can fire again
21	
22	log() {
23	    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
24	    echo "$msg"
25	    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
26	}
27	
28	send_alert() {
29	    local subject="$1"
30	    local body="$2"
31	    local key="$3"
32	
33	    # Cooldown check
34	    local now
35	    now=$(date +%s)
36	    if [[ -n "${LAST_ALERTED[$key]:-}" ]]; then
37	        local elapsed=$(( now - LAST_ALERTED[$key] ))
38	        if (( elapsed < COOLDOWN )); then
39	            return 0
40	        fi
41	    fi
42	    LAST_ALERTED[$key]=$now
43	
44	    log "ALERT: $subject — $body"
45	
46	    case "$ALERT_METHOD" in
47	        email)
48	            if [[ -n "$ALERT_EMAIL" ]] && command -v mail &>/dev/null; then
49	                echo "$body" | mail -s "$subject" "$ALERT_EMAIL"
50	            fi
51	            ;;
52	        slack)
53	            if [[ -n "$SLACK_WEBHOOK_URL" ]] && command -v curl &>/dev/null; then
54	                curl -sf -X POST -H 'Content-type: application/json' \
55	                    --data "{\"text\":\":warning: *$subject*\n$body\"}" \
56	                    "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
57	            fi
58	            ;;
59	        log) ;;  # already logged above
60	    esac
61	}
62	
63	check_cpu() {
64	    # Average CPU usage over 1-second sample (works on Linux & macOS)
65	    local usage
66	    if command -v mpstat &>/dev/null; then
67	        usage=$(mpstat 1 1 | awk '/Average/ && $NF ~ /[0-9]/ {printf "%.0f", 100 - $NF}')
68	    else
69	        # Fallback: /proc/stat on Linux
70	        if [[ -f /proc/stat ]]; then
71	            read -r _ u1 n1 s1 i1 _ < /proc/stat
72	            local total1=$(( u1 + n1 + s1 + i1 ))
73	            local idle1=$i1
74	            sleep 1
75	            read -r _ u2 n2 s2 i2 _ < /proc/stat
76	            local total2=$(( u2 + n2 + s2 + i2 ))
77	            local idle2=$i2
78	            local diff_total=$(( total2 - total1 ))
79	            local diff_idle=$(( idle2 - idle1 ))
80	            if (( diff_total > 0 )); then
81	                usage=$(( (diff_total - diff_idle) * 100 / diff_total ))
82	            else
83	                usage=0
84	            fi
85	        else
86	            usage=0
87	        fi
88	    fi
89	
90	    if (( usage > CPU_THRESHOLD )); then
91	        send_alert "High CPU Usage" "CPU usage is ${usage}% (threshold: ${CPU_THRESHOLD}%)" "cpu"
92	    fi
93	}
94	
95	check_memory() {
96	    local usage
97	    if command -v free &>/dev/null; then
98	        usage=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
99	    elif [[ "$(uname)" == "Darwin" ]]; then
100	        local total used
101	        total=$(sysctl -n hw.memsize)
102	        used=$(vm_stat | awk '/Pages active/ {a=$3} /Pages wired/ {w=$3} END {gsub(/\./,"",a); gsub(/\./,"",w); print (a+w)*4096}')
103	        usage=$(( used * 100 / total ))
104	    else
105	        usage=0
106	    fi
107	
108	    if (( usage > MEM_THRESHOLD )); then
109	        send_alert "High Memory Usage" "Memory usage is ${usage}% (threshold: ${MEM_THRESHOLD}%)" "mem"
110	    fi
111	}
112	
113	check_disk() {
114	    df -h --output=target,pcent 2>/dev/null | tail -n +2 | while read -r mount pct; do
115	        local usage=${pct%\%}
116	        if (( usage > DISK_THRESHOLD )); then
117	            send_alert "High Disk Usage" "Disk ${mount} is ${usage}% full (threshold: ${DISK_THRESHOLD}%)" "disk_${mount}"
118	        fi
119	    done
120	}
121	
122	usage() {
123	    cat <<EOF
124	Usage: $(basename "$0") [OPTIONS]
125	
126	Options:
127	  -c NUM    CPU threshold %       (default: $CPU_THRESHOLD)
128	  -m NUM    Memory threshold %    (default: $MEM_THRESHOLD)
129	  -d NUM    Disk threshold %      (default: $DISK_THRESHOLD)
130	  -i NUM    Check interval secs   (default: $CHECK_INTERVAL)
131	  -a TYPE   Alert method: log|email|slack (default: $ALERT_METHOD)
132	  -e ADDR   Alert email address
133	  -w URL    Slack webhook URL
134	  -l PATH   Log file path         (default: $LOG_FILE)
135	  -1        Run once and exit
136	  -h        Show this help
137	EOF
138	    exit 0
139	}
140	
141	RUN_ONCE=false
142	
143	while getopts "c:m:d:i:a:e:w:l:1h" opt; do
144	    case $opt in
145	        c) CPU_THRESHOLD=$OPTARG ;;
146	        m) MEM_THRESHOLD=$OPTARG ;;
147	        d) DISK_THRESHOLD=$OPTARG ;;
148	        i) CHECK_INTERVAL=$OPTARG ;;
149	        a) ALERT_METHOD=$OPTARG ;;
150	        e) ALERT_EMAIL=$OPTARG ;;
151	        w) SLACK_WEBHOOK_URL=$OPTARG ;;
152	        l) LOG_FILE=$OPTARG ;;
153	        1) RUN_ONCE=true ;;
154	        h) usage ;;
155	        *) usage ;;
156	    esac
157	done
158	
159	log "Monitor started — CPU>${CPU_THRESHOLD}% MEM>${MEM_THRESHOLD}% DISK>${DISK_THRESHOLD}% every ${CHECK_INTERVAL}s (alert via ${ALERT_METHOD})"
160	
161	if $RUN_ONCE; then
162	    check_cpu
163	    check_memory
164	    check_disk
165	    exit 0
166	fi
167	
168	trap 'log "Monitor stopped."; exit 0' INT TERM
169	
170	while true; do
171	    check_cpu
172	    check_memory
173	    check_disk
174	    sleep "$CHECK_INTERVAL"
175	done
176	

### Turn 6 (tool)
1	#!/usr/bin/env bash
2	set -euo pipefail
3	
4	# Configuration
5	THRESHOLD=${DISK_THRESHOLD:-80}
6	TARGET_DIRS=(${CLEANUP_DIRS:-"/tmp /var/log"})
7	MAX_AGE_DAYS=${MAX_AGE:-30}
8	LOG_FILE=${LOG_FILE:-"/var/log/disk_monitor.log"}
9	DRY_RUN=${DRY_RUN:-false}
10	
11	log() {
12	    local level="$1"
13	    shift
14	    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
15	    echo "$msg" | tee -a "$LOG_FILE" 2>/dev/null || echo "$msg"
16	}
17	
18	check_disk_usage() {
19	    local mount="${1:-/}"
20	    local usage
21	    usage=$(df "$mount" | awk 'NR==2 {gsub(/%/,""); print $5}')
22	    echo "$usage"
23	}
24	
25	find_old_files() {
26	    local dir="$1"
27	    local age="$2"
28	    if [[ ! -d "$dir" ]]; then
29	        log "WARN" "Directory does not exist: $dir"
30	        return 1
31	    fi
32	    find "$dir" -type f -mtime +"$age" -print 2>/dev/null
33	}
34	
35	cleanup_file() {
36	    local file="$1"
37	    if [[ "$DRY_RUN" == "true" ]]; then
38	        log "DRY-RUN" "Would delete: $file"
39	        return 0
40	    fi
41	    if rm -f "$file" 2>>"$LOG_FILE"; then
42	        log "INFO" "Deleted: $file"
43	        return 0
44	    else
45	        log "ERROR" "Failed to delete: $file"
46	        return 1
47	    fi
48	}
49	
50	main() {
51	    log "INFO" "Starting disk monitor (threshold=${THRESHOLD}%, max_age=${MAX_AGE_DAYS}d, dry_run=${DRY_RUN})"
52	
53	    local usage
54	    usage=$(check_disk_usage "/")
55	    log "INFO" "Current disk usage: ${usage}%"
56	
57	    if (( usage < THRESHOLD )); then
58	        log "INFO" "Disk usage ${usage}% is below threshold ${THRESHOLD}%. No action needed."
59	        exit 0
60	    fi
61	
62	    log "WARN" "Disk usage ${usage}% exceeds threshold ${THRESHOLD}%. Starting cleanup..."
63	
64	    local deleted=0
65	    local failed=0
66	
67	    for dir in "${TARGET_DIRS[@]}"; do
68	        log "INFO" "Scanning: $dir"
69	        while IFS= read -r file; do
70	            [[ -z "$file" ]] && continue
71	            if cleanup_file "$file"; then
72	                ((deleted++))
73	            else
74	                ((failed++))
75	            fi
76	        done < <(find_old_files "$dir" "$MAX_AGE_DAYS")
77	    done
78	
79	    local new_usage
80	    new_usage=$(check_disk_usage "/")
81	    log "INFO" "Cleanup complete. Files deleted: $deleted, failed: $failed"
82	    log "INFO" "Disk usage after cleanup: ${new_usage}%"
83	
84	    if (( new_usage >= THRESHOLD )); then
85	        log "WARN" "Disk usage still above threshold after cleanup. Manual intervention may be required."
86	        exit 1
87	    fi
88	
89	    log "INFO" "Disk usage restored below threshold."
90	    exit 0
91	}
92	
93	main "$@"
94	

### Turn 7 (assistant)
Now I'll create the queue depth monitor script following the same conventions as the existing monitoring scripts.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/queue_monitor.sh",
  "content": "#!/usr/bin/env bash\n#\n# Queue Depth Monitor\n# Monitors queue depth and sends alerts when thresholds are exceeded.\n# Supports multiple queue backends: RabbitMQ, Redis, AWS SQS, custom script.\n\nset -euo pipefail\n\n# --- Configuration (override via environment) ---\nQUEUE_BACKEND=\"${QUEUE_BACKEND:-custom}\"          # rabbitmq | redis | sqs | custom\nWARNING_THRESHOLD=\"${WARNING_THRESHOLD:-1000}\"     # warning alert 
```

### Turn 8 (tool)
File created successfully at: /data/agent/choucisan/queue_monitor.sh (file state is current in your context — no need to Read it back)

### Turn 9 (assistant)
**Tool**: `Bash`
```json
{
  "command": "chmod +x /data/agent/choucisan/queue_monitor.sh",
  "description": "Make script executable"
}
```

### Turn 10 (tool)
(Bash completed with no output)

### Turn 11 (assistant)
Created `queue_monitor.sh`. Here's what it does:

**Supported backends** (`-b` flag or `QUEUE_BACKEND` env var):
- **rabbitmq** — polls the management API (`/api/queues`)
- **redis** — checks `LLEN` on specified list keys
- **sqs** — queries `ApproximateNumberOfMessages` via AWS CLI
- **custom** — runs any script that outputs `queue_name depth` per line

**Alerting:**
- Two-tier thresholds: **warning** (default 1000) and **critical** (default 5000)
- Recovery alerts when depth drops back below thresholds
- Cooldown of 300s per queue+severity to avoid spam
- Methods: `log`, `email` (via `mail`), `slack` (webhook), `webhook` (generic JSON POST)

**Usage examples:**

```bash
# One-shot check with defaults
./queue_monitor.sh -1

# Continuous RabbitMQ monitoring, Slack alerts
QUEUE_BACKEND=rabbitmq ALERT_METHOD=slack SLACK_WEBHOOK_URL=https://hooks.slack.com/... ./queue_monitor.sh

# Redis queue monitoring with custom thresholds
QUEUE_BACKEND=redis REDIS_QUEUE_KEYS="tasks:pending,tasks:failed" \
  WARNING_THRESHOLD=500 CRITICAL_THRESHOLD=2000 ./queue_monitor.sh

# SQS with generic webhook
QUEUE_BACKEND=sqs SQS_QUEUE_URLS="https://sqs.us-east-1.amazonaws.com/123/my-q" \
  ALERT_METHOD=webhook WEBHOOK_URL=https://example.com/alerts ./queue_monitor.sh
```

All configuration is overridable via environment variables or CLI flags, matching the pattern of your existing `system_monitor.sh` and `disk_monitor.sh`.

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