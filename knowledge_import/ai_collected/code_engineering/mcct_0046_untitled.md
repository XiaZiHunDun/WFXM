# Implement Rabin-Karp string matching in Python. Analyze its time and space complexity.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Implement Rabin-Karp string matching in Python. Analyze its time and space complexity.

## Conversation
### Turn 1 (user)
Implement Rabin-Karp string matching in Python. Analyze its time and space complexity.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/rabin_karp.py",
  "content": "def rabin_karp(text: str, pattern: str) -> list[int]:\n    \"\"\"Return all starting indices where pattern occurs in text using Rabin-Karp.\"\"\"\n    n, m = len(text), len(pattern)\n    if m > n:\n        return []\n\n    base = 256\n    mod = (1 << 61) - 1  # Mersenne prime for fewer collisions\n\n    # Precompute base^(m-1) % mod\n    h = pow(base, m - 1, mod)\n\n    # Initial hash values for pattern and first window of tex
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/rabin_karp.py 2>/dev/null || echo \"NOT_EXISTS\"",
  "description": "Check if file exists"
}
```

### Turn 5 (tool)
/data/agent/choucisan/rabin_karp.py

### Turn 6 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/rabin_karp.py"
}
```

### Turn 7 (tool)
1	"""Rabin-Karp vs brute-force string matching comparison."""
2	
3	
4	def brute_force(text: str, pattern: str) -> list[int]:
5	    """Check every window with direct substring comparison.
6	
7	    Time:  O(nm) always.
8	    Space: O(1) auxiliary.
9	    """
10	    n, m = len(text), len(pattern)
11	    if m == 0:
12	        return list(range(n + 1))
13	    if m > n:
14	        return []
15	
16	    hits = []
17	    for i in range(n - m + 1):
18	        if text[i : i + m] == pattern:
19	            hits.append(i)
20	    return hits
21	
22	
23	def rabin_karp(text: str, pattern: str) -> list[int]:
24	    """Rolling-hash match with double hash to near-eliminate collisions.
25	
26	    Uses two independent rolling hashes to reduce collision probability
27	    to near-zero, with a final substring check to guarantee correctness.
28	
29	    Time:  O(n + m) average, O(nm) worst case (many collisions).
30	    Space: O(1) auxiliary.
31	    """
32	    n, m = len(text), len(pattern)
33	
34	    if m == 0:
35	        return list(range(n + 1))
36	    if m > n:
37	        return []
38	
39	    BASE = 256
40	    MOD1 = 1_000_000_007
41	    MOD2 = 1_000_000_009
42	
43	    base_pow1 = pow(BASE, m - 1, MOD1)
44	    base_pow2 = pow(BASE, m - 1, MOD2)
45	
46	    h_pat1 = h_pat2 = 0
47	    h_txt1 = h_txt2 = 0
48	    for i in range(m):
49	        cp = ord(pattern[i])
50	        h_pat1 = (h_pat1 * BASE + cp) % MOD1
51	        h_pat2 = (h_pat2 * BASE + cp) % MOD2
52	        ct = ord(text[i])
53	        h_txt1 = (h_txt1 * BASE + ct) % MOD1
54	        h_txt2 = (h_txt2 * BASE + ct) % MOD2
55	
56	    hits: list[int] = []
57	
58	    for i in range(n - m + 1):
59	        if h_txt1 == h_pat1 and h_txt2 == h_pat2:
60	            if text[i : i + m] == pattern:
61	                hits.append(i)
62	
63	        if i < n - m:
64	            out_char = ord(text[i]) * base_pow1
65	            h_txt1 = (h_txt1 - out_char) * BASE + ord(text[i + m])
66	            h_txt1 %= MOD1
67	
68	            out_char = ord(text[i]) * base_pow2
69	            h_txt2 = (h_txt2 - out_char) * BASE + ord(text[i + m])
70	            h_txt2 %= MOD2
71	
72	    return hits
73	
74	
75	# ── Correctness tests ───────────────────────────────────────────────────
76	
77	def test():
78	    tests = [
79	        ("abcabcabc", "abc", [0, 3, 6]),
80	        ("aaaaaa", "aa", [0, 1, 2, 3, 4]),
81	        ("abcdef", "gh", []),
82	        ("abcdef", "", [0, 1, 2, 3, 4, 5, 6]),
83	        ("", "a", []),
84	        ("", "", [0]),
85	        ("a", "a", [0]),
86	        ("abc", "abcd", []),
87	        ("aabaaabaaab", "aabaaab", [0, 4]),
88	        ("abababab", "abab", [0, 2, 4]),
89	    ]
90	    for text, pattern, expected in tests:
91	        assert brute_force(text, pattern) == expected, f"BF FAIL: {text!r}, {pattern!r}"
92	        assert rabin_karp(text, pattern) == expected, f"RK FAIL: {text!r}, {pattern!r}"
93	    print("All correctness tests passed.\n")
94	
95	
96	# ── Benchmark ───────────────────────────────────────────────────────────
97	
98	def benchmark():
99	    import random
100	    import string
101	    import time
102	
103	    random.seed(42)
104	    size = 200_000
105	    text = "".join(random.choices(string.ascii_lowercase, k=size))
106	
107	    cases = [
108	        ("rare 20-char pattern", text[50_000 : 50_020]),
109	        ("common 'abc'",          "abc"),
110	        ("single char 'a'",      "a"),
111	    ]
112	
113	    for desc, pattern in cases:
114	        print(f"Pattern: {desc}  (len={len(pattern)})")
115	        for name, func in [("Brute-force", brute_force), ("Rabin-Karp", rabin_karp)]:
116	            start = time.perf_counter()
117	            result = func(text, pattern)
118	            elapsed = time.perf_counter() - start
119	            print(f"  {name:12s}  matches={len(result):5d}  time={elapsed:.4f}s")
120	        print()
121	
122	
123	if __name__ == "__main__":
124	    test()
125	    benchmark()
126	

### Turn 8 (assistant)
The file already contains a solid Rabin-Karp implementation. Let me run it to verify correctness and performance.
**Tool**: `Bash`
```json
{
  "command": "python rabin_karp.py",
  "description": "Run Rabin-Karp tests and benchmarks"
}
```

### Turn 9 (tool)
All correctness tests passed.

Pattern: rare 20-char pattern  (len=20)
  Brute-force   matches=    1  time=0.0229s
  Rabin-Karp    matches=    1  time=0.1588s

Pattern: common 'abc'  (len=3)
  Brute-force   matches=    9  time=0.0227s
  Rabin-Karp    matches=    9  time=0.1114s

Pattern: single char 'a'  (len=1)
  Brute-force   matches= 7627  time=0.0202s
  Rabin-Karp    matches= 7627  time=0.0973s

### Turn 10 (assistant)
All tests pass. Here's the complexity analysis:

**Time Complexity**

| Case | Rabin-Karp | Brute Force |
|------|-----------|-------------|
| **Average** | O(n + m) | O(nm) |
| **Worst case** | O(nm) | O(nm) |

- **Average**: Each of the `n - m + 1` windows computes a rolling hash in O(1) by removing the outgoing character and adding the incoming one. Hash comparison is O(1), and the final substring equality check (`text[i:i+m] == pattern`) only fires on hash matches, which with a good hash is O(1) times. Total: O(n) + O(m) for initial hash.
- **Worst case**: If every window produces a hash collision (all windows hash-match but most aren't real matches), each triggers an O(m) substring comparison → O(nm). The double-hash scheme (two independent moduli: 10^9+7 and 10^9+9) makes this astronomically unlikely.

**Space Complexity**: O(1) auxiliary — only a fixed number of integer variables for the two rolling hashes, regardless of input size.

**Why brute force is faster here**: Python's `text[i:i+m] == pattern` is a C-level memcmp, which is extremely fast. The rolling hash arithmetic happens in pure Python, so the constant factor overhead dominates. Rabin-Karp's O(n + m) advantage materializes in C/C++/Java where character comparison and arithmetic have similar costs, or when searching for **multiple patterns simultaneously** (the algorithm's real strength — one hash pass over the text for many patterns).

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