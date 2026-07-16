# Code Rabin-Karp string matching in Python. Compare it with a brute-force approach.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Code Rabin-Karp string matching in Python. Compare it with a brute-force approach.

## Conversation
### Turn 1 (user)
Code Rabin-Karp string matching in Python. Compare it with a brute-force approach.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/rabin_karp.py",
  "content": "\"\"\"Rabin-Karp vs brute-force string matching.\"\"\"\n\nimport time\n\n\ndef brute_force(text: str, pattern: str) -> list[int]:\n    \"\"\"Return all starting indices where pattern occurs in text.\"\"\"\n    matches = []\n    n, m = len(text), len(pattern)\n    for i in range(n - m + 1):\n        if text[i : i + m] == pattern:\n            matches.append(i)\n    return matches\n\n\ndef rabin_karp(text: str, pattern: str, bas
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/rabin_karp.py 2>/dev/null && echo EXISTS || echo NOT_FOUND",
  "description": "Check if file exists"
}
```

### Turn 5 (tool)
/data/agent/choucisan/rabin_karp.py
EXISTS

### Turn 6 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/rabin_karp.py"
}
```

### Turn 7 (tool)
1	"""Rabin-Karp string matching with double rolling hash."""
2	
3	
4	def rabin_karp(text: str, pattern: str) -> list[int]:
5	    """Return all starting indices where pattern occurs in text.
6	
7	    Uses two independent rolling hashes to reduce collision probability
8	    to near-zero, with a final substring check to guarantee correctness.
9	
10	    Time:  O(n + m) average, O(nm) worst case (many collisions).
11	    Space: O(1) auxiliary.
12	
13	    Edge cases handled:
14	      - Empty pattern: matches at every position (including len(text)).
15	      - Pattern longer than text: no matches.
16	      - Single-character inputs.
17	    """
18	    n, m = len(text), len(pattern)
19	
20	    if m == 0:
21	        return list(range(n + 1))
22	    if m > n:
23	        return []
24	
25	    BASE = 256
26	    MOD1 = 1_000_000_007
27	    MOD2 = 1_000_000_009
28	
29	    # Precompute BASE^(m-1) % MOD for removing the leading character.
30	    base_pow1 = pow(BASE, m - 1, MOD1)
31	    base_pow2 = pow(BASE, m - 1, MOD2)
32	
33	    # Compute initial hashes for pattern and first window.
34	    h_pat1 = h_pat2 = 0
35	    h_txt1 = h_txt2 = 0
36	    for i in range(m):
37	        cp = ord(pattern[i])
38	        h_pat1 = (h_pat1 * BASE + cp) % MOD1
39	        h_pat2 = (h_pat2 * BASE + cp) % MOD2
40	        ct = ord(text[i])
41	        h_txt1 = (h_txt1 * BASE + ct) % MOD1
42	        h_txt2 = (h_txt2 * BASE + ct) % MOD2
43	
44	    hits: list[int] = []
45	
46	    for i in range(n - m + 1):
47	        # Double hash match -> verify with substring comparison.
48	        if h_txt1 == h_pat1 and h_txt2 == h_pat2:
49	            if text[i : i + m] == pattern:
50	                hits.append(i)
51	
52	        # Roll the window: remove leading char, shift, add trailing char.
53	        if i < n - m:
54	            out_char = ord(text[i]) * base_pow1
55	            h_txt1 = (h_txt1 - out_char) * BASE + ord(text[i + m])
56	            h_txt1 %= MOD1
57	
58	            out_char = ord(text[i]) * base_pow2
59	            h_txt2 = (h_txt2 - out_char) * BASE + ord(text[i + m])
60	            h_txt2 %= MOD2
61	
62	    return hits
63	
64	
65	if __name__ == "__main__":
66	    tests = [
67	        ("abcabcabc", "abc", [0, 3, 6]),
68	        ("aaaaaa", "aa", [0, 1, 2, 3, 4]),
69	        ("abcdef", "gh", []),
70	        ("abcdef", "", [0, 1, 2, 3, 4, 5, 6]),
71	        ("", "a", []),
72	        ("", "", [0]),
73	        ("a", "a", [0]),
74	        ("abc", "abcd", []),
75	        ("aabaaabaaab", "aabaaab", [0, 4]),
76	        ("abababab", "abab", [0, 2, 4]),
77	    ]
78	    for text, pattern, expected in tests:
79	        result = rabin_karp(text, pattern)
80	        assert result == expected, f"FAIL: ({text!r}, {pattern!r}) -> {result}, expected {expected}"
81	    print("All tests passed.")
82	

### Turn 8 (assistant)
The file already has a Rabin-Karp implementation. I'll add a brute-force method and a benchmark comparison.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/rabin_karp.py",
  "content": "\"\"\"Rabin-Karp vs brute-force string matching comparison.\"\"\"\n\n\ndef brute_force(text: str, pattern: str) -> list[int]:\n    \"\"\"Check every window with direct substring comparison.\n\n    Time:  O(nm) always.\n    Space: O(1) auxiliary.\n    \"\"\"\n    n, m = len(text), len(pattern)\n    if m == 0:\n        return list(range(n + 1))\n    if m > n:\n        return []\n\n    hits = []\n    for i in range(n - m + 1):\n 
```

### Turn 9 (tool)
The file /data/agent/choucisan/rabin_karp.py has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 10 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python rabin_karp.py",
  "description": "Run correctness tests and benchmark"
}
```

### Turn 11 (tool)
All correctness tests passed.

Pattern: rare 20-char pattern  (len=20)
  Brute-force   matches=    1  time=0.0164s
  Rabin-Karp    matches=    1  time=0.1110s

Pattern: common 'abc'  (len=3)
  Brute-force   matches=    9  time=0.0162s
  Rabin-Karp    matches=    9  time=0.0765s

Pattern: single char 'a'  (len=1)
  Brute-force   matches= 7627  time=0.0143s
  Rabin-Karp    matches= 7627  time=0.0645s

### Turn 12 (assistant)
Interesting results. Here's what's going on:

**Algorithm comparison:**

| Aspect | Brute-force | Rabin-Karp |
|---|---|---|
| **Time complexity** | O(nm) always | O(n+m) average, O(nm) worst case |
| **Space** | O(1) | O(1) |
| **Approach** | Compare each window character-by-character | Compute rolling hash, compare only on hash match |

**Why brute-force won here:** In CPython, `text[i:i+m] == pattern` is a C-optimized memcmp — it's blisteringly fast. Rabin-Karp's per-character modular arithmetic runs in the Python interpreter, which is much slower per operation. The O(n+m) advantage only materializes when:
- The pattern is **very long** (reducing per-hash relative cost)
- You're matching **multiple patterns simultaneously** (Rabin-Karp's killer feature)
- The language has low-overhead arithmetic (C, Rust, Java)

**When Rabin-Karp shines:** Searching for k patterns at once is O(nk) for brute-force but O(n) for Rabin-Karp (hash all patterns, scan text once). That's its real use case — plagiarism detection, multi-pattern grep, etc.

The code is at `/data/agent/choucisan/rabin_karp.py`.

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