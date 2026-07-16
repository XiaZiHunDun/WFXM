# Code Kahn's algorithm for topological sort in Python. Compare it with a brute-force approach.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Code Kahn's algorithm for topological sort in Python. Compare it with a brute-force approach.

## Conversation
### Turn 1 (user)
Code Kahn's algorithm for topological sort in Python. Compare it with a brute-force approach.

### Turn 2 (assistant)
Here's a Python implementation of both approaches:
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/topological_sort.py",
  "content": "from collections import deque\n\n\ndef topological_sort_kahn(num_vertices, edges):\n    \"\"\"Kahn's algorithm (BFS-based) for topological sort.\n\n    Args:\n        num_vertices: number of vertices (0 to num_vertices-1)\n        edges: list of (u, v) directed edges meaning u -> v\n\n    Returns:\n        List of vertices in topological order, or [] if a cycle exists.\n\n    Time:  O(V + E)\n    Space: O(V + E)\n    \"\
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/",
  "description": "Check directory contents"
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
analyze_excel.py
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
binary_tree.py
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
calculate_factory.py
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
circular_buffer_test.js
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
dbtool.py
debounce
debounce.go
debounce.js
debounce.py
debounce.rs
debounce_test.go
deep_merge.go
deep_merge.js
deep_merge.py
deep_merge_test.go
default_dict.py
defaultdict.py
deploy
deploy.conf.example
deploy.sh
determinant.py
dfs.py
digital_root.py
dijkstra_comparison.py
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
extended_euclidean.py
factorial.py
fastapi-app.service
fdagent
fdagent.tar.gz
fenwick_tree.py
fibonacci_gen.py
fibonacci.py
file-storage-api
file_uploaded_db_webhook.py
file_uploaded_email_webhook.py
file_uploaded_webhook.py
find_duplicates.go
find_duplicates.js
find_duplicates.py
find_duplicates_test.go
find_min_max.py
find_period.py
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
image_tool.py
infix_to_postfix.js
infix_to_postfix.py
inventory-ws-api
jacobi.py
jira_client
jira-proxy
jobmanager.py
json_api_sqlite_etl.py
json_dedup.py
jsonl_to_html.py
jsonl_validator.py
json_sampler.py
json_schema_validator
json_schema_validator.py
json_to_html_table.py
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
logrotate.sh
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
merge_xml.py
message_queue.py
message_sent_webhook.py
metrics_collector.py
miller_rabin.py
mimo-claude-code-traces
min_bounding_circle.py
min_heap.py
minimum_bounding_circle.py
min_max.py
min_max_stack.py
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
nginx-fastapi.conf
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
output_table.html
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
pivot_jsonl.py
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
retry.go
retry.js
retry_test.go
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
sample_jsonl.py
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
segment_tree_set.py
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
slack_ws_client.py
sliding_window_maximum.py
sliding_window_max.py
sort_by_second.py
sparse_table.py
spring-boot-app.service
spring-boot.Dockerfile
sql_to_pg_pipeline.py
src
ssl-renew.sh
stirling.py
strategies.py
streaming_csv_parser.py
streaming_jsonl_parser.py
streaming_parquet_parser.py
streaming_xml_parser.py
stripe_wrapper
structured-logging
suffix_array.py
suffix_tree_bruteforce.py
suffix_tree_compare.py
suffix_tree.py
sum_proper_divisors.py
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
test_binary_tree.py
test_cloud_resource_cli.py
test_compress_string.py
test_connection_pool.py
test.db
test_email_utils.py
test_env1.env
test_env2.env
test_excel_data_validator.py
test_file_uploaded_db_webhook.py
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
test_mo_algorithm.py
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
test_type_validator.py
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
trie_

### Turn 6 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/topological_sort.py"
}
```

### Turn 7 (tool)
1	"""Topological sort using Depth-First Search (DFS).
2	
3	Topological sorting produces a linear ordering of vertices in a Directed
4	Acyclic Graph (DAG) such that for every directed edge (u, v), vertex u
5	appears before vertex v in the ordering.  A graph with at least one cycle
6	has no valid topological ordering.
7	
8	The DFS approach works by exploiting the *post-order* of a DFS traversal:
9	the last node to *finish* (i.e. have all its descendants explored) is a
10	source node — it has no incoming edges from unvisited nodes.  By collecting
11	nodes in post-order and then reversing the list, we obtain a valid
12	topological ordering.
13	
14	Time complexity : O(V + E) — every vertex and edge is visited exactly once.
15	Space complexity: O(V)     — for the color array and the recursion stack.
16	"""
17	
18	from collections import defaultdict, deque
19	
20	
21	# ── DFS-based topological sort ────────────────────────────────────────────────
22	
23	def topo_sort_dfs(num_vertices, edges):
24	    """Return a topological ordering of the given DAG using DFS.
25	
26	    Args:
27	        num_vertices: Total number of vertices (0 .. num_vertices-1).
28	        edges: List of (u, v) tuples representing directed edges u → v.
29	
30	    Returns:
31	        A list of vertices in topological order.
32	
33	    Raises:
34	        ValueError: If the graph contains a cycle.
35	    """
36	    # Step 1 — Build the adjacency list.
37	    # defaultdict(list) creates an empty list for any key we haven't seen,
38	    # so we can append neighbours without checking existence first.
39	    graph = defaultdict(list)
40	    for u, v in edges:
41	        graph[u].append(v)
42	
43	    # Step 2 — Initialize a three-color marking system for each vertex.
44	    #   WHITE (0) — node has not been discovered yet (untouched).
45	    #   GRAY  (1) — node is on the *current* DFS path (in-progress).
46	    #   BLACK (2) — node and all its descendants have been fully explored.
47	    #
48	    # Why three colors instead of a simple boolean visited set?
49	    # A boolean "visited" flag can only tell us "seen" vs "not seen".
50	    # With three colors we can also detect *back-edges*: if we encounter
51	    # a GRAY neighbour while exploring a node, that neighbour is an
52	    # ancestor on the current DFS path, which means the graph has a cycle.
53	    WHITE, GRAY, BLACK = 0, 1, 2
54	    color = [WHITE] * num_vertices
55	
56	    # 'order' accumulates vertices in *post-order* — each vertex is appended
57	    # only after all its descendants have already been appended.
58	    order = []
59	
60	    def dfs(u):
61	        """Explore vertex u and all its descendants via DFS."""
62	        # Step 3 — Mark u as GRAY to indicate we are currently exploring it.
63	        # Any GRAY node reachable from u means a cycle exists.
64	        color[u] = GRAY
65	
66	        # Step 4 — Visit every neighbour of u.
67	        for v in graph[u]:
68	            # Step 5 — Cycle detection: if v is GRAY, it is an ancestor on
69	            # the current DFS path, meaning u → … → v → u forms a cycle.
70	            if color[v] == GRAY:
71	                raise ValueError("Graph contains a cycle")
72	
73	            # Step 6 — If v is WHITE (unvisited), recurse into it.
74	            # This is the core of DFS: we go as deep as possible before
75	            # backtracking, which naturally produces a post-order traversal.
76	            if color[v] == WHITE:
77	                dfs(v)
78	
79	        # Step 7 — All descendants of u have been fully explored (turned BLACK).
80	        # We now mark u as BLACK to record that it is completely done.
81	        color[u] = BLACK
82	
83	        # Step 8 — Append u to the result list.  Because we only append *after*
84	        # all descendants are done, u is guaranteed to come after every node
85	        # it can reach.  Reversing this list at the end flips that into the
86	        # required topological order (u *before* everything it reaches).
87	        order.append(u)
88	
89	    # Step 9 — Iterate over every vertex and start a DFS from each unvisited
90	    # one.  This is necessary because the graph may be disconnected: a single
91	    # DFS call only reaches vertices in one connected component.
92	    for u in range(num_vertices):
93	        if color[u] == WHITE:
94	            dfs(u)
95	
96	    # Step 10 — Reverse the post-order list.
97	    # In post-order, a node appears *after* all its descendants.
98	    # Topological sort requires a node to appear *before* all its descendants.
99	    # Simply reversing the list transforms one into the other.
100	    order.reverse()
101	    return order
102	
103	
104	# ── Brute-force: Kahn's algorithm (BFS-based in-degree removal) ───────────────
105	
106	def topo_sort_bruteforce(num_vertices, edges):
107	    """Repeatedly find nodes with in-degree 0, remove them, and repeat.
108	
109	    Time:  O(V² + V·E) — recomputes in-degrees from scratch each round
110	    Space: O(V + E)
111	    """
112	    graph = defaultdict(list)
113	    for u, v in edges:
114	        graph[u].append(v)
115	
116	    remaining = set(range(num_vertices))
117	    order = []
118	
119	    while remaining:
120	        # Recompute in-degrees for all remaining nodes (brute-force part)
121	        in_degree = {n: 0 for n in remaining}
122	        for u in remaining:
123	            for v in graph[u]:
124	                if v in remaining:
125	                    in_degree[v] += 1
126	
127	        # Collect all nodes with in-degree 0
128	        zeros = [n for n in remaining if in_degree[n] == 0]
129	        if not zeros:
130	            raise ValueError("Graph contains a cycle")
131	
132	        # Remove them
133	        for n in zeros:
134	            remaining.remove(n)
135	            order.append(n)
136	
137	    return order
138	
139	
140	# ── Optimized Kahn's (for reference) ─────────────────────────────────────────
141	
142	def topo_sort_kahn(num_vertices, edges):
143	    """Standard Kahn's algorithm — O(V + E).
144	
145	    Computes in-degrees once, then updates incrementally.
146	    Included as a baseline for the brute-force to compare against.
147	    """
148	    graph = defaultdict(list)
149	    in_degree = [0] * num_vertices
150	    for u, v in edges:
151	        graph[u].append(v)
152	        in_degree[v] += 1
153	
154	    queue = deque(i for i in range(num_vertices) if in_degree[i] == 0)
155	    order = []
156	
157	    while queue:
158	        u = queue.popleft()
159	        order.append(u)
160	        for v in graph[u]:
161	            in_degree[v] -= 1
162	            if in_degree[v] == 0:
163	                queue.append(v)
164	
165	    if len(order) != num_vertices:
166	        raise ValueError("Graph contains a cycle")
167	    return order
168	
169	
170	# ── Validation helper ─────────────────────────────────────────────────────────
171	
172	def is_valid_topo(order, edges):
173	    """Check that every edge u→v has u appearing before v."""
174	    pos = {n: i for i, n in enumerate(order)}
175	    return all(pos[u] < pos[v] for u, v in edges)
176	
177	
178	# ── Demo ──────────────────────────────────────────────────────────────────────
179	
180	if __name__ == "__main__":
181	    #   0 → 1 → 3
182	    #   0 → 2 → 3
183	    #   4 → 5
184	    edges = [(0, 1), (1, 3), (0, 2), (2, 3), (4, 5)]
185	
186	    r_dfs = topo_sort_dfs(6, edges)
187	    r_bf = topo_sort_bruteforce(6, edges)
188	    r_kahn = topo_sort_kahn(6, edges)
189	
190	    print("DFS result:       ", r_dfs)
191	    print("Brute-force result:", r_bf)
192	    print("Kahn's result:    ", r_kahn)
193	    print(f"All valid: {is_valid_topo(r_dfs, edges)}, "
194	          f"{is_valid_topo(r_bf, edges)}, "
195	          f"{is_valid_topo(r_kahn, edges)}")
196	
197	    # Cycle detection
198	    try:
199	        topo_sort_dfs(3, [(0, 1), (1, 2), (2, 0)])
200	    except ValueError as e:
201	        print(f"\nCycle detected (DFS): {e}")
202	
203	    try:
204	        topo_sort_bruteforce(3, [(0, 1), (1, 2), (2, 0)])
205	    except ValueError as e:
206	        print(f"Cycle detected (brute-force): {e}")
207	
208	    # ── Benchmark ─────────────────────────────────────────────────────────
209	    import timeit, random
210	
211	    n = 2000
212	    big_edges = []
213	    for i in range(n - 1):
214	        for _ in range(random.randint(0, 5)):
215	            j = random.randint(i + 1, n - 1)
216	            big_edges.append((i, j))
217	
218	    t_dfs = timeit.timeit(lambda: topo_sort_dfs(n, big_edges), number=3)
219	    t_bf = timeit.timeit(lambda: topo_sort_bruteforce(n, big_edges), number=3)
220	    t_kahn = timeit.timeit(lambda: topo_sort_kahn(n, big_edges), number=3)
221	
222	    print(f"\nBenchmark (V={n}, {len(big_edges)} edges, 3 runs):")
223	    print(f"  DFS:          {t_dfs:.4f}s")
224	    print(f"  Brute-force:  {t_bf:.4f}s")
225	    print(f"  Kahn's:       {t_kahn:.4f}s")
226	    print(f"  DFS/Brute:    {t_bf / t_dfs:.1f}x speedup")
227	

### Turn 8 (assistant)
The file already has all three implementations. Let me run it to show the results and comparison:
**Tool**: `Bash`
```json
{
  "command": "python topological_sort.py",
  "description": "Run topological sort demo"
}
```

### Turn 9 (tool)
DFS result:        [4, 5, 0, 2, 1, 3]
Brute-force result: [0, 4, 1, 2, 5, 3]
Kahn's result:     [0, 4, 1, 2, 5, 3]
All valid: True, True, True

Cycle detected (DFS): Graph contains a cycle
Cycle detected (brute-force): Graph contains a cycle

Benchmark (V=2000, 4961 edges, 3 runs):
  DFS:          0.0046s
  Brute-force:  0.0185s
  Kahn's:       0.0051s
  DFS/Brute:    4.1x speedup

### Turn 10 (assistant)
The file at `topological_sort.py` already contains both implementations. Here's the comparison:

### Kahn's Algorithm (BFS-based) — `topo_sort_kahn`
- Computes in-degree for each vertex **once**
- Starts with all zero-in-degree vertices in a queue
- Pops a vertex, appends it to the result, decrements in-degree of its neighbors
- If a neighbor hits in-degree 0, enqueue it
- **O(V + E)** time, **O(V + E)** space

### Brute-force — `topo_sort_bruteforce`
- Each round: recompute in-degrees for **all remaining** vertices from scratch
- Find all zero-in-degree nodes, remove them
- Repeat until done or no zero-in-degree node found (cycle)
- **O(V² + V·E)** time — the re-scanning each round is the bottleneck

### Key difference

Kahn's maintains an `in_degree` array and updates it incrementally (`in_degree[v] -= 1`), while the brute-force rebuilds it from scratch every iteration. The benchmark on a 2000-vertex graph shows **Kahn's is ~3-4x faster**, and the gap grows with graph size since brute-force is quadratic.

Both produce valid (but possibly different) topological orderings, and both detect cycles — Kahn's by checking if fewer than V vertices were output, brute-force by finding no zero-in-degree vertices remain.

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