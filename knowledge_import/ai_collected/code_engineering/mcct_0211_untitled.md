# Write a Rust function called `debounce` that implements a thread pool for parallel task execution. I
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Rust function called `debounce` that implements a thread pool for parallel task execution. Include comprehensive test cases.

## Conversation
### Turn 1 (user)
Write a Rust function called `debounce` that implements a thread pool for parallel task execution. Include comprehensive test cases.

### Turn 2 (assistant)
**Tool**: `Glob`
```json
{
  "pattern": "**/*.rs"
}
```
**Tool**: `Glob`
```json
{
  "pattern": "**/Cargo.toml"
}
```

### Turn 3 (tool)
fdagent/desktop/src-tauri/src/lib.rs
fdagent/desktop/src-tauri/src/main.rs
fdagent/desktop/src-tauri/build.rs
debounce_pool/src/main.rs
debounce_pool/src/lib.rs
circular_buffer/src/main.rs
circular_buffer/src/lib.rs

### Turn 4 (tool)
fdagent/desktop/src-tauri/Cargo.toml
debounce_pool/Cargo.toml
circular_buffer/Cargo.toml

### Turn 5 (assistant)
There's already a `debounce_pool` crate. Let me check the existing files.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/debounce_pool/Cargo.toml"
}
```
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/debounce_pool/src/lib.rs"
}
```
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/debounce_pool/src/main.rs"
}
```

### Turn 6 (tool)
1	fn main() {
2	    println!("Hello, world!");
3	}
4	

### Turn 7 (tool)
1	[package]
2	name = "debounce_pool"
3	version = "0.1.0"
4	edition = "2024"
5	
6	[dependencies]
7	

### Turn 8 (tool)
1	use std::collections::HashMap;
2	use std::sync::{Arc, Mutex, mpsc};
3	use std::thread;
4	use std::time::Duration;
5	
6	type Task = Box<dyn FnOnce() + Send + 'static>;
7	
8	struct PoolState {
9	    workers: Vec<thread::JoinHandle<()>>,
10	    sender: Option<mpsc::Sender<Task>>,
11	}
12	
13	/// A thread pool that supports debounced task submission.
14	///
15	/// Tasks submitted with the same key within the debounce window
16	/// replace the previous pending task — only the last one executes.
17	pub struct DebouncePool {
18	    state: Arc<Mutex<PoolState>>,
19	    pending: Arc<Mutex<HashMap<String, PendingTask>>>,
20	}
21	
22	struct PendingTask {
23	    cancel: Arc<Mutex<bool>>,
24	    handle: Option<thread::JoinHandle<()>>,
25	}
26	
27	impl DebouncePool {
28	    /// Create a new debounce pool with the given number of worker threads.
29	    pub fn new(num_workers: usize) -> Self {
30	        assert!(num_workers > 0, "need at least one worker");
31	
32	        let (sender, receiver) = mpsc::channel::<Task>();
33	        let receiver = Arc::new(Mutex::new(receiver));
34	
35	        let mut workers = Vec::with_capacity(num_workers);
36	        for _ in 0..num_workers {
37	            let rx = Arc::clone(&receiver);
38	            workers.push(thread::spawn(move || loop {
39	                let msg = rx.lock().unwrap().recv();
40	                match msg {
41	                    Ok(task) => task(),
42	                    Err(_) => break,
43	                }
44	            }));
45	        }
46	
47	        DebouncePool {
48	            state: Arc::new(Mutex::new(PoolState {
49	                workers,
50	                sender: Some(sender),
51	            })),
52	            pending: Arc::new(Mutex::new(HashMap::new())),
53	        }
54	    }
55	
56	    /// Submit a task under `key` with a debounce delay.
57	    ///
58	    /// If another task with the same key is already pending, it is cancelled
59	    /// (prevented from executing). The new task runs on the thread pool after
60	    /// `delay` elapses without another submission for the same key.
61	    pub fn debounce<F>(&self, key: &str, delay: Duration, task: F)
62	    where
63	        F: FnOnce() + Send + 'static,
64	    {
65	        // Cancel any existing pending task for this key.
66	        let cancel_flag = {
67	            let mut pending = self.pending.lock().unwrap();
68	            if let Some(existing) = pending.get(key) {
69	                *existing.cancel.lock().unwrap() = true;
70	            }
71	            let flag = Arc::new(Mutex::new(false));
72	            pending.insert(
73	                key.to_string(),
74	                PendingTask {
75	                    cancel: Arc::clone(&flag),
76	                    handle: None,
77	                },
78	            );
79	            flag
80	        };
81	
82	        let sender = self.state.lock().unwrap().sender.clone().unwrap();
83	        let pending_map = Arc::clone(&self.pending);
84	        let key_owned = key.to_string();
85	
86	        let handle = thread::spawn(move || {
87	            thread::sleep(delay);
88	
89	            let cancelled = *cancel_flag.lock().unwrap();
90	            if cancelled {
91	                // Clean up our entry if we are still the one in the map.
92	                let mut pending = pending_map.lock().unwrap();
93	                if let Some(entry) = pending.get(&key_owned) {
94	                    if Arc::ptr_eq(&entry.cancel, &cancel_flag) {
95	                        pending.remove(&key_owned);
96	                    }
97	                }
98	                return;
99	            }
100	
101	            // Not cancelled — submit the real task to the pool.
102	            let _ = sender.send(Box::new(task));
103	
104	            // Clean up.
105	            let mut pending = pending_map.lock().unwrap();
106	            if let Some(entry) = pending.get(&key_owned) {
107	                if Arc::ptr_eq(&entry.cancel, &cancel_flag) {
108	                    pending.remove(&key_owned);
109	                }
110	            }
111	        });
112	
113	        // Store the debounce timer handle so we can join on shutdown.
114	        let mut pending = self.pending.lock().unwrap();
115	        if let Some(entry) = pending.get_mut(key) {
116	            entry.handle = Some(handle);
117	        }
118	    }
119	
120	    /// Shut down the pool, waiting for all pending debounce timers and
121	    /// queued tasks to complete.
122	    pub fn shutdown(self) {
123	        // Collect debounce timer handles without holding the lock during joins.
124	        let handles: Vec<_> = {
125	            let mut pending = self.pending.lock().unwrap();
126	            pending
127	                .drain()
128	                .filter_map(|(_, mut entry)| entry.handle.take())
129	                .collect()
130	        };
131	
132	        for h in handles {
133	            let _ = h.join();
134	        }
135	
136	        // Drop the sender to signal workers to exit.
137	        {
138	            let mut state = self.state.lock().unwrap();
139	            state.sender.take();
140	        }
141	
142	        // Join worker threads.
143	        let mut state = self.state.lock().unwrap();
144	        for handle in state.workers.drain(..) {
145	            let _ = handle.join();
146	        }
147	    }
148	}
149	
150	impl Drop for DebouncePool {
151	    fn drop(&mut self) {
152	        // Best-effort: drop the sender so workers eventually exit.
153	        if let Ok(mut state) = self.state.lock() {
154	            state.sender.take();
155	        }
156	    }
157	}
158	
159	#[cfg(test)]
160	mod tests {
161	    use super::*;
162	    use std::sync::atomic::{AtomicUsize, Ordering};
163	    use std::time::Instant;
164	
165	    #[test]
166	    fn test_single_task_executes() {
167	        let pool = DebouncePool::new(2);
168	        let executed = Arc::new(AtomicUsize::new(0));
169	        let flag = executed.clone();
170	
171	        pool.debounce(
172	            "k",
173	            Duration::from_millis(50),
174	            move || {
175	                flag.fetch_add(1, Ordering::SeqCst);
176	            },
177	        );
178	
179	        thread::sleep(Duration::from_millis(150));
180	        assert_eq!(executed.load(Ordering::SeqCst), 1);
181	        pool.shutdown();
182	    }
183	
184	    #[test]
185	    fn test_debounce_cancels_previous() {
186	        let pool = DebouncePool::new(2);
187	        let count = Arc::new(AtomicUsize::new(0));
188	
189	        for _ in 0..5 {
190	            let c = count.clone();
191	            pool.debounce("same-key", Duration::from_millis(40), move || {
192	                c.fetch_add(1, Ordering::SeqCst);
193	            });
194	            thread::sleep(Duration::from_millis(10));
195	        }
196	
197	        // Only the last one should execute.
198	        thread::sleep(Duration::from_millis(100));
199	        assert_eq!(count.load(Ordering::SeqCst), 1);
200	        pool.shutdown();
201	    }
202	
203	    #[test]
204	    fn test_different_keys_run_independently() {
205	        let pool = DebouncePool::new(2);
206	        let a_count = Arc::new(AtomicUsize::new(0));
207	        let b_count = Arc::new(AtomicUsize::new(0));
208	
209	        let ac = a_count.clone();
210	        pool.debounce("a", Duration::from_millis(30), move || {
211	            ac.fetch_add(1, Ordering::SeqCst);
212	        });
213	
214	        let bc = b_count.clone();
215	        pool.debounce("b", Duration::from_millis(30), move || {
216	            bc.fetch_add(1, Ordering::SeqCst);
217	        });
218	
219	        thread::sleep(Duration::from_millis(100));
220	        assert_eq!(a_count.load(Ordering::SeqCst), 1);
221	        assert_eq!(b_count.load(Ordering::SeqCst), 1);
222	        pool.shutdown();
223	    }
224	
225	    #[test]
226	    fn test_task_runs_after_delay() {
227	        let pool = DebouncePool::new(2);
228	        let ran = Arc::new(AtomicUsize::new(0));
229	        let flag = ran.clone();
230	
231	        let start = Instant::now();
232	        pool.debounce(
233	            "timed",
234	            Duration::from_millis(80),
235	            move || {
236	                flag.fetch_add(1, Ordering::SeqCst);
237	            },
238	        );
239	
240	        thread::sleep(Duration::from_millis(200));
241	        let elapsed = start.elapsed();
242	        assert_eq!(ran.load(Ordering::SeqCst), 1);
243	        assert!(elapsed >= Duration::from_millis(70), "task ran too early");
244	        pool.shutdown();
245	    }
246	
247	    #[test]
248	    fn test_rapid_resubmission_last_wins() {
249	        let pool = DebouncePool::new(2);
250	        let results = Arc::new(Mutex::new(Vec::new()));
251	
252	        for i in 0..10 {
253	            let r = results.clone();
254	            pool.debounce("rapid", Duration::from_millis(30), move || {
255	                r.lock().unwrap().push(i);
256	            });
257	            thread::sleep(Duration::from_millis(5));
258	        }
259	
260	        thread::sleep(Duration::from_millis(100));
261	        let r = results.lock().unwrap();
262	        assert_eq!(*r, vec![9]);
263	        pool.shutdown();
264	    }
265	
266	    #[test]
267	    fn test_multiple_workers_execute_concurrently() {
268	        let pool = DebouncePool::new(4);
269	        let counter = Arc::new(AtomicUsize::new(0));
270	
271	        for i in 0..4 {
272	            let c = counter.clone();
273	            pool.debounce(&format!("concurrent-{}", i), Duration::from_millis(20), move || {
274	                c.fetch_add(1, Ordering::SeqCst);
275	            });
276	        }
277	
278	        thread::sleep(Duration::from_millis(100));
279	        assert_eq!(counter.load(Ordering::SeqCst), 4);
280	        pool.shutdown();
281	    }
282	
283	    #[test]
284	    fn test_submit_after_delay_gap_executes_again() {
285	        let pool = DebouncePool::new(2);
286	        let count = Arc::new(AtomicUsize::new(0));
287	
288	        // First submission — let it execute.
289

### Turn 9 (assistant)
The crate already has a complete implementation. Let me verify the tests pass.
**Tool**: `Bash`
```json
{
  "command": "cd /data/agent/choucisan/debounce_pool && cargo test 2>&1",
  "description": "Run debounce_pool tests",
  "timeout": 120000
}
```

### Turn 10 (tool)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.01s
     Running unittests src/lib.rs (target/debug/deps/debounce_pool-32b8b3598c1d014b)

running 9 tests
test tests::test_shutdown_waits_for_pending_tasks ... ok
test tests::test_zero_delay ... ok
test tests::test_different_keys_run_independently ... ok
test tests::test_multiple_workers_execute_concurrently ... ok
test tests::test_single_task_executes ... ok
test tests::test_debounce_cancels_previous ... ok
test tests::test_rapid_resubmission_last_wins ... ok
test tests::test_submit_after_delay_gap_executes_again ... ok
test tests::test_task_runs_after_delay ... ok

test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.21s

     Running unittests src/main.rs (target/debug/deps/debounce_pool-4408d1f56d58ec91)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

   Doc-tests debounce_pool

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

### Turn 11 (assistant)
The `debounce_pool` crate already has a complete implementation with all 9 tests passing. Here's what's in place:

**`DebouncePool`** (`debounce_pool/src/lib.rs`) — a thread pool with debounced task submission:

- **`new(num_workers)`** — creates a pool with N worker threads sharing a channel-based task queue
- **`debounce(key, delay, task)`** — submits a task under a string key with a debounce delay. If another task with the same key is submitted within the delay window, the previous one is cancelled and only the last one executes
- **`shutdown()`** — drains pending debounce timers and joins all worker threads

**9 test cases** covering:

| Test | What it verifies |
|---|---|
| `test_single_task_executes` | A single debounced task runs |
| `test_debounce_cancels_previous` | Rapid re-submissions cancel earlier tasks |
| `test_different_keys_run_independently` | Separate keys debounce independently |
| `test_task_runs_after_delay` | Task respects the debounce delay |
| `test_rapid_resubmission_last_wins` | 10 rapid submissions → only the last value is captured |
| `test_multiple_workers_execute_concurrently` | 4 workers run 4 different-key tasks concurrently |
| `test_submit_after_delay_gap_executes_again` | A key can execute again after its debounce window passes |
| `test_zero_delay` | Zero-delay debounce still works |
| `test_shutdown_waits_for_pending_tasks` | `shutdown()` blocks until pending tasks complete |

No changes needed — the implementation and tests are solid.

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