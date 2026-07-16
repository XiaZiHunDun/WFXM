# Implement KMP string matching algorithm in Python. Analyze its time and space complexity.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Implement KMP string matching algorithm in Python. Analyze its time and space complexity.

## Conversation
### Turn 1 (user)
Implement KMP string matching algorithm in Python. Analyze its time and space complexity.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/kmp.py",
  "content": "\"\"\"KMP (Knuth-Morris-Pratt) string matching algorithm.\"\"\"\n\n\ndef build_lps(pattern: str) -> list[int]:\n    \"\"\"Build the Longest Proper Prefix which is also Suffix table.\n\n    lps[i] = length of the longest proper prefix of pattern[0..i]\n    that is also a suffix of pattern[0..i].\n    \"\"\"\n    m = len(pattern)\n    lps = [0] * m\n    length = 0  # length of the previous longest prefix-suffix\n    i = 1\n\n    while 
```

### Turn 3 (tool)
<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan/kmp.py 2>/dev/null; echo \"exit:$?\"",
  "description": "Check if kmp.py already exists"
}
```

### Turn 5 (tool)
/data/agent/choucisan/kmp.py
exit:0

### Turn 6 (assistant)
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/kmp.py"
}
```

### Turn 7 (tool)
1	"""Knuth-Morris-Pratt (KMP) string matching algorithm."""
2	
3	
4	def build_lps(pattern: str) -> list[int]:
5	    """Build the Longest Proper Prefix which is also Suffix (LPS) array.
6	
7	    lps[i] = length of the longest proper prefix of pattern[0..i]
8	    that is also a suffix of pattern[0..i].
9	    """
10	    m = len(pattern)
11	    lps = [0] * m
12	    length = 0
13	    i = 1
14	    while i < m:
15	        if pattern[i] == pattern[length]:
16	            length += 1
17	            lps[i] = length
18	            i += 1
19	        elif length:
20	            length = lps[length - 1]
21	        else:
22	            lps[i] = 0
23	            i += 1
24	    return lps
25	
26	
27	def kmp_search(text: str, pattern: str) -> list[int]:
28	    """Return all starting indices where pattern occurs in text using KMP.
29	
30	    Time: O(n + m), Space: O(m) where n = len(text), m = len(pattern).
31	    """
32	    if not pattern:
33	        return list(range(len(text) + 1))
34	
35	    n, m = len(text), len(pattern)
36	    if m > n:
37	        return []
38	
39	    lps = build_lps(pattern)
40	    indices: list[int] = []
41	    i = j = 0  # i -> text index, j -> pattern index
42	    while i < n:
43	        if text[i] == pattern[j]:
44	            i += 1
45	            j += 1
46	            if j == m:
47	                indices.append(i - j)
48	                j = lps[j - 1]
49	        elif j:
50	            j = lps[j - 1]
51	        else:
52	            i += 1
53	    return indices
54	
55	
56	def kmp_find(text: str, pattern: str) -> int:
57	    """Return the first index where pattern occurs in text, or -1."""
58	    results = kmp_search(text, pattern)
59	    return results[0] if results else -1
60	

### Turn 8 (assistant)
The file already contains a solid KMP implementation. Let me verify it works and then provide the analysis.
**Tool**: `Bash`
```json
{
  "command": "python3 -c \"\nfrom kmp import kmp_search, kmp_find, build_lps\n\n# Test LPS table\nprint('LPS of ABABCABAB:', build_lps('ABABCABAB'))\nprint('LPS of AAAAAA:   ', build_lps('AAAAAA'))\nprint('LPS of ABCDABDC: ', build_lps('ABCDABDC'))\nprint()\n\n# Test search\ntests = [\n    ('ABABDABACDABABCABAB', 'ABABCABAB'),\n    ('AAAAAA', 'AA'),\n    ('ABCABCABC', 'ABC'),\n    ('hello world', 'world'),\n    ('abcdef', 'xyz'),\n    ('', 'a'),\n    ('abc', ''),\n    ('aaa', 'a'),\n]\nfor tex
```

### Turn 9 (tool)
LPS of ABABCABAB: [0, 0, 1, 2, 0, 1, 2, 3, 4]
LPS of AAAAAA:    [0, 1, 2, 3, 4, 5]
LPS of ABCDABDC:  [0, 0, 0, 0, 1, 2, 0, 0]

text='ABABDABACDABABCABAB'     pattern='ABABCABAB'     -> [10]
text='AAAAAA'                  pattern='AA'            -> [0, 1, 2, 3, 4]
text='ABCABCABC'               pattern='ABC'           -> [0, 3, 6]
text='hello world'             pattern='world'         -> [6]
text='abcdef'                  pattern='xyz'           -> []
text=''                        pattern='a'             -> []
text='abc'                     pattern=''              -> [0, 1, 2, 3]
text='aaa'                     pattern='a'             -> [0, 1, 2]

kmp_find("hello world", "world") = 6
kmp_find("hello", "xyz")         = -1

### Turn 10 (assistant)
All tests pass. Here's the implementation in `kmp.py` and the complexity analysis:

## How KMP works

1. **`build_lps(pattern)`** — Preprocesses the pattern to build the LPS (Longest Proper Prefix which is also Suffix) array. `lps[i]` tells us the length of the longest prefix of `pattern[0..i]` that is also its suffix. This lets us skip characters on mismatch without backtracking in the text.

2. **`kmp_search(text, pattern)`** — Scans left-to-right through `text`. On a mismatch, instead of restarting from the next character (like brute force), it uses the LPS table to jump the pattern index `j` back to `lps[j-1]`, keeping `i` in place. This avoids re-examining text characters.

## Complexity analysis

| | KMP | Brute Force |
|---|---|---|
| **Time (preprocessing)** | O(m) | — |
| **Time (search)** | O(n) | O(n·m) worst case |
| **Total time** | **O(n + m)** | **O(n·m)** |
| **Space** | **O(m)** for LPS array | O(1) |

Where `n = len(text)`, `m = len(pattern)`.

**Why O(n) for search:** The text index `i` never moves backward. It advances by at most 1 per iteration, so the while loop runs at most `2n` times (each iteration either increments `i` or decrements `j`, and `j` can decrease at most as many times as it was increased). This gives O(n) amortized.

**Why O(m) for preprocessing:** The LPS construction uses two pointers (`i` and `length`) where `i` strictly increases, and `length` can only decrease by as much as it previously increased — so total work is O(m).

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