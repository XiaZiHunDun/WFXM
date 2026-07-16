# Write a Python function called `rate_limiter` that chunks an iterable into groups of size n. Include
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python function called `rate_limiter` that chunks an iterable into groups of size n. Include comprehensive test cases.

## Conversation
### Turn 1 (user)
Write a Python function called `rate_limiter` that chunks an iterable into groups of size n. Include comprehensive test cases.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/rate_limiter.py",
  "content": "from itertools import islice\nfrom typing import Iterable, Iterator, TypeVar\n\nT = TypeVar(\"T\")\n\n\ndef rate_limiter(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:\n    \"\"\"Chunk an iterable into tuples of size n.\n\n    The final chunk may have fewer than n elements if the iterable\n    length is not evenly divisible by n.\n    \"\"\"\n    if n < 1:\n        raise ValueError(\"n must be >= 1\")\n    it = i
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/",
  "description": "List files in working directory"
}
```

### Turn 5 (tool)
actix-app.service
aho_corasick.py
airscape_bench.jsonl
airscape_qa.jsonl
AirScape_Train_list.txt
airtable
airtable_client
airtable-proxy
analytics-graphql-api
analyze_jsonl.py
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
bloom_filter.test.js
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
compress_string.js
compress_string.py
compress_string_test.go
compute_pi.py
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
defaultdict.py
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
ecommerce-api
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
github_rest_client
go
go.Dockerfile
go-http-server.service
go.mod
google-sheets-proxy
gpt1
graphql-auth-middleware
hanoi.py
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
output.sql
package.json
package-lock.json
paginate_results.go
paginate_results.js
paginate_results_test.go
paper.tex
parquet_sampler.py
parquet_to_html.py
parquet_to_sql.py
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
processor.py
process.py
pubsub_segment_tree.py
__pycache__
pythagorean_triples.py
quadratic_solver.py
queue_monitor.sh
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
rotate_logs.sh
router.py
routes.py
routing.py
ruff.toml
run_all.sh
run_length_encoding.go
run_length_encoding_test.go
s3_rest_client
s3_ws_client
sample.csv
sample_data.json
sample_data.jsonl
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
sample_sales.csv
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
sparse_table.py
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
test_suffix_tree.py
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
yaml_pivot.py
yaml_schema_validator.py
yaml_to_html.py
yaml_to_json.py

### Turn 6 (assistant)
The file already exists. Let me read it first.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/rate_limiter.py"
}
```

### Turn 7 (tool)
1	"""Rate-limiter context manager and decorator for Python function calls.
2	
3	Provides:
4	- ``RateLimiter`` class usable as both a context manager and decorator
5	- ``rate_limit()`` helper context manager
6	- Backward-compatible ``rate_limiter()`` function for thread-pool execution
7	"""
8	
9	from __future__ import annotations
10	
11	import threading
12	import time
13	from concurrent.futures import Future, ThreadPoolExecutor, as_completed
14	from contextlib import contextmanager
15	from dataclasses import dataclass
16	from functools import wraps
17	from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
18	
19	
20	# ---------------------------------------------------------------------------
21	# Context manager / decorator rate limiter
22	# ---------------------------------------------------------------------------
23	
24	
25	class RateLimiter:
26	    """Rate-limit calls to at most *max_calls* per *period* seconds.
27	
28	    Uses a sliding window: tracks timestamps of recent calls and sleeps
29	    when the window is full.  Thread-safe.
30	
31	    Can be used three ways:
32	
33	    1. **Context manager** – one ``with`` block per call::
34	
35	           limiter = RateLimiter(3)
36	           for item in items:
37	               with limiter:
38	                   process(item)
39	
40	    2. **Decorator** – every invocation of the wrapped function is limited::
41	
42	           @RateLimiter(max_calls=2, period=1.0)
43	           def call_api(endpoint): ...
44	
45	    3. **Manual** – call ``.wait()`` before the operation::
46	
47	           limiter = RateLimiter(5, period=1.0)
48	           for item in items:
49	               limiter.wait()
50	               process(item)
51	    """
52	
53	    def __init__(self, max_calls: int, period: float = 1.0):
54	        if max_calls < 1:
55	            raise ValueError("max_calls must be >= 1")
56	        if period <= 0:
57	            raise ValueError("period must be > 0")
58	        self.max_calls = max_calls
59	        self.period = period
60	        self._timestamps: list[float] = []
61	        self._lock = threading.Lock()
62	
63	    # -- sliding-window helpers --------------------------------------------
64	
65	    def _prune(self, now: float) -> None:
66	        """Remove timestamps outside the current window."""
67	        cutoff = now - self.period
68	        while self._timestamps and self._timestamps[0] <= cutoff:
69	            self._timestamps.pop(0)
70	
71	    # -- public API --------------------------------------------------------
72	
73	    def wait(self) -> None:
74	        """Block until a call is permitted, then record it."""
75	        with self._lock:
76	            now = time.monotonic()
77	            self._prune(now)
78	            if len(self._timestamps) >= self.max_calls:
79	                sleep_until = self._timestamps[0] + self.period
80	                delay = sleep_until - now
81	                if delay > 0:
82	                    time.sleep(delay)
83	                now = time.monotonic()
84	                self._prune(now)
85	            self._timestamps.append(now)
86	
87	    # -- context manager protocol ------------------------------------------
88	
89	    def __enter__(self):
90	        self.wait()
91	        return self
92	
93	    def __exit__(self, *exc_info):
94	        return False
95	
96	    # -- decorator protocol ------------------------------------------------
97	
98	    def __call__(self, func: Callable) -> Callable:
99	        @wraps(func)
100	        def wrapper(*args, **kwargs):
101	            with self:
102	                return func(*args, **kwargs)
103	        return wrapper
104	
105	
106	@contextmanager
107	def rate_limit(max_calls: int, period: float = 1.0):
108	    """Yield a :class:`RateLimiter` that has already waited for its slot.
109	
110	    >>> with rate_limit(3, period=1.0) as rl:
111	    ...     for item in items:
112	    ...         rl.wait()
113	    ...         process(item)
114	    """
115	    limiter = RateLimiter(max_calls, period)
116	    with limiter:
117	        yield limiter
118	
119	
120	# ---------------------------------------------------------------------------
121	# Thread-pool executor (backward-compatible)
122	# ---------------------------------------------------------------------------
123	
124	
125	@dataclass
126	class TaskResult:
127	    """Result of a single executed task."""
128	
129	    task_id: str
130	    result: Any = None
131	    exception: Optional[BaseException] = None
132	    elapsed: float = 0.0
133	
134	    @property
135	    def succeeded(self) -> bool:
136	        return self.exception is None
137	
138	
139	class ParallelRateLimiter:
140	    """Execute callables in a thread pool while enforcing a rate limit.
141	
142	    Args:
143	        max_workers: Thread-pool size.  ``None`` for the default.
144	        rate: Max task starts per second (``0`` for unlimited).
145	    """
146	
147	    def __init__(
148	        self,
149	        max_workers: Optional[int] = None,
150	        rate: float = 0,
151	    ) -> None:
152	        if rate < 0:
153	            raise ValueError("rate must be non-negative")
154	        self._max_workers = max_workers
155	        self._rate = rate
156	        self._lock = threading.Lock()
157	        self._last_submit: float = 0.0
158	
159	    def execute(
160	        self,
161	        tasks: Sequence[Tuple[str, Callable[..., Any], tuple, dict]],
162	    ) -> List[TaskResult]:
163	        """Run *tasks* concurrently, respecting the rate limit.
164	
165	        Each element of *tasks* is a tuple of
166	        ``(task_id, func, args, kwargs)``.
167	        """
168	        if not tasks:
169	            return []
170	
171	        results: Dict[str, TaskResult] = {}
172	        interval = (1.0 / self._rate) if self._rate else 0.0
173	
174	        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
175	            futures: Dict[Future, str] = {}
176	            for task_id, func, args, kwargs in tasks:
177	                self._throttle(interval)
178	                future = pool.submit(self._run, task_id, func, args, kwargs)
179	                futures[future] = task_id
180	
181	            for future in as_completed(futures):
182	                tr: TaskResult = future.result()
183	                results[tr.task_id] = tr
184	
185	        return [results[tid] for tid, _, _, _ in tasks]
186	
187	    @staticmethod
188	    def _run(
189	        task_id: str,
190	        func: Callable[..., Any],
191	        args: tuple,
192	        kwargs: dict,
193	    ) -> TaskResult:
194	        start = time.monotonic()
195	        try:
196	            result = func(*args, **kwargs)
197	            return TaskResult(
198	                task_id=task_id,
199	                result=result,
200	                elapsed=time.monotonic() - start,
201	            )
202	        except BaseException as exc:
203	            return TaskResult(
204	                task_id=task_id,
205	                exception=exc,
206	                elapsed=time.monotonic() - start,
207	            )
208	
209	    def _throttle(self, interval: float) -> None:
210	        if interval <= 0:
211	            return
212	        with self._lock:
213	            now = time.monotonic()
214	            wait = interval - (now - self._last_submit)
215	            if wait > 0:
216	                time.sleep(wait)
217	            self._last_submit = time.monotonic()
218	
219	
220	def rate_limiter(
221	    tasks: Sequence[Tuple[str, Callable[..., Any], tuple, dict]],
222	    max_workers: Optional[int] = None,
223	    rate: float = 0,
224	) -> List[TaskResult]:
225	    """Convenience wrapper around :class:`ParallelRateLimiter`."""
226	    return ParallelRateLimiter(max_workers=max_workers, rate=rate).execute(tasks)
227	
228	
229	# ---------------------------------------------------------------------------
230	# Usage examples
231	# ---------------------------------------------------------------------------
232	
233	if __name__ == "__main__":
234	    # Example 1: Context manager
235	    print("--- Context manager (5 calls, max 3/sec) ---")
236	    limiter = RateLimiter(max_calls=3, period=1.0)
237	    for i in range(5):
238	        with limiter:
239	            print(f"  call {i} at t={time.monotonic():.3f}s")
240	
241	    # Example 2: Decorator
242	    print("\n--- Decorator (5 calls, max 2/sec) ---")
243	
244	    @RateLimiter(max_calls=2, period=1.0)
245	    def api_call(endpoint: str) -> dict:
246	        print(f"  GET {endpoint} at t={time.monotonic():.3f}s")
247	        return {"status": 200}
248	
249	    for ep in ["/users", "/posts", "/comments", "/tags", "/health"]:
250	        api_call(ep)
251	
252	    # Example 3: rate_limit() helper
253	    print("\n--- rate_limit() helper (4 calls, max 2/sec) ---")
254	    with rate_limit(max_calls=2, period=1.0) as rl:
255	        for i in range(4):
256	            rl.wait()
257	            print(f"  item {i} at t={time.monotonic():.3f}s")
258	

### Turn 8 (assistant)
The existing `rate_limiter.py` is a different implementation (call-rate limiting). I'll create the chunking function in a new file to avoid overwriting it.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/rate_limiter_chunk.py",
  "content": "from itertools import islice\nfrom typing import Iterable, Iterator, TypeVar\n\nT = TypeVar(\"T\")\n\n\ndef rate_limiter(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:\n    \"\"\"Chunk an iterable into tuples of size n.\n\n    The final chunk may have fewer than n elements if the iterable\n    length is not evenly divisible by n.\n    \"\"\"\n    if n < 1:\n        raise ValueError(\"n must be >= 1\")\n    
```

### Turn 9 (tool)
File created successfully at: /data/agent/choucisan/rate_limiter_chunk.py (file state is current in your context — no need to Read it back)

### Turn 10 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python rate_limiter_chunk.py -v",
  "description": "Run tests"
}
```

### Turn 11 (tool)
Exit code 1
test_chunk_size_one (__main__.TestRateLimiter) ... ok
test_empty_iterable (__main__.TestRateLimiter) ... ok
test_evenly_divisible (__main__.TestRateLimiter) ... ok
test_generator_input (__main__.TestRateLimiter) ... ok
test_large_iterable (__main__.TestRateLimiter) ... ok
test_n_negative_raises (__main__.TestRateLimiter) ... ok
test_n_zero_raises (__main__.TestRateLimiter) ... ok
test_remainder (__main__.TestRateLimiter) ... ok
test_returns_tuples (__main__.TestRateLimiter) ... ok
test_reusable (__main__.TestRateLimiter) ... FAIL
test_single_chunk (__main__.TestRateLimiter) ... ok
test_single_element (__main__.TestRateLimiter) ... ok
test_string_iterable (__main__.TestRateLimiter) ... ok
test_tuple_input (__main__.TestRateLimiter) ... ok

======================================================================
FAIL: test_reusable (__main__.TestRateLimiter)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/data/agent/choucisan/rate_limiter_chunk.py", line 114, in test_reusable
    self.assertEqual(list(limiter), [(1, 2), (3,)])
AssertionError: Lists differ: [] != [(1, 2), (3,)]

Second list contains 2 additional elements.
First extra element 0:
(1, 2)

- []
+ [(1, 2), (3,)]

----------------------------------------------------------------------
Ran 14 tests in 0.001s

FAILED (failures=1)

### Turn 12 (assistant)
The `test_reusable` test is wrong — generators aren't reusable. I'll fix it to reflect actual generator behavior.
**Tool**: `Edit`
```json
{
  "replace_all": false,
  "file_path": "/data/agent/choucisan/rate_limiter_chunk.py",
  "old_string": "        # -- idempotent re-iteration -----------------------------------------\n\n        def test_reusable(self):\n            limiter = rate_limiter([1, 2, 3], 2)\n            self.assertEqual(list(limiter), [(1, 2), (3,)])\n            self.assertEqual(list(limiter), [(1, 2), (3,)])",
  "new_string": "        # -- generator is single-use ----------------------------------------\n\n        
```

### Turn 13 (tool)
The file /data/agent/choucisan/rate_limiter_chunk.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 14 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python rate_limiter_chunk.py -v",
  "description": "Run tests again"
}
```

### Turn 15 (tool)
test_chunk_size_one (__main__.TestRateLimiter) ... ok
test_empty_iterable (__main__.TestRateLimiter) ... ok
test_evenly_divisible (__main__.TestRateLimiter) ... ok
test_generator_exhausted_after_first_pass (__main__.TestRateLimiter) ... ok
test_generator_input (__main__.TestRateLimiter) ... ok
test_large_iterable (__main__.TestRateLimiter) ... ok
test_n_negative_raises (__main__.TestRateLimiter) ... ok
test_n_zero_raises (__main__.TestRateLimiter) ... ok
test_remainder (__main__.TestRateLimiter) ... ok
test_returns_tuples (__main__.TestRateLimiter) ... ok
test_single_chunk (__main__.TestRateLimiter) ... ok
test_single_element (__main__.TestRateLimiter) ... ok
test_string_iterable (__main__.TestRateLimiter) ... ok
test_tuple_input (__main__.TestRateLimiter) ... ok

----------------------------------------------------------------------
Ran 14 tests in 0.001s

OK

### Turn 16 (assistant)
All 14 tests pass. Created `rate_limiter_chunk.py` with:

- **`rate_limiter(iterable, n)`** — yields tuples of size `n` from any iterable, with the last chunk containing the remaining elements
- **14 test cases** covering: evenly divisible, remainder, single chunk, chunk size 1, empty input, single element, generators, strings, tuples, return type validation, error handling (`n < 1`), large input (10k items), and generator exhaustion behavior

Note: the existing `rate_limiter.py` contains a different implementation (call-rate limiting with `RateLimiter` class), so I wrote this to a separate file.

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