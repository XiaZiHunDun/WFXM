# Write a Python decorator that traces function calls and builds a call graph. Include usage examples 
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python decorator that traces function calls and builds a call graph. Include usage examples and tests.

## Conversation
### Turn 1 (user)
Write a Python decorator that traces function calls and builds a call graph. Include usage examples and tests.

### Turn 2 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan",
  "description": "List files in working directory"
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
analyze_jsonl.py
api_codegen
api_etl_pipeline.py
arbitrary_precision.py
astar.py
backup_db.conf.example
backup_db.sh
backup_logs
base_converter.py
batch_operations_sample.json
batch_processor.py
bellman_ford.py
bernoulli.py
bfs.py
binomial_coefficient.py
blog-graphql-api
blog-rest-api
blog-ws-api
bloom_filter_expression.py
bloom_filter.go
bloom_filter.js
bloom_filter.py
bloom_filter_test.go
bloom_filter.test.js
boyer_moore.py
btree.py
bug.py
build
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
casinoSlots
catalan.py
characteristic_polynomial.py
chat-graphql-api
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
clean_architecture.py
cleaned_dates.md
cleaned_output.html
cleaned_output.md
cleaned_parquet.md
cleaned_sales.md
cloud_resource_cli.py
CMakeLists.txt
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
controllers
convex_hull.py
counter.py
count_min_sketch.go
count_min_sketch.py
count_min_sketch_test.go
csv_analyzer.py
csv_fuzzy_dedup.py
csv_html_pipeline.py
csv_loader_logs
csv_loader.sh
csv_sampler.py
csv_test_dir
csv_to_db_loader.sh
csv_to_json_pipeline.py
csv_to_markdown.py
csv_to_sql_pipeline.py
cuda_12.8.0_570.86.10_linux.run
data
data_processor.py
data_structures.py
db_backup.sh
db_batch_cli.py
db_etl_pipeline.py
db_parquet_etl.py
debounce
debounce.go
debounce.js
debounce.py
debounce.rs
debounce_test.go
deep_merge.js
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
discrete_log.py
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
Dockerfile.flask
Dockerfile.go
Dockerfile.rust
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
event_bus.rb
event_bus_test.rb
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
file-storage-api
file_uploaded_email_webhook.py
file_uploaded_webhook.py
find_duplicates.go
find_duplicates.js
find_duplicates.py
find_duplicates_test.go
find_min_max.py
fix_min_max.py
flash-attention-2.7.4
flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp310-cp310-linux_x86_64.whl
flask-app.service
flatten_nested_dict.py
floyd_warshall.py
format_converter.py
fraction_period.py
function_logger.py
gaussian_elimination.py
gcd_lcm.py
Gemfile
gen_table.py
github_api_client
github_pr_webhook.py
github_rest_client
go
go.Dockerfile
go-http-server.service
go.mod
google-sheets-proxy
google-sheets-wrapper
gpt1
graphql-auth-middleware
handlers.py
hanoi.py
health_monitor.sh
heapsort.py
huffman.cpp
huffman.h
hyper_log_log.py
hyperloglog.py
imagebatch.py
infix_to_postfix.js
infix_to_postfix.py
inventory-ws-api
jacobi.py
jira_client
jira-proxy
jobmanager.py
json_dedup.py
jsonl_to_html.py
jsonl_validator.py
json_sampler.py
json_schema_validator
json_schema_validator.py
json_to_sql_pipeline.py
json_to_sql.py
jwt-auth-module
kadane.py
kahn_topological_sort.py
kmp.py
kruskal.py
linear_congruence.py
line_intersection.py
linked_list_sort.py
log_aggregator.py
loganalyzer
log_etl_pipeline.py
log_report.sh
logrotate_remote.sh
longest_palindrome.py
lru_cache.go
lru_cache.js
lru_cache.py
lru_cache_test.go
main.py
majority_vote.py
Makefile
markdown-converter
max_finder.py
max_subarray.py
median_of_two_sorted_arrays.py
median_sorted_arrays.py
mediator_refactor.py
memoize_context.py
memoize_lru.py
memory_profiler_examples.py
memory_profiler.py
merge_csv.py
merge_excel.py
merge_jsonl.py
merge_json.py
merge_parquet.py
merge.py
merge_sorted_lists.go
merge_sorted_lists.js
merge_sorted_lists_test.go
mergesort_linked_list.py
message_queue.py
message_sent_webhook.py
metrics_collector.py
miller_rabin.py
mimo-claude-code-traces
min_heap.py
min_max.py
min_stack.py
mo_algorithm.cpp
mo_algorithm.py
mobius.py
models
modular_exponentiation.py
monitor_db_connections.sh
motion-mllm
motion-mllms
motion-mllmss
motion-mllm-v1
network_bandwidth_monitor.sh
newton.py
nginx-actix.conf
nginx.conf
nginx-flask.conf
nginx-react.conf
nginx-springboot.conf
nlp_tokenizer.cpp
nlp_tokenizer.h
nlp_tokenizer.rb
nlp_tokenizer_test.cpp
nlp_tokenizer_test.rb
node_modules
notion
notion_client
notion-proxy
optimized.py
ordered_dict.py
output.sql
package.json
package-lock.json
paginate_results.go
paginate_results.js
paginate_results_test.go
palindrome.rs
paper.tex
parquet_sampler.py
parquet_to_csv_pipeline.py
parquet_to_html.py
parquet_to_markdown_pipeline.py
parquet_to_sql.py
parse_categorical.py
parse_excel.py
parse_expression.go
parse_expression.js
parse_expression.py
parse_expression_test.go
parse_expression.test.js
parse_jsonl.py
parse_yaml_dates.py
partition_function.py
pascals_triangle.py
pascal_triangle.py
payment_webhook.py
perfect_numbers.py
perfect_square.py
pipeline_output.html
pipeline_sample.csv
pivot_csv.py
pivot.py
plan.md
point_segment_distance.py
pollard_rho.py
polygon_area.py
pricing.py
prim_mst.py
prim.py
prims_mst.py
priority_queue.js
priority_queue.py
prng_period.py
processor.py
process.py
pubsub_segment_tree.py
__pycache__
pyproject.toml
pythagorean_triples.py
quadratic_solver.py
queue_monitor.sh
quicksort.py
rabin_karp.py
rate_limiter_chunk.py
rate_limiter.go
rate_limiter.js
rate_limiter.py
rate_limiter_test.go
rate_limiter.test.js
rate_limit_middleware
react-frontend.service
rebuttal
red_black_tree.py
remote-dev-setup.sh
remote-setup-logs
renew-ssl.sh
reports
repositories
request_facade.py
request_handler.py
request_logging_middleware
requirements-dev.txt
requirements.txt
response_time_monitor.sh
retry_context.py
retry_decorator.py
retry.js
retry.test.js
retry_with_backoff.go
retry_with_backoff.py
retry_with_backoff_test.go
right_triangle.py
rle_compressor.py
roman_converter.js
roman_converter.py
roman_converter.rs
rotated_binary_search.py
rotate_logs.sh
router.py
routers
routes.py
routing.py
ruff.toml
run_all.sh
run_length_encoding.go
run_length_encoding_test.go
s3_client
s3_rest_client
s3_ws_client
safe_write.py
sample.csv
sample_data_clean.json
sample_data.csv
sample_data.json
sample_data.jsonl
sample_data.parquet
sample_data.report.txt
sample_data.xml
sample_data.yaml
sample_employees.csv
sample_employees.json
sample_employees.md
sample_employees.sql
sample_employees.xlsx
sample.jsonl
sample_logs
sample_messy_dropped.json
sample_messy.json
sample_messy.xml
sample_messy.yaml
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
services
setup-dev.log
setup-dev-rollback.sh
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
stirling.py
strategies.py
streaming_jsonl_parser.py
streaming_parquet_parser.py
streaming_xml_parser.py
stripe_wrapper
structured-logging
suffix_array.py
suffix_tree_bruteforce.py
suffix_tree_compare.py
suffix_tree.py
svd.py
sync_dirs.sh
sync_to_async.py
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
test_bfs.py
test_cloud_resource_cli.py
test_compress_string.py
test_connection_pool.py
test.db
test_email_utils.py
test_env1.env
test_env2.env
test_excel_data_validator.py
test_find_duplicates.js
test_find_duplicates.py
test_function_logger.py
test_heapsort.py
test_jobs.json
test_json_dedup.py
test_jsonl_validator.py
test_json_schema_validator.py
test_kmp.py
test_kruskal.py
test_lru_cache.py
test_memoize_context.py
test_memory_profiler.py
test_quicksort.py
test_rate_limiter.py
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
trie_metrics.py
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
user_registered_log_webhook.py
user_registered_webhook.py
validate_email.py
validate_schema.js
validate_schema.py
videoRL
webhook_receiver.py
web_scraper_etl.py
web_scraper_parquet_etl.py
web_scraper.py
ws_api_key_middleware
ws_validation_middleware
xml_analyzer.py
xml_data_validator
xml_pivot.py
xml_sampler.py
xml_to_json_pipeline.py
xml_to_markdown.py
xml_to_sql.py
yaml_analyzer.py
yaml_clean_pipeline.py
yaml_fuzzy_dedup.py
yaml_merg

### Turn 4 (assistant)
I see there's already a `call_tracer.py` file. Let me check it and then create a proper implementation.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/call_tracer.py"
}
```

### Turn 5 (tool)
1	"""Context manager that traces function calls and builds a call graph."""
2	
3	import sys
4	import time
5	from dataclasses import dataclass, field
6	
7	
8	@dataclass
9	class CallNode:
10	    """A node in the call graph representing a function."""
11	
12	    name: str
13	    call_count: int = 0
14	    total_time: float = 0.0
15	    children: dict[str, "CallNode"] = field(default_factory=dict)
16	
17	
18	class CallTracer:
19	    """Context manager that traces function calls and builds a call graph.
20	
21	    Usage:
22	        with CallTracer() as tracer:
23	            my_function()
24	        tracer.print_graph()
25	    """
26	
27	    def __init__(self, ignore_modules: tuple[str, ...] = ()):
28	        self.root = CallNode(name="<root>")
29	        self._ignore_modules = set(ignore_modules)
30	        self._call_stack: list[tuple[CallNode, float]] = []
31	        self._enabled = False
32	
33	    def __enter__(self) -> "CallTracer":
34	        self._enabled = True
35	        sys.setprofile(self._profile)
36	        return self
37	
38	    def __exit__(self, *exc_info) -> None:
39	        sys.setprofile(None)
40	        self._enabled = False
41	
42	    def _profile(self, frame, event, arg):
43	        if not self._enabled:
44	            return
45	
46	        module = frame.f_globals.get("__name__", "")
47	        if module in self._ignore_modules:
48	            return
49	
50	        # Skip CallTracer's own methods
51	        code = frame.f_code
52	        qualname = code.co_qualname if hasattr(code, "co_qualname") else code.co_name
53	        if qualname.startswith("CallTracer.") or qualname == "CallTracer":
54	            return
55	
56	        if event == "call":
57	            self._on_call(frame)
58	        elif event == "return":
59	            self._on_return(frame)
60	
61	    def _on_call(self, frame):
62	        name = self._qualname(frame)
63	        current = self._call_stack[-1][0] if self._call_stack else self.root
64	
65	        if name not in current.children:
66	            current.children[name] = CallNode(name=name)
67	
68	        node = current.children[name]
69	        node.call_count += 1
70	        self._call_stack.append((node, time.perf_counter()))
71	
72	    def _on_return(self, frame):
73	        if not self._call_stack:
74	            return
75	        node, start = self._call_stack.pop()
76	        node.total_time += time.perf_counter() - start
77	
78	    @staticmethod
79	    def _qualname(frame) -> str:
80	        code = frame.f_code
81	        qualname = code.co_qualname if hasattr(code, "co_qualname") else code.co_name
82	        module = frame.f_globals.get("__name__", "")
83	        return f"{module}.{qualname}" if module else qualname
84	
85	    def print_graph(self, node: CallNode | None = None, indent: int = 0) -> None:
86	        """Print the call graph as a tree."""
87	        if node is None:
88	            node = self.root
89	        prefix = "  " * indent
90	        if node.name == "<root>":
91	            label = "<root>"
92	        else:
93	            label = f"{node.name}  (calls={node.call_count}, time={node.total_time*1000:.2f}ms)"
94	        print(f"{prefix}{label}")
95	        for child in node.children.values():
96	            self.print_graph(child, indent + 1)
97	
98	    def get_edges(self) -> list[tuple[str, str, int]]:
99	        """Return edges as (parent, child, call_count)."""
100	        edges: list[tuple[str, str, int]] = []
101	        self._collect_edges(self.root, edges)
102	        return edges
103	
104	    def _collect_edges(self, node: CallNode, edges: list) -> None:
105	        for child in node.children.values():
106	            edges.append((node.name, child.name, child.call_count))
107	            self._collect_edges(child, edges)
108	
109	    def get_node(self, qualified_name: str) -> CallNode | None:
110	        """Find a node by qualified name."""
111	        return self._find_node(self.root, qualified_name)
112	
113	    def _find_node(self, node: CallNode, name: str) -> CallNode | None:
114	        if node.name == name:
115	            return node
116	        for child in node.children.values():
117	            found = self._find_node(child, name)
118	            if found:
119	                return found
120	        return None
121	
122	
123	# ---------------------------------------------------------------------------
124	# Usage examples
125	# ---------------------------------------------------------------------------
126	
127	def _example_workload():
128	    """Simulate a call hierarchy for demonstration."""
129	
130	    def parse(data):
131	        return [x.strip() for x in data.split(",")]
132	
133	    def validate(items):
134	        return all(len(item) > 0 for item in items)
135	
136	    def process(data):
137	        items = parse(data)
138	        if validate(items):
139	            return [item.upper() for item in items]
140	        return []
141	
142	    def pipeline(raw_inputs):
143	        results = []
144	        for raw in raw_inputs:
145	            results.extend(process(raw))
146	        return results
147	
148	    return pipeline(["hello, world", "foo, bar, baz", "single"])
149	
150	
151	def example_basic():
152	    """Basic usage: trace a call and print the graph."""
153	    tracer = CallTracer()
154	    with tracer:
155	        _example_workload()
156	
157	    print("=== Call Graph ===")
158	    tracer.print_graph()
159	    print()
160	
161	
162	def example_edges():
163	    """Extract edges for external analysis."""
164	    tracer = CallTracer()
165	    with tracer:
166	        _example_workload()
167	
168	    print("=== Edges ===")
169	    for parent, child, count in tracer.get_edges():
170	        print(f"  {parent} -> {child}  ({count} calls)")
171	    print()
172	
173	
174	def example_timing():
175	    """Inspect per-function timing."""
176	    tracer = CallTracer()
177	    with tracer:
178	        _example_workload()
179	
180	    print("=== Timing ===")
181	    for _, child, _ in tracer.get_edges():
182	        node = tracer.get_node(child)
183	        if node and node.total_time > 0:
184	            print(f"  {node.name}: {node.total_time*1000:.3f}ms")
185	    print()
186	
187	
188	# ---------------------------------------------------------------------------
189	# Tests
190	# ---------------------------------------------------------------------------
191	
192	def _test_basic_tracing():
193	    """Traced functions appear in the graph."""
194	    tracer = CallTracer()
195	    with tracer:
196	        _example_workload()
197	
198	    edges = tracer.get_edges()
199	    assert len(edges) > 0, "Expected at least one edge"
200	
201	    names = {child for _, child, _ in edges}
202	    assert any("parse" in n for n in names), f"Expected 'parse' in {names}"
203	    assert any("validate" in n for n in names), f"Expected 'validate' in {names}"
204	    assert any("process" in n for n in names), f"Expected 'process' in {names}"
205	
206	
207	def _test_call_counts():
208	    """Call counts reflect actual invocations."""
209	    def a():
210	        pass
211	
212	    def b():
213	        a()
214	        a()
215	
216	    def c():
217	        b()
218	
219	    tracer = CallTracer()
220	    with tracer:
221	        c()
222	        c()
223	
224	    edges = {child: count for _, child, count in tracer.get_edges()}
225	
226	    c_name = [n for n in edges if n.endswith(".c")]
227	    b_name = [n for n in edges if n.endswith(".b")]
228	    a_name = [n for n in edges if n.endswith(".a")]
229	
230	    assert c_name, f"Expected c in edges: {edges}"
231	    assert b_name, f"Expected b in edges: {edges}"
232	    assert a_name, f"Expected a in edges: {edges}"
233	
234	    # c called 2 times, b called 2 times, a called 4 times
235	    assert edges[c_name[0]] == 2, f"c: expected 2, got {edges[c_name[0]]}"
236	    assert edges[b_name[0]] == 2, f"b: expected 2, got {edges[b_name[0]]}"
237	    assert edges[a_name[0]] == 4, f"a: expected 4, got {edges[a_name[0]]}"
238	
239	
240	def _test_graph_structure():
241	    """The graph captures parent-child relationships."""
242	    def parent():
243	        child_a()
244	        child_b()
245	
246	    def child_a():
247	        grandchild()
248	
249	    def child_b():
250	        pass
251	
252	    def grandchild():
253	        pass
254	
255	    tracer = CallTracer()
256	    with tracer:
257	        parent()
258	
259	    edges = {(p, c) for p, c, _ in tracer.get_edges()}
260	    names = {c for _, c in edges}
261	
262	    parent_name = [n for n in names if n.endswith(".parent")][0]
263	    child_a_name = [n for n in names if n.endswith(".child_a")][0]
264	    child_b_name = [n for n in names if n.endswith(".child_b")][0]
265	    grandchild_name = [n for n in names if n.endswith(".grandchild")][0]
266	
267	    assert (parent_name, child_a_name) in edges
268	    assert (parent_name, child_b_name) in edges
269	    assert (child_a_name, grandchild_name) in edges
270	
271	
272	def _test_ignore_modules():
273	    """Modules in ignore_modules are excluded from the trace."""
274	    def my_func():
275	        pass
276	
277	    tracer = CallTracer(ignore_modules=("__main__",))
278	    with tracer:
279	        my_func()
280	
281	    assert len(tracer.root.children) == 0, (
282	        f"Expected no children when ignoring __main__, got {list(tracer.root.children)}"
283	    )
284	
285	
286	def _test_empty_trace():
287	    """An empty body produces a graph with only root."""
288	    tracer = CallTracer()
289	    with tracer:
290	        pass
291	
292	    assert len(tracer.root.children) == 0
293	    assert tracer.get_edges() == []
294	
295	
296	def _test_timing_recorded():
297	    """Nodes accumulate non-zero time."""
298	    import time as _time
299	
300	    def slow():
301	        _time.sleep(0.01)
302	
303	    tracer = CallTracer()
304	    with tracer:
305	        slow()
306	
307	    edges = tracer.get_edges()
308	    slow_name = [c for _, c, _ in edges if "slow" in c][0]
309	    node = tracer.get_node(slow_name)
310

### Turn 6 (assistant)
The existing `call_tracer.py` uses a context manager with `sys.setprofile`. The user asked for a **decorator**-based approach. Let me rewrite it with a proper decorator that traces decorated functions and builds a call graph.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/call_tracer.py",
  "content": "\"\"\"Decorator that traces function calls and builds a call graph.\"\"\"\n\nimport functools\nimport time\nfrom collections import defaultdict\nfrom dataclasses import dataclass, field\n\n\n@dataclass\nclass CallNode:\n    \"\"\"A node in the call graph representing a traced function.\"\"\"\n\n    name: str\n    call_count: int = 0\n    total_time: float = 0.0\n    children: dict[str, \"CallNode\"] = field(default_factory=di
```

### Turn 7 (tool)
The file /data/agent/choucisan/call_tracer.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 8 (assistant)
Let me run the tests and examples to verify everything works.
**Tool**: `Bash`
```json
{
  "command": "python call_tracer.py test",
  "description": "Run call_tracer tests"
}
```

### Turn 9 (tool)
  PASS  _test_basic_tracing
  PASS  _test_call_counts
  PASS  _test_graph_structure
  PASS  _test_timing_recorded
  PASS  _test_custom_graph
  PASS  _test_preserves_return_value
  PASS  _test_preserves_metadata
  PASS  _test_empty_trace

8 passed, 0 failed out of 8

### Turn 10 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python call_tracer.py",
  "description": "Run call_tracer examples"
}
```

### Turn 11 (tool)
=== Call Graph ===
<root>
  example_basic.<locals>.pipeline  (calls=1, time=0.03ms)
    example_basic.<locals>.process  (calls=3, time=0.02ms)
      example_basic.<locals>.parse  (calls=3, time=0.00ms)
      example_basic.<locals>.validate  (calls=3, time=0.00ms)

=== Edges ===
  <root> -> example_edges.<locals>.c  (2 calls)
  example_edges.<locals>.c -> example_edges.<locals>.b  (2 calls)
  example_edges.<locals>.b -> example_edges.<locals>.a  (4 calls)

=== Custom Graph ===
<root>
  example_custom_graph.<locals>.foo  (calls=2, time=0.00ms)
    example_custom_graph.<locals>.bar  (calls=2, time=0.00ms)

### Turn 12 (assistant)
All 8 tests pass and all 3 examples produce correct output. Here's what the rewritten `call_tracer.py` provides:

**Core API:**
- `@trace` — decorator that records each call into a `CallGraph`, tracking call count and wall-clock time
- `@trace(graph=my_graph)` — trace into a dedicated graph instead of the module-level default
- `CallGraph` — stores the tree structure, exposes `get_edges()`, `get_node()`, `print_graph()`
- `get_graph()` / `reset_graph()` — access or clear the default graph

**Key design choices:**
- Uses `functools.wraps` so decorated functions keep their `__name__` and `__doc__`
- Tracks parent-child relationships via a call stack, so nested calls produce a proper tree
- Return values and exceptions pass through unchanged (timing is in a `finally` block)
- Each `CallNode` records `call_count` and `total_time` per unique call-site path

**8 tests cover:** basic tracing, call counts, graph structure, timing, custom graph isolation, return value preservation, metadata preservation, and empty trace.

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