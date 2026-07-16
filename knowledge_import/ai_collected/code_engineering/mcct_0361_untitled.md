# Write a Python decorator that adds timeout support to a function. Include usage examples and tests.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python decorator that adds timeout support to a function. Include usage examples and tests.

## Conversation
### Turn 1 (user)
Write a Python decorator that adds timeout support to a function. Include usage examples and tests.

### Turn 2 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/",
  "description": "List files in working directory"
}
```

### Turn 3 (tool)
aho_corasick.py
airscape_bench.jsonl
airscape_qa.jsonl
AirScape_Train_list.txt
airtable
api_etl_pipeline.py
arbitrary_precision.py
astar.py
base_converter.py
bellman_ford.py
binomial_coefficient.py
blog-ws-api
bloom_filter.js
btree.py
cache_with_ttl.go
cache_with_ttl.js
cache_with_ttl.rs
cache_with_ttl_test.go
calculator.py
call_tracer.py
cam_motion
CamReasoner
Cargo.lock
Cargo.toml
catalan.py
chunk_iterator.go
chunk_iterator_test.go
circuit_breaker.py
circular_buffer.go
circular_buffer.js
circular_buffer.py
circular_buffer_test.go
circular_buffer.test.js
code
coin_change.py
compress_string.py
concatenate.py
connection_pool.py
convex_hull.py
csv_to_markdown.py
csv_to_sql_pipeline.py
cuda_12.8.0_570.86.10_linux.run
data
data_processor.py
debounce
debounce.rs
deploy
deploy.conf.example
deploy.sh
dfs.py
dijkstra.py
disk_monitor_cleanup.sh
distributed_lock.rb
distributed_lock_test.rb
docker-compose.yml
Dockerfile
docs
Dog100K
email-module
env_batch.py
etl_pipeline.py
excel_to_sql.py
factorial.py
fdagent
fdagent.tar.gz
fenwick_tree.py
fibonacci.py
find_duplicates.py
find_min_max.py
flash-attention-2.7.4
flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp310-cp310-linux_x86_64.whl
format_converter.py
fraction_period.py
gaussian_elimination.py
Gemfile
gen_table.py
go
go-http-server.service
go.mod
google-sheets-proxy
gpt1
graphql-auth-middleware
health_monitor.sh
heapsort.py
hyper_log_log.py
hyperloglog.py
jira-proxy
jsonl_validator.py
json_to_sql_pipeline.py
kadane.py
kruskal.py
line_intersection.py
log_aggregator.py
loganalyzer
log_etl_pipeline.py
longest_palindrome.py
lru_cache.go
lru_cache.js
lru_cache.py
lru_cache_test.go
main.py
majority_vote.py
Makefile
max_subarray.py
mediator_refactor.py
memoize_context.py
merge_jsonl.py
message_queue.py
metrics_collector.py
mimo-claude-code-traces
min_heap.py
min_max.py
mo_algorithm.cpp
motion-mllm
motion-mllms
motion-mllmss
motion-mllm-v1
nginx.conf
optimized.py
paginate_results.js
paper.tex
parquet_sampler.py
parquet_to_html.py
parse_expression.py
parse_jsonl.py
partition_function.py
pascal_triangle.py
payment_webhook.py
pivot.py
plan.md
pollard_rho.py
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
request_logging_middleware
requirements-dev.txt
requirements.txt
response_time_monitor.sh
retry_context.py
right_triangle.py
routes.py
ruff.toml
run_all.sh
run_length_encoding.go
run_length_encoding_test.go
s3_ws_client
sample.csv
sample_data.json
sample_employees.csv
sample_employees.sql
sample.jsonl
sample_logs
sample_schema.json
scc.py
scraper.py
segment_tree_metrics.py
segment_tree.py
sendgrid-proxy
serialize_tree.js
serialize_tree.py
serialize_tree.test.js
servers.conf
shoelace.py
sieve_of_atkin.py
skip_list.py
slack_api
sliding_window_maximum.py
spring-boot.Dockerfile
sql_to_pg_pipeline.py
src
strategies.py
streaming_xml_parser.py
suffix_array.py
suffix_tree_bruteforce.py
suffix_tree_compare.py
suffix_tree.py
t2v_metrics
target
tarjan_scc.py
task_scheduler.py
test_aho_corasick.py
test_astar.py
test_compress_string.py
test_connection_pool.py
test_env1.env
test_env2.env
test_find_duplicates.py
test_jsonl_validator.py
test_kruskal.py
test_memoize_context.py
test_retry_context.py
tests
test_schema.json
test_scraper.py
test_three_sum.py
test_validate_schema.py
th.md
three_sum.py
throttle_function.go
throttle_function.py
throttle_function_test.go
timeout_context.py
topological_sort.py
trainingfree
tree
trie_node.py
twilio-graphql
two_sum.js
uav_accuracy_comparison.png
uavdown
UAVideo
UAVideo-Bench
uav-train-lora
url_shortener.js
url_shortener.test.js
validate_schema.py
videoRL
webhook_receiver.py
web_scraper_etl.py
xml_pivot.py
yaml_merger.py

### Turn 4 (assistant)
There's already a `timeout_context.py` in the repo. Let me check it, then create the decorator.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/timeout_context.py"
}
```

### Turn 5 (tool)
1	"""Context manager that adds timeout support to function calls."""
2	
3	import signal
4	import threading
5	import time
6	from contextlib import contextmanager
7	from functools import wraps
8	
9	
10	class TimeoutError(Exception):
11	    """Raised when an operation exceeds the allowed time."""
12	
13	
14	@contextmanager
15	def timeout(seconds):
16	    """Context manager that raises TimeoutError after `seconds`.
17	
18	    Uses signal.SIGALRM on Unix (main thread only) and falls back to
19	    a threading-based timer otherwise.
20	
21	    Usage:
22	        with timeout(5):
23	            long_running_function()
24	    """
25	    if seconds <= 0:
26	        raise ValueError("timeout must be positive")
27	
28	    # Try signal-based approach (Unix main thread only)
29	    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
30	        old_handler = signal.signal(signal.SIGALRM, _handler)
31	        signal.setitimer(signal.ITIMER_REAL, seconds)
32	        try:
33	            yield
34	        finally:
35	            signal.setitimer(signal.ITIMER_REAL, 0)
36	            signal.signal(signal.SIGALRM, old_handler)
37	    else:
38	        # Thread-based fallback
39	        timer = threading.Timer(seconds, _set_flag)
40	        fired = threading.Event()
41	        _timer_events[id(timer)] = fired
42	        timer.start()
43	        try:
44	            yield
45	        finally:
46	            timer.cancel()
47	            _timer_events.pop(id(timer), None)
48	            if fired.is_set():
49	                raise TimeoutError(f"Operation timed out after {seconds}s")
50	
51	
52	def _handler(signum, frame):
53	    raise TimeoutError("Operation timed out")
54	
55	
56	# Thread-based fallback state
57	_timer_events: dict[int, threading.Event] = {}
58	
59	
60	def _set_flag():
61	    # Walk all active timer events and set them (last one is the active one)
62	    for event in _timer_events.values():
63	        event.set()
64	
65	
66	def with_timeout(seconds):
67	    """Decorator that kills a function call after `seconds`.
68	
69	    Usage:
70	        @with_timeout(5)
71	        def slow_function():
72	            ...
73	    """
74	    def decorator(func):
75	        @wraps(func)
76	        def wrapper(*args, **kwargs):
77	            with timeout(seconds):
78	                return func(*args, **kwargs)
79	        return wrapper
80	    return decorator
81	
82	
83	# --- Examples ---
84	
85	def example_basic():
86	    """Basic timeout usage."""
87	    print("--- Basic timeout example ---")
88	    try:
89	        with timeout(1):
90	            time.sleep(5)  # Will be interrupted
91	    except TimeoutError as e:
92	        print(f"Caught: {e}")
93	
94	
95	def example_no_timeout():
96	    """Operation completes within the deadline."""
97	    print("--- No timeout example ---")
98	    with timeout(3):
99	        result = sum(range(1000))
100	    print(f"Result: {result}")
101	
102	
103	def example_decorator():
104	    """Using the @with_timeout decorator."""
105	    print("--- Decorator example ---")
106	
107	    @with_timeout(1)
108	    def fast_enough():
109	        return 42
110	
111	    @with_timeout(0.5)
112	    def too_slow():
113	        time.sleep(5)
114	
115	    print(f"fast_enough() = {fast_enough()}")
116	    try:
117	        too_slow()
118	    except TimeoutError as e:
119	        print(f"Caught: {e}")
120	
121	
122	def example_nested():
123	    """Nested timeouts — inner deadline wins."""
124	    print("--- Nested timeout example ---")
125	    try:
126	        with timeout(10):
127	            with timeout(1):
128	                time.sleep(5)
129	    except TimeoutError as e:
130	        print(f"Caught inner timeout: {e}")
131	
132	
133	# --- Tests ---
134	
135	import unittest
136	
137	
138	class TestTimeout(unittest.TestCase):
139	
140	    def test_raises_on_expired(self):
141	        with self.assertRaises(TimeoutError):
142	            with timeout(0.3):
143	                time.sleep(5)
144	
145	    def test_no_raise_when_fast(self):
146	        with timeout(3):
147	            x = 1 + 1
148	        self.assertEqual(x, 2)
149	
150	    def test_returns_value(self):
151	        with timeout(3):
152	            result = "ok"
153	        self.assertEqual(result, "ok")
154	
155	    def test_zero_raises_valueerror(self):
156	        with self.assertRaises(ValueError):
157	            with timeout(0):
158	                pass
159	
160	    def test_negative_raises_valueerror(self):
161	        with self.assertRaises(ValueError):
162	            with timeout(-1):
163	                pass
164	
165	    def test_cleanup_runs_finally(self):
166	        cleaned = False
167	        try:
168	            with timeout(0.3):
169	                cleaned = True  # noqa: F841
170	                time.sleep(5)
171	        except TimeoutError:
172	            pass
173	        self.assertTrue(cleaned)
174	
175	    def test_nested_inner_wins(self):
176	        start = time.monotonic()
177	        with self.assertRaises(TimeoutError):
178	            with timeout(10):
179	                with timeout(0.3):
180	                    time.sleep(5)
181	        elapsed = time.monotonic() - start
182	        self.assertLess(elapsed, 2)
183	
184	    def test_decorator_raises(self):
185	        @with_timeout(0.3)
186	        def slow():
187	            time.sleep(5)
188	
189	        with self.assertRaises(TimeoutError):
190	            slow()
191	
192	    def test_decorator_returns(self):
193	        @with_timeout(3)
194	        def fast():
195	            return "done"
196	
197	        self.assertEqual(fast(), "done")
198	
199	    def test_timeout_precision(self):
200	        start = time.monotonic()
201	        with self.assertRaises(TimeoutError):
202	            with timeout(1):
203	                time.sleep(10)
204	        elapsed = time.monotonic() - start
205	        self.assertLess(abs(elapsed - 1.0), 0.5)
206	
207	
208	if __name__ == "__main__":
209	    example_basic()
210	    print()
211	    example_no_timeout()
212	    print()
213	    example_decorator()
214	    print()
215	    example_nested()
216	    print()
217	    print("Running tests...")
218	    unittest.main(verbosity=2)
219	

### Turn 6 (assistant)
This file already exists with a full implementation. Let me verify it runs correctly.
**Tool**: `Bash`
```json
{
  "command": "python timeout_context.py 2>&1",
  "description": "Run existing timeout decorator with examples and tests",
  "timeout": 30000
}
```

### Turn 7 (tool)
test_cleanup_runs_finally (__main__.TestTimeout) ... ok
test_decorator_raises (__main__.TestTimeout) ... ok
test_decorator_returns (__main__.TestTimeout) ... ok
test_negative_raises_valueerror (__main__.TestTimeout) ... ok
test_nested_inner_wins (__main__.TestTimeout) ... ok
test_no_raise_when_fast (__main__.TestTimeout) ... ok
test_raises_on_expired (__main__.TestTimeout) ... ok
test_returns_value (__main__.TestTimeout) ... ok
test_timeout_precision (__main__.TestTimeout) ... ok
test_zero_raises_valueerror (__main__.TestTimeout) ... ok

----------------------------------------------------------------------
Ran 10 tests in 2.204s

OK
--- Basic timeout example ---
Caught: Operation timed out

--- No timeout example ---
Result: 499500

--- Decorator example ---
fast_enough() = 42
Caught: Operation timed out

--- Nested timeout example ---
Caught inner timeout: Operation timed out

Running tests...

### Turn 8 (assistant)
The file `timeout_context.py` already exists in your repo with a complete implementation. All 10 tests pass and all 4 examples run correctly. Here's what's in it:

**Core components:**

- **`timeout(seconds)`** — a context manager (`with timeout(5): ...`) that raises `TimeoutError` if the block exceeds the deadline. Uses `signal.SIGALRM` on Unix main threads, falls back to a `threading.Timer` otherwise.
- **`with_timeout(seconds)`** — a decorator that wraps any function with the timeout context manager.

**Usage examples:**

| Example | What it shows |
|---|---|
| `example_basic()` | Context manager raises on `time.sleep(5)` with a 1s deadline |
| `example_no_timeout()` | Fast work completes normally |
| `example_decorator()` | `@with_timeout` on two functions — one fast, one slow |
| `example_nested()` | Inner timeout wins when nesting |

**Tests cover:** expiry, no-expiry, return values, zero/negative validation, cleanup in `finally`, nested timeout behavior, decorator form, and timing precision.

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