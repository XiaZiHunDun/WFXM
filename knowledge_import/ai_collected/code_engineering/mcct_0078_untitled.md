# Implement suffix array construction in Python. Analyze its time and space complexity.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Implement suffix array construction in Python. Analyze its time and space complexity.

## Conversation
### Turn 1 (user)
Implement suffix array construction in Python. Analyze its time and space complexity.

### Turn 2 (assistant)
I'll implement a suffix array with the efficient prefix doubling algorithm (O(n log n)) and a naive approach for comparison.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/suffix_array.py",
  "content": "\"\"\"\nSuffix Array Construction\n=========================\nA suffix array is a sorted array of all suffixes of a string,\nrepresented by their starting indices. It enables efficient\nsubstring search, longest common substring, and other string operations.\n\"\"\"\n\nfrom typing import List, Tuple\n\n\ndef suffix_array_naive(s: str) -> List[int]:\n    \"\"\"\n    Naive suffix array construction.\n    Generate all suffixes,
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
bloom_filter.js
bloom_filter.py
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
csv_to_json_pipeline.py
csv_to_markdown.py
csv_to_sql_pipeline.py
cuda_12.8.0_570.86.10_linux.run
data
data_processor.py
debounce
debounce.js
debounce.py
debounce.rs
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
infix_to_postfix.py
jacobi.py
jira-proxy
jsonl_to_html.py
jsonl_validator.py
json_schema_validator.py
json_to_sql_pipeline.py
json_to_sql.py
jwt-auth-module
kadane.py
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
metrics_collector.py
mimo-claude-code-traces
min_heap.py
min_max.py
min_stack.py
mo_algorithm.cpp
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
parse_expression.js
parse_expression.py
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
xml_analyzer.py
xml_pivot.py
xml_sampler.py
xml_to_sql.py
yaml_fuzzy_dedup.py
yaml_merger.py
yaml_schema_validator.py
yaml_to_html.py
yaml_to_json.py

### Turn 6 (assistant)
There's already a `suffix_array.py` in the repo. Let me check what's there.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/suffix_array.py"
}
```

### Turn 7 (tool)
1	"""
2	Suffix Array Construction using SA-IS (Suffix Array by Induced Sorting).
3	
4	O(n) time and space complexity. Handles edge cases including:
5	- Empty input
6	- Single character strings
7	- All-same-character strings
8	- Binary strings
9	- Strings with sentinel character (null byte)
10	"""
11	
12	
13	def build_suffix_array(s: str) -> list[int]:
14	    """Build suffix array for string s. Returns list of starting indices sorted lexicographically."""
15	    if not s:
16	        return []
17	
18	    n = len(s)
19	    if n == 1:
20	        return [0]
21	
22	    # Convert to integer array with sentinel (0 = unique minimum appended)
23	    alphabet = sorted(set(s))
24	    char_map = {c: i + 1 for i, c in enumerate(alphabet)}
25	    t = [char_map[c] for c in s]
26	    t.append(0)  # sentinel is always 0, unique minimum
27	
28	    result = _sais(t, len(alphabet) + 1)
29	    return result[1:]  # remove sentinel position (always index 0)
30	
31	
32	def _sais(s: list[int], alphabet_size: int) -> list[int]:
33	    """SA-IS algorithm. s must end with a unique minimum sentinel (0)."""
34	    n = len(s)
35	    if n <= 1:
36	        return list(range(n))
37	
38	    # Step 1: Classify each position as S-type or L-type
39	    # S-type: s[i] < s[i+1], or s[i] == s[i+1] and i+1 is S-type
40	    is_s = [False] * n
41	    is_s[n - 1] = True  # sentinel is S-type
42	    for i in range(n - 2, -1, -1):
43	        if s[i] < s[i + 1]:
44	            is_s[i] = True
45	        elif s[i] == s[i + 1]:
46	            is_s[i] = is_s[i + 1]
47	
48	    # Step 2: Find LMS (Left-Most S-type) positions
49	    # LMS: position i where s[i] is S-type and s[i-1] is L-type
50	    is_lms = [False] * n
51	    for i in range(1, n):
52	        if is_s[i] and not is_s[i - 1]:
53	            is_lms[i] = True
54	
55	    lms_positions = [i for i in range(n) if is_lms[i]]
56	
57	    # Step 3: Sort LMS suffixes using induce sort
58	    sa = _induce_sort_lms(s, is_s, is_lms, lms_positions, alphabet_size)
59	
60	    # Step 4: Assign names to LMS substrings (lexicographic ranks)
61	    lms_sorted = [p for p in sa if p != -1 and is_lms[p]]
62	
63	    name = 0
64	    names = [0] * n
65	    prev_start = -1
66	    for pos in lms_sorted:
67	        if prev_start != -1 and not _lms_substring_equal(s, is_lms, prev_start, pos):
68	            name += 1
69	        names[pos] = name
70	        prev_start = pos
71	
72	    # Step 5: Build reduced string from LMS names
73	    lms_name_list = []
74	    lms_index_map = []
75	    for i in range(n):
76	        if is_lms[i]:
77	            lms_name_list.append(names[i])
78	            lms_index_map.append(i)
79	
80	    # Step 6: Recursively solve if names aren't all unique
81	    if name + 1 < len(lms_positions):
82	        reduced_sa = _sais(lms_name_list, name + 1)
83	        lms_sorted = [lms_index_map[p] for p in reduced_sa]
84	    # else lms_sorted is already correct from the induce sort
85	
86	    # Step 7: Final induce sort with correct LMS order -> full suffix array
87	    return _induce_sort_full(s, is_s, is_lms, lms_sorted, alphabet_size)
88	
89	
90	def _lms_substring_equal(s: list[int], is_lms: list[bool], i: int, j: int) -> bool:
91	    """Check if two LMS substrings starting at i and j are identical."""
92	    n = len(s)
93	    k = 0
94	    while True:
95	        i_end = i + k >= n
96	        j_end = j + k >= n
97	        if i_end or j_end:
98	            return i_end == j_end
99	        if s[i + k] != s[j + k]:
100	            return False
101	        # End of LMS substring: next position is LMS (and k > 0 means not start)
102	        if k > 0 and is_lms[i + k]:
103	            return True
104	        k += 1
105	
106	
107	def _get_bucket_boundaries(s: list[int], alphabet_size: int):
108	    """Compute bucket start/end indices for each character value."""
109	    bucket_sizes = [0] * alphabet_size
110	    for c in s:
111	        bucket_sizes[c] += 1
112	    starts = [0] * alphabet_size
113	    ends = [0] * alphabet_size
114	    acc = 0
115	    for i in range(alphabet_size):
116	        starts[i] = acc
117	        acc += bucket_sizes[i]
118	        ends[i] = acc
119	    return starts, ends
120	
121	
122	def _induce_lms_into_sa(s: list[int], sa: list[int], is_s: list[bool],
123	                         lms_positions: list[int], ends: list[int]) -> None:
124	    """Place LMS suffixes at the end of their respective buckets."""
125	    bucket_ends = ends[:]
126	    for pos in reversed(lms_positions):
127	        c = s[pos]
128	        bucket_ends[c] -= 1
129	        sa[bucket_ends[c]] = pos
130	
131	
132	def _induce_l_type(s: list[int], sa: list[int], is_s: list[bool],
133	                    starts: list[int]) -> None:
134	    """Induce L-type suffixes by scanning left to right."""
135	    buckets = starts[:]
136	    for i in range(len(sa)):
137	        j = sa[i] - 1
138	        if j < 0:
139	            continue
140	        if not is_s[j]:  # L-type
141	            c = s[j]
142	            sa[buckets[c]] = j
143	            buckets[c] += 1
144	
145	
146	def _induce_s_type(s: list[int], sa: list[int], is_s: list[bool],
147	                    ends: list[int]) -> None:
148	    """Induce S-type suffixes by scanning right to left."""
149	    buckets = ends[:]
150	    for i in range(len(sa) - 1, -1, -1):
151	        j = sa[i] - 1
152	        if j < 0:
153	            continue
154	        if is_s[j]:  # S-type
155	            c = s[j]
156	            buckets[c] -= 1
157	            sa[buckets[c]] = j
158	
159	
160	def _induce_sort_lms(s: list[int], is_s: list[bool], is_lms: list[bool],
161	                      lms_positions: list[int], alphabet_size: int) -> list[int]:
162	    """Induce sort to find relative order of LMS suffixes only."""
163	    n = len(s)
164	    sa = [-1] * n
165	    starts, ends = _get_bucket_boundaries(s, alphabet_size)
166	
167	    # Place LMS at end of buckets
168	    _induce_lms_into_sa(s, sa, is_s, lms_positions, ends)
169	
170	    # Induce L then S
171	    _induce_l_type(s, sa, is_s, starts)
172	    _induce_s_type(s, sa, is_s, ends)
173	
174	    return sa
175	
176	
177	def _induce_sort_full(s: list[int], is_s: list[bool], is_lms: list[bool],
178	                       lms_sorted: list[int], alphabet_size: int) -> list[int]:
179	    """Full induce sort: given correctly sorted LMS suffixes, produce the full SA."""
180	    n = len(s)
181	    sa = [-1] * n
182	    starts, ends = _get_bucket_boundaries(s, alphabet_size)
183	
184	    # Place LMS suffixes at end of buckets in the correct order
185	    _induce_lms_into_sa(s, sa, is_s, lms_sorted, ends)
186	
187	    # Induce L then S
188	    _induce_l_type(s, sa, is_s, starts)
189	    _induce_s_type(s, sa, is_s, ends)
190	
191	    return sa
192	
193	
194	def build_lcp_array(s: str, sa: list[int]) -> list[int]:
195	    """Build LCP (Longest Common Prefix) array using Kasai's algorithm. O(n)."""
196	    n = len(s)
197	    if n <= 1:
198	        return []
199	
200	    rank = [0] * n
201	    for i, pos in enumerate(sa):
202	        rank[pos] = i
203	
204	    lcp = [0] * (n - 1)
205	    k = 0
206	    for i in range(n):
207	        if rank[i] == 0:
208	            k = 0
209	            continue
210	        j = sa[rank[i] - 1]
211	        while i + k < n and j + k < n and s[i + k] == s[j + k]:
212	            k += 1
213	        lcp[rank[i] - 1] = k
214	        if k > 0:
215	            k -= 1
216	    return lcp
217	
218	
219	def substring_search(s: str, pattern: str, sa: list[int]) -> list[int]:
220	    """Find all occurrences of pattern in s using suffix array. O(m log n + occ)."""
221	    n = len(s)
222	    m = len(pattern)
223	    if m == 0 or m > n:
224	        return []
225	
226	    # Binary search for lower bound
227	    lo, hi = 0, n
228	    while lo < hi:
229	        mid = (lo + hi) // 2
230	        if s[sa[mid]:sa[mid] + m] < pattern:
231	            lo = mid + 1
232	        else:
233	            hi = mid
234	    start = lo
235	
236	    # Binary search for upper bound
237	    lo, hi = 0, n
238	    while lo < hi:
239	        mid = (lo + hi) // 2
240	        if s[sa[mid]:sa[mid] + m] <= pattern:
241	            lo = mid + 1
242	        else:
243	            hi = mid
244	    end = lo
245	
246	    return sorted(sa[start:end])
247	
248	
249	if __name__ == "__main__":
250	    test_cases = [
251	        ("banana", [5, 3, 1, 0, 4, 2]),
252	        ("", []),
253	        ("a", [0]),
254	        ("aaaa", [3, 2, 1, 0]),
255	        ("abracadabra", [10, 7, 0, 3, 5, 8, 1, 4, 6, 9, 2]),
256	        ("abcab", [3, 0, 4, 1, 2]),
257	        ("abcabc", [3, 0, 4, 1, 5, 2]),
258	        ("mississippi", [10, 7, 4, 1, 0, 9, 8, 6, 3, 5, 2]),
259	    ]
260	
261	    all_pass = True
262	    for s, expected in test_cases:
263	        result = build_suffix_array(s)
264	        status = "PASS" if result == expected else "FAIL"
265	        if status == "FAIL":
266	            all_pass = False
267	        print(f"{status}: build_suffix_array({s!r}) = {result} (expected {expected})")
268	
269	    # Test LCP array
270	    s = "banana"
271	    sa = build_suffix_array(s)
272	    lcp = build_lcp_array(s, sa)
273	    expected_lcp = [1, 3, 0, 0, 2]
274	    status = "PASS" if lcp == expected_lcp else "FAIL"
275	    if status == "FAIL":
276	        all_pass = False
277	    print(f"\n{status}: LCP for 'banana': {lcp} (expected {expected_lcp})")
278	
279	    # Test substring search
280	    s = "abracadabra"
281	    sa = build_suffix_array(s)
282	    search_tests = [
283	        ("abra", [0, 7]),
284	        ("a", [0, 3, 5, 7, 10]),
285	        ("bra", [1, 8]),
286	        ("xyz", []),
287	    ]
288	    for pat, expected_pos in search_tests:
289	        positions = substring_search(s, pat, sa)
290	        status = "PASS" if positions == expected_pos else "FAIL"
291	        if status == "FAIL":
292	            all_pass = False
293	        print(f"{status}: Search '{pat}' in '{s}': {positions} (expected {expected_pos})")
294	
295	    print(f"\n{'All tests passed!' if all_pass else 'Some tests FAI

### Turn 8 (assistant)
The repo already has a suffix array implementation using SA-IS (linear time). Let me verify it works and then provide the complexity analysis.
**Tool**: `Bash`
```json
{
  "command": "python3 suffix_array.py",
  "description": "Run suffix array tests"
}
```

### Turn 9 (tool)
PASS: build_suffix_array('banana') = [5, 3, 1, 0, 4, 2] (expected [5, 3, 1, 0, 4, 2])
PASS: build_suffix_array('') = [] (expected [])
PASS: build_suffix_array('a') = [0] (expected [0])
PASS: build_suffix_array('aaaa') = [3, 2, 1, 0] (expected [3, 2, 1, 0])
PASS: build_suffix_array('abracadabra') = [10, 7, 0, 3, 5, 8, 1, 4, 6, 9, 2] (expected [10, 7, 0, 3, 5, 8, 1, 4, 6, 9, 2])
PASS: build_suffix_array('abcab') = [3, 0, 4, 1, 2] (expected [3, 0, 4, 1, 2])
PASS: build_suffix_array('abcabc') = [3, 0, 4, 1, 5, 2] (expected [3, 0, 4, 1, 5, 2])
PASS: build_suffix_array('mississippi') = [10, 7, 4, 1, 0, 9, 8, 6, 3, 5, 2] (expected [10, 7, 4, 1, 0, 9, 8, 6, 3, 5, 2])

PASS: LCP for 'banana': [1, 3, 0, 0, 2] (expected [1, 3, 0, 0, 2])
PASS: Search 'abra' in 'abracadabra': [0, 7] (expected [0, 7])
PASS: Search 'a' in 'abracadabra': [0, 3, 5, 7, 10] (expected [0, 3, 5, 7, 10])
PASS: Search 'bra' in 'abracadabra': [1, 8] (expected [1, 8])
PASS: Search 'xyz' in 'abracadabra': [] (expected [])

All tests passed!

### Turn 10 (assistant)
All tests pass. Here's the complexity analysis of the existing implementation:

## Complexity Analysis

### `build_suffix_array` — SA-IS Algorithm

The implementation uses **SA-IS (Suffix Array by Induced Sorting)**, one of the most efficient known algorithms.

**Time: O(n)**

| Phase | Work |
|-------|------|
| S/L-type classification | O(n) — single reverse scan |
| LMS position identification | O(n) — single scan |
| Induce sort (L-type + S-type) | O(n) — each element visited O(1) times per pass |
| LMS substring naming | O(n) — amortized, each LMS substring compared at most its length |
| Recursive call | On a problem of size ≤ n/2 (number of LMS positions), giving geometric series: n + n/2 + n/4 + ... = O(n) |
| Final induce sort | O(n) |

Total: O(n) + O(n/2) + O(n/4) + ... = **O(n)**

**Space: O(n)**

| Structure | Size |
|-----------|------|
| `is_s`, `is_lms` | O(n) bools each |
| `sa` | O(n) ints |
| `names`, `lms_name_list` | O(n) ints |
| Bucket boundaries | O(σ) where σ = alphabet size, σ ≤ n |
| Recursion depth | O(log n) frames, each O(n) work but reusing arrays → O(n) total |

### `build_lcp_array` — Kasai's Algorithm

- **Time: O(n)** — the `k` variable decreases at most n times total across the entire loop (amortized analysis)
- **Space: O(n)** — rank array + lcp array

### `substring_search`

- **Time: O(m log n)** — two binary searches over the suffix array, each comparison costs O(m) for pattern of length m
- **Space: O(occ)** — for the result list of `occ` matches

### Comparison with alternatives

| Algorithm | Time | Space | Notes |
|-----------|------|-------|-------|
| **SA-IS (this impl)** | O(n) | O(n) | Optimal. Most practical for large inputs |
| Prefix doubling | O(n log n) | O(n) | Simpler, but slower |
| Naive sort | O(n² log n) | O(n²) | Compare all suffixes directly |

The SA-IS implementation here is asymptotically optimal — you can't do better than O(n) since you must read all n characters.

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