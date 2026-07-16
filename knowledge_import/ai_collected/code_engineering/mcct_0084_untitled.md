# Write a Python implementation of KMP string matching algorithm with detailed comments explaining eac
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python implementation of KMP string matching algorithm with detailed comments explaining each step.

## Conversation
### Turn 1 (user)
Write a Python implementation of KMP string matching algorithm with detailed comments explaining each step.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/kmp.py",
  "content": "def build_failure_function(pattern: str) -> list[int]:\n    \"\"\"Build the KMP failure function (partial match table).\n\n    For each position i in the pattern, failure[i] stores the length of the\n    longest proper prefix of pattern[:i+1] that is also a suffix. This tells\n    us how far back we can shift the pattern when a mismatch occurs, without\n    re-examining characters we've already matched.\n\n    Time: O(m) where m = le
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/kmp.py"
}
```

### Turn 5 (tool)
1	"""KMP vs brute-force string matching comparison."""
2	
3	import time
4	
5	
6	# ── Brute-force ──────────────────────────────────────────────────────
7	
8	def brute_force(text: str, pattern: str) -> list[int]:
9	    """Find all occurrences of pattern in text.
10	
11	    For each position i in text, walk pattern left-to-right until a
12	    mismatch or full match.  O(n * m) worst-case.
13	    """
14	    n, m = len(text), len(pattern)
15	    if m == 0:
16	        return list(range(n + 1))
17	    matches = []
18	    for i in range(n - m + 1):
19	        j = 0
20	        while j < m and text[i + j] == pattern[j]:
21	            j += 1
22	        if j == m:
23	            matches.append(i)
24	    return matches
25	
26	
27	# ── KMP ──────────────────────────────────────────────────────────────
28	
29	def build_lps(pattern: str) -> list[int]:
30	    """Build the Longest Proper Prefix which is also Suffix array.
31	
32	    lps[i] = length of the longest proper prefix of pattern[0..i]
33	    that is also a suffix of pattern[0..i].
34	    """
35	    m = len(pattern)
36	    lps = [0] * m
37	    length = 0
38	    i = 1
39	    while i < m:
40	        if pattern[i] == pattern[length]:
41	            length += 1
42	            lps[i] = length
43	            i += 1
44	        elif length:
45	            length = lps[length - 1]
46	        else:
47	            lps[i] = 0
48	            i += 1
49	    return lps
50	
51	
52	def kmp(text: str, pattern: str) -> list[int]:
53	    """Find all occurrences of pattern in text using the KMP algorithm.
54	
55	    Uses the LPS array to avoid re-examining characters: when a mismatch
56	    happens after j matched characters, we know the first lps[j-1]
57	    characters of the pattern are already aligned with text — no
58	    backtracking in text.  O(n + m).
59	    """
60	    n, m = len(text), len(pattern)
61	    if m == 0:
62	        return list(range(n + 1))
63	    lps = build_lps(pattern)
64	    matches = []
65	    i = j = 0  # i -> text index, j -> pattern index
66	    while i < n:
67	        if text[i] == pattern[j]:
68	            i += 1
69	            j += 1
70	        if j == m:
71	            matches.append(i - j)
72	            j = lps[j - 1]
73	        elif i < n and text[i] != pattern[j]:
74	            if j:
75	                j = lps[j - 1]
76	            else:
77	                i += 1
78	    return matches
79	
80	
81	# ── Tests ────────────────────────────────────────────────────────────
82	
83	def test():
84	    cases = [
85	        ("ABABDABACDABABCABAB", "ABABCABAB", [10]),
86	        ("AAAAAA", "AA", [0, 1, 2, 3, 4]),
87	        ("ABCABCABC", "ABC", [0, 3, 6]),
88	        ("hello world", "world", [6]),
89	        ("hello world", "xyz", []),
90	        ("aaaaaa", "b", []),
91	        ("", "a", []),
92	        ("abc", "", list(range(4))),
93	    ]
94	    for text, pattern, expected in cases:
95	        assert brute_force(text, pattern) == expected, f"BF failed: {text!r}, {pattern!r}"
96	        assert kmp(text, pattern) == expected, f"KMP failed: {text!r}, {pattern!r}"
97	    print("All tests passed.")
98	
99	
100	# ── Benchmark ────────────────────────────────────────────────────────
101	
102	def benchmark():
103	    scenarios = [
104	        (
105	            "worst-case (repeated char, near-match pattern)",
106	            "a" * 100_000 + "b",
107	            "a" * 20 + "b",
108	        ),
109	        (
110	            "repeated segment",
111	            ("ABCD" * 25_000) + "E",
112	            ("ABCD" * 5) + "E",
113	        ),
114	        (
115	            "random-ish DNA",
116	            ("ACGTACGT" * 12_500) + "GATTACA",
117	            "GATTACA",
118	        ),
119	    ]
120	
121	    for label, text, pattern in scenarios:
122	        print(f"\n--- {label} ---")
123	        print(f"  text: {len(text):>10,} chars | pattern: {len(pattern)} chars")
124	
125	        start = time.perf_counter()
126	        r1 = brute_force(text, pattern)
127	        t1 = time.perf_counter() - start
128	
129	        start = time.perf_counter()
130	        r2 = kmp(text, pattern)
131	        t2 = time.perf_counter() - start
132	
133	        assert r1 == r2
134	        print(f"  brute-force : {t1:.4f}s  ({len(r1)} matches)")
135	        print(f"  KMP         : {t2:.4f}s  ({len(r2)} matches)")
136	        if t2 > 0:
137	            print(f"  speedup     : {t1 / t2:.1f}x")
138	
139	
140	if __name__ == "__main__":
141	    test()
142	    benchmark()
143	

### Turn 6 (assistant)
There's already a `kmp.py` with a working implementation but minimal comments. I'll rewrite it with detailed comments explaining each step.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/kmp.py",
  "content": "\"\"\"KMP string matching algorithm with detailed comments.\n\nThe Knuth-Morris-Pratt (KMP) algorithm searches for a pattern in text in\nO(n + m) time by precomputing a \"failure function\" (LPS array) that tells\nus how far to shift the pattern on a mismatch — avoiding redundant work.\n\nKey insight: when we mismatch after matching j characters of the pattern,\nwe already know what those j text characters are. The LPS array tells us
```

### Turn 7 (tool)
The file /data/agent/choucisan/kmp.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 8 (assistant)
Let me verify it runs correctly.
**Tool**: `Bash`
```json
{
  "command": "python kmp.py",
  "description": "Run KMP implementation tests and benchmark"
}
```

### Turn 9 (tool)
All tests passed.

--- worst-case (repeated char, near-match pattern) ---
  text:    100,001 chars | pattern: 21 chars
  brute-force : 0.2163s  (1 matches)
  KMP         : 0.0218s  (1 matches)
  speedup     : 9.9x

--- repeated segment ---
  text:    100,001 chars | pattern: 21 chars
  brute-force : 0.0583s  (1 matches)
  KMP         : 0.0186s  (1 matches)
  speedup     : 3.1x

--- random-ish DNA ---
  text:    100,007 chars | pattern: 7 chars
  brute-force : 0.0141s  (1 matches)
  KMP         : 0.0192s  (1 matches)
  speedup     : 0.7x

### Turn 10 (assistant)
All tests pass. Here's a summary of the implementation:

**`kmp.py`** contains two core functions:

1. **`build_lps(pattern)`** — Constructs the LPS (failure) array in O(m). For each position `i`, `lps[i]` stores the length of the longest proper prefix of `pattern[0..i]` that is also a suffix. The example table for `"ABABCABAB"` in the docstring illustrates this clearly.

2. **`kmp(text, pattern)`** — The main search in O(n+m). The key invariant: `i` never backtracks in the text. On a mismatch after matching `j` characters, `lps[j-1]` tells us exactly how far to slide the pattern forward because those characters are already known to match.

**Why KMP wins on worst-case inputs**: the benchmark shows ~10x speedup on `"aaa...ab"` with a nearly-matching pattern, where brute force re-scans the same text characters repeatedly.

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