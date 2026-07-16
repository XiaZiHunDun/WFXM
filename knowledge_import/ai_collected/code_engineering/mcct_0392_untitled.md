# Write a JavaScript function called `cache_with_ttl` that validates a value against a JSON schema def
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a JavaScript function called `cache_with_ttl` that validates a value against a JSON schema definition. Include comprehensive test cases.

## Conversation
### Turn 1 (user)
Write a JavaScript function called `cache_with_ttl` that validates a value against a JSON schema definition. Include comprehensive test cases.

### Turn 2 (assistant)
Let me first look at the project structure to understand the context.
**Tool**: `Bash`
```json
{
  "command": "ls /data/agent/choucisan",
  "description": "List files in working directory"
}
```

### Turn 3 (tool)
aho_corasick.py
airscape_bench.jsonl
airscape_qa.jsonl
AirScape_Train_list.txt
analytics-api
api_etl_config.yaml
api_etl_pipeline.py
cam_motion
CamReasoner
circular_buffer
cuda_12.8.0_570.86.10_linux.run
data
debounce_pool
docs
Dog100K
email
etl_config.yaml
etl_demo.py
etl_output
etl_pipeline.py
excel_to_sql.py
fdagent
fdagent.tar.gz
fibonacci.py
flash-attention-2.7.4
flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp310-cp310-linux_x86_64.whl
gen_table.py
go
gpt1
log_etl_config.yaml
log_etl_demo.py
log_etl_pipeline.py
logparser
Makefile
message_queue.py
mimo-claude-code-traces
motion-mllm
motion-mllms
motion-mllmss
motion-mllm-v1
paper.tex
plan.md
__pycache__
rate_limiter.js
rate_limiter.py
rate_limit_express.js
rate_limit_middleware.py
rebuttal
ruby-distributed-lock
run_all.sh
segment_tree.py
skip_list.py
suffix_tree.py
t2v_metrics
task_scheduler.py
test_aho_corasick.py
th.md
trainingfree
uav_accuracy_comparison.png
uavdown
UAVideo
UAVideo-Bench
uav-train-lora
videoRL

### Turn 4 (assistant)
I see there's already a `rate_limiter.js` in the project. Let me check the existing JS file for style conventions.
**Tool**: `Read`
```json
{
  "file_path": "/data/agent/choucisan/rate_limiter.js"
}
```

### Turn 5 (tool)
1	/**
2	 * Validates a value against a JSON Schema definition.
3	 *
4	 * Supports: type, enum, const, string (minLength/maxLength/pattern),
5	 * number (minimum/maximum/exclusiveMinimum/exclusiveMaximum/multipleOf),
6	 * array (items/minItems/maxItems/uniqueItems), object (properties/required/additionalProperties),
7	 * allOf/anyOf/oneOf/not, $ref (inline defs), and nullable types via type arrays.
8	 */
9	function rate_limiter(value, schema) {
10	  const errors = [];
11	  _validate(value, schema, [], errors);
12	  return { valid: errors.length === 0, errors };
13	}
14	
15	function _validate(value, schema, path, errors) {
16	  if (schema === true) return;
17	  if (schema === false) {
18	    errors.push({ path: path.join('.'), message: 'No value is allowed' });
19	    return;
20	  }
21	
22	  // --- const ---
23	  if ('const' in schema && !deepEqual(value, schema.const)) {
24	    errors.push({ path: path.join('.'), message: `Expected const ${JSON.stringify(schema.const)}, got ${JSON.stringify(value)}` });
25	    return;
26	  }
27	
28	  // --- enum ---
29	  if (schema.enum && !schema.enum.some(e => deepEqual(value, e))) {
30	    errors.push({ path: path.join('.'), message: `Value must be one of ${JSON.stringify(schema.enum)}, got ${JSON.stringify(value)}` });
31	    return;
32	  }
33	
34	  // --- nullable ---
35	  if (value === null) {
36	    const nullable = Array.isArray(schema.type) ? schema.type.includes('null') : schema.type === 'null';
37	    if (nullable || schema.nullable === true) return;
38	    errors.push({ path: path.join('.'), message: 'Value is null but schema does not allow null' });
39	    return;
40	  }
41	
42	  // --- type ---
43	  if ('type' in schema && !checkType(value, schema.type)) {
44	    errors.push({ path: path.join('.'), message: `Expected type ${JSON.stringify(schema.type)}, got ${typeof value === 'object' ? (Array.isArray(value) ? 'array' : 'object') : typeof value}` });
45	    return; // no point checking further if type is wrong
46	  }
47	
48	  // --- combiners ---
49	  if (schema.allOf) {
50	    for (const sub of schema.allOf) _validate(value, sub, path, errors);
51	  }
52	  if (schema.anyOf) {
53	    const subErrors = [];
54	    const anyValid = schema.anyOf.some(sub => {
55	      const e = [];
56	      _validate(value, sub, path, e);
57	      if (e.length === 0) return true;
58	      subErrors.push(...e);
59	      return false;
60	    });
61	    if (!anyValid) {
62	      errors.push({ path: path.join('.'), message: 'Value does not match anyOf schemas' });
63	      errors.push(...subErrors);
64	    }
65	  }
66	  if (schema.oneOf) {
67	    const matchCount = schema.oneOf.filter(sub => {
68	      const e = [];
69	      _validate(value, sub, path, e);
70	      return e.length === 0;
71	    }).length;
72	    if (matchCount !== 1) {
73	      errors.push({ path: path.join('.'), message: `Value must match exactly one oneOf schema, matched ${matchCount}` });
74	    }
75	  }
76	  if (schema.not) {
77	    const e = [];
78	    _validate(value, schema.not, path, e);
79	    if (e.length === 0) {
80	      errors.push({ path: path.join('.'), message: 'Value must not match the "not" schema' });
81	    }
82	  }
83	
84	  // --- string ---
85	  if (typeof value === 'string') {
86	    if (schema.minLength !== undefined && value.length < schema.minLength) {
87	      errors.push({ path: path.join('.'), message: `String length ${value.length} is less than minimum ${schema.minLength}` });
88	    }
89	    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
90	      errors.push({ path: path.join('.'), message: `String length ${value.length} exceeds maximum ${schema.maxLength}` });
91	    }
92	    if (schema.pattern && !(new RegExp(schema.pattern).test(value))) {
93	      errors.push({ path: path.join('.'), message: `String does not match pattern "${schema.pattern}"` });
94	    }
95	  }
96	
97	  // --- number ---
98	  if (typeof value === 'number') {
99	    if (schema.minimum !== undefined && value < schema.minimum) {
100	      errors.push({ path: path.join('.'), message: `Value ${value} is less than minimum ${schema.minimum}` });
101	    }
102	    if (schema.maximum !== undefined && value > schema.maximum) {
103	      errors.push({ path: path.join('.'), message: `Value ${value} exceeds maximum ${schema.maximum}` });
104	    }
105	    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) {
106	      errors.push({ path: path.join('.'), message: `Value ${value} is not greater than exclusive minimum ${schema.exclusiveMinimum}` });
107	    }
108	    if (schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) {
109	      errors.push({ path: path.join('.'), message: `Value ${value} is not less than exclusive maximum ${schema.exclusiveMaximum}` });
110	    }
111	    if (schema.multipleOf !== undefined && value % schema.multipleOf !== 0) {
112	      errors.push({ path: path.join('.'), message: `Value ${value} is not a multiple of ${schema.multipleOf}` });
113	    }
114	  }
115	
116	  // --- array ---
117	  if (Array.isArray(value)) {
118	    if (schema.minItems !== undefined && value.length < schema.minItems) {
119	      errors.push({ path: path.join('.'), message: `Array length ${value.length} is less than minimum ${schema.minItems}` });
120	    }
121	    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
122	      errors.push({ path: path.join('.'), message: `Array length ${value.length} exceeds maximum ${schema.maxItems}` });
123	    }
124	    if (schema.uniqueItems) {
125	      const seen = new Set();
126	      for (let i = 0; i < value.length; i++) {
127	        const key = JSON.stringify(value[i]);
128	        if (seen.has(key)) {
129	          errors.push({ path: path.join('.'), message: `Array has duplicate items at index ${i}` });
130	        }
131	        seen.add(key);
132	      }
133	    }
134	    if (schema.items) {
135	      if (Array.isArray(schema.items)) {
136	        // tuple validation
137	        for (let i = 0; i < value.length; i++) {
138	          const itemSchema = schema.items[i] ?? schema.additionalItems;
139	          if (itemSchema) _validate(value[i], itemSchema, [...path, `[${i}]`], errors);
140	        }
141	      } else {
142	        for (let i = 0; i < value.length; i++) {
143	          _validate(value[i], schema.items, [...path, `[${i}]`], errors);
144	        }
145	      }
146	    }
147	  }
148	
149	  // --- object ---
150	  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
151	    const keys = Object.keys(value);
152	
153	    // required
154	    if (schema.required) {
155	      for (const prop of schema.required) {
156	        if (!(prop in value)) {
157	          errors.push({ path: path.join('.'), message: `Missing required property "${prop}"` });
158	        }
159	      }
160	    }
161	
162	    // properties
163	    if (schema.properties) {
164	      for (const key of keys) {
165	        if (schema.properties[key]) {
166	          _validate(value[key], schema.properties[key], [...path, key], errors);
167	        }
168	      }
169	    }
170	
171	    // additionalProperties
172	    if (schema.additionalProperties !== undefined) {
173	      const known = new Set([...Object.keys(schema.properties || {}), ...Object.keys(schema.patternProperties || {})]);
174	      for (const key of keys) {
175	        if (!known.has(key)) {
176	          if (schema.additionalProperties === false) {
177	            errors.push({ path: [...path, key].join('.'), message: `Additional property "${key}" is not allowed` });
178	          } else if (typeof schema.additionalProperties === 'object') {
179	            _validate(value[key], schema.additionalProperties, [...path, key], errors);
180	          }
181	        }
182	      }
183	    }
184	
185	    // patternProperties
186	    if (schema.patternProperties) {
187	      for (const pattern of Object.keys(schema.patternProperties)) {
188	        const regex = new RegExp(pattern);
189	        for (const key of keys) {
190	          if (regex.test(key)) {
191	            _validate(value[key], schema.patternProperties[pattern], [...path, key], errors);
192	          }
193	        }
194	      }
195	    }
196	
197	    // minProperties / maxProperties
198	    if (schema.minProperties !== undefined && keys.length < schema.minProperties) {
199	      errors.push({ path: path.join('.'), message: `Object has ${keys.length} properties, minimum is ${schema.minProperties}` });
200	    }
201	    if (schema.maxProperties !== undefined && keys.length > schema.maxProperties) {
202	      errors.push({ path: path.join('.'), message: `Object has ${keys.length} properties, maximum is ${schema.maxProperties}` });
203	    }
204	  }
205	}
206	
207	function checkType(value, type) {
208	  if (Array.isArray(type)) return type.some(t => checkType(value, t));
209	  switch (type) {
210	    case 'string':  return typeof value === 'string';
211	    case 'number':  return typeof value === 'number';
212	    case 'integer': return typeof value === 'number' && Number.isInteger(value);
213	    case 'boolean': return typeof value === 'boolean';
214	    case 'null':    return value === null;
215	    case 'array':   return Array.isArray(value);
216	    case 'object':  return typeof value === 'object' && value !== null && !Array.isArray(value);
217	    default:        return true;
218	  }
219	}
220	
221	function deepEqual(a, b) {
222	  if (a === b) return true;
223	  if (a === null || b === null) return false;
224	  if (typeof a !== typeof b) return false;
225	  if (typeof a !== 'object') return false;
226	  if (Array.isArray(a) !== Array.isArray(b)) return false;
227	  const keysA = Object.keys(a);
228	  const keysB = Object.keys(b);
229	  if (keysA.length !== keysB.length) return false;
230	  return keysA.every(k => deepEqual(a[k], b[k]));
231	}
232	
233	// ─────────────────────────────────────────────────────────────────────────────
234	// Tests
235	// ───────────────────────────────

### Turn 6 (assistant)
The existing `rate_limiter.js` already contains a JSON schema validator. I'll create a new `cache_with_ttl.js` file with the requested function name and comprehensive tests.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/cache_with_ttl.js",
  "content": "/**\n * Validates a value against a JSON Schema definition.\n *\n * Supports: type, enum, const, string (minLength/maxLength/pattern),\n * number (minimum/maximum/exclusiveMinimum/exclusiveMaximum/multipleOf),\n * array (items/minItems/maxItems/uniqueItems), object (properties/required/additionalProperties),\n * allOf/anyOf/oneOf/not, and nullable types via type arrays.\n */\nfunction cache_with_ttl(value, schema) {\n  con
```

### Turn 7 (tool)
File created successfully at: /data/agent/choucisan/cache_with_ttl.js (file state is current in your context — no need to Read it back)

### Turn 8 (assistant)
Let me run the tests to verify everything passes.
**Tool**: `Bash`
```json
{
  "command": "node cache_with_ttl.js",
  "description": "Run cache_with_ttl tests"
}
```

### Turn 9 (tool)
Exit code 1

── Type checks ──
  ✓ string type passes for string
  ✓ string type fails for number
  ✓ number type passes for number
  ✓ number type fails for string
  ✓ integer type passes for integer
  ✓ integer type fails for float
  ✓ boolean type passes for true
  ✗ boolean type passes for false
    expected valid=false, got valid=true
  ✓ null type passes for null
  ✓ null type fails for 0
  ✓ array type passes for array
  ✓ array type fails for object
  ✓ object type passes for object
  ✓ object type fails for array
  ✓ union type (string|number) passes for string
  ✓ union type (string|number) passes for number
  ✓ union type (string|number) fails for boolean

── Nullable ──
  ✓ null passes with type array including null
  ✓ null fails with string-only type
  ✓ null passes with nullable: true
  ✓ non-null passes with nullable schema

── Const ──
  ✓ const passes with exact match
  ✓ const fails with different value
  ✓ const works with object
  ✓ const fails with different object
  ✓ const works with number
  ✗ const works with null
    expected valid=true, got valid=false
    errors: [
  { path: '', message: 'Value is null but schema does not allow null' }
]
  ✓ const works with boolean

── Enum ──
  ✓ enum passes with valid value
  ✓ enum fails with invalid value
  ✓ enum works with mixed types
  ✓ enum fails with undefined-like value

── String constraints ──
  ✓ minLength passes when met
  ✓ minLength passes when exact
  ✓ minLength fails when not met
  ✓ maxLength passes when met
  ✓ maxLength passes when exact
  ✓ maxLength fails when exceeded
  ✓ empty string passes minLength 0
  ✓ pattern passes on match
  ✓ pattern fails on no match
  ✓ email pattern passes
  ✓ email pattern fails

── Number constraints ──
  ✓ minimum passes when met
  ✓ minimum passes when above
  ✓ minimum fails when below
  ✓ maximum passes when met
  ✓ maximum passes when below
  ✓ maximum fails when above
  ✓ exclusiveMinimum passes when above
  ✓ exclusiveMinimum fails when equal
  ✓ exclusiveMinimum fails when below
  ✓ exclusiveMaximum passes when below
  ✓ exclusiveMaximum fails when equal
  ✓ exclusiveMaximum fails when above
  ✓ multipleOf passes when divisible
  ✓ multipleOf fails when not divisible
  ✓ multipleOf works with 0
  ✓ combined min+max passes in range
  ✓ combined min+max fails out of range

── Array constraints ──
  ✓ minItems passes
  ✓ minItems fails
  ✓ maxItems passes
  ✓ maxItems fails
  ✓ empty array passes minItems 0
  ✓ uniqueItems passes with unique array
  ✓ uniqueItems fails with duplicates
  ✓ uniqueItems passes with empty array
  ✓ items validates each element
  ✓ items rejects invalid element
  ✓ items validates strings
  ✓ tuple items validates by position
  ✓ tuple items fails wrong position type

── Object constraints ──
  ✓ required properties pass when present
  ✓ required properties fail when missing
  ✓ required properties fail with empty object
  ✓ properties validates nested schema
  ✓ properties rejects invalid nested value
  ✓ additionalProperties false rejects extra keys
  ✓ additionalProperties true accepts extra keys
  ✓ additionalProperties schema validates extra keys
  ✓ additionalProperties schema rejects invalid extra keys
  ✓ patternProperties validates matched keys
  ✓ patternProperties rejects mismatched values
  ✓ minProperties passes
  ✓ minProperties fails
  ✓ maxProperties passes
  ✓ maxProperties fails
  ✓ empty object passes minProperties 0

── Combiners ──
  ✓ allOf passes when all sub-schemas match
  ✓ allOf fails when one sub-schema fails
  ✓ anyOf passes when at least one matches
  ✓ anyOf fails when none match
  ✓ oneOf passes when exactly one matches
  ✓ oneOf fails when two match
  ✓ oneOf fails when none match
  ✓ not passes when sub-schema fails
  ✓ not fails when sub-schema passes

── Schema true/false ──
  ✓ schema true accepts any value
  ✓ schema true accepts string
  ✓ schema true accepts null
  ✓ schema true accepts object
  ✓ schema false rejects any value
  ✓ schema false rejects null
  ✓ schema false rejects empty string

── Edge cases ──
  ✓ undefined value with no type constraint
  ✓ NaN with number type
  ✓ Infinity with number type
  ✓ empty string with string type
  ✓ deeply nested object
  ✓ deeply nested object fails

── Nested / complex schemas ──
  ✓ complex: valid user
  ✓ complex: missing required
  ✓ complex: invalid email pattern
  ✓ complex: invalid enum in array
  ✓ complex: additional property rejected
  ✓ complex: nested settings validation
  ✓ address schema: valid
  ✓ address schema: valid with zip+4
  ✓ address schema: invalid zip
  ✓ address schema: missing street

────────────────────────────────────────
Results: 119 passed, 2 failed, 121 total

### Turn 10 (assistant)
Two test failures to fix. The `false` test expectation is wrong (false is a valid boolean), and the const-null ordering issue needs fixing in the validator.
**Tool**: `Edit`
```json
{
  "replace_all": false,
  "file_path": "/data/agent/choucisan/cache_with_ttl.js",
  "old_string": "  // --- nullable ---\n  if (value === null) {\n    const nullable = Array.isArray(schema.type) ? schema.type.includes('null') : schema.type === 'null';\n    if (nullable || schema.nullable === true) return;\n    errors.push({ path: path.join('.'), message: 'Value is null but schema does not allow null' });\n    return;\n  }",
  "new_string": "  // --- nullable ---\n  if (value === null && !('con
```

### Turn 11 (tool)
The file /data/agent/choucisan/cache_with_ttl.js has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 12 (assistant)
**Tool**: `Edit`
```json
{
  "replace_all": false,
  "file_path": "/data/agent/choucisan/cache_with_ttl.js",
  "old_string": "  assert('boolean type passes for false', cache_with_ttl(false, { type: 'boolean' }), false);",
  "new_string": "  assert('boolean type passes for false', cache_with_ttl(false, { type: 'boolean' }), true);"
}
```

### Turn 13 (tool)
The file /data/agent/choucisan/cache_with_ttl.js has been updated successfully. (file state is current in your context — no need to Read it back)

### Turn 14 (assistant)
**Tool**: `Bash`
```json
{
  "command": "node cache_with_ttl.js",
  "description": "Run tests after fixes"
}
```

### Turn 15 (tool)
── Type checks ──
  ✓ string type passes for string
  ✓ string type fails for number
  ✓ number type passes for number
  ✓ number type fails for string
  ✓ integer type passes for integer
  ✓ integer type fails for float
  ✓ boolean type passes for true
  ✓ boolean type passes for false
  ✓ null type passes for null
  ✓ null type fails for 0
  ✓ array type passes for array
  ✓ array type fails for object
  ✓ object type passes for object
  ✓ object type fails for array
  ✓ union type (string|number) passes for string
  ✓ union type (string|number) passes for number
  ✓ union type (string|number) fails for boolean

── Nullable ──
  ✓ null passes with type array including null
  ✓ null fails with string-only type
  ✓ null passes with nullable: true
  ✓ non-null passes with nullable schema

── Const ──
  ✓ const passes with exact match
  ✓ const fails with different value
  ✓ const works with object
  ✓ const fails with different object
  ✓ const works with number
  ✓ const works with null
  ✓ const works with boolean

── Enum ──
  ✓ enum passes with valid value
  ✓ enum fails with invalid value
  ✓ enum works with mixed types
  ✓ enum fails with undefined-like value

── String constraints ──
  ✓ minLength passes when met
  ✓ minLength passes when exact
  ✓ minLength fails when not met
  ✓ maxLength passes when met
  ✓ maxLength passes when exact
  ✓ maxLength fails when exceeded
  ✓ empty string passes minLength 0
  ✓ pattern passes on match
  ✓ pattern fails on no match
  ✓ email pattern passes
  ✓ email pattern fails

── Number constraints ──
  ✓ minimum passes when met
  ✓ minimum passes when above
  ✓ minimum fails when below
  ✓ maximum passes when met
  ✓ maximum passes when below
  ✓ maximum fails when above
  ✓ exclusiveMinimum passes when above
  ✓ exclusiveMinimum fails when equal
  ✓ exclusiveMinimum fails when below
  ✓ exclusiveMaximum passes when below
  ✓ exclusiveMaximum fails when equal
  ✓ exclusiveMaximum fails when above
  ✓ multipleOf passes when divisible
  ✓ multipleOf fails when not divisible
  ✓ multipleOf works with 0
  ✓ combined min+max passes in range
  ✓ combined min+max fails out of range

── Array constraints ──
  ✓ minItems passes
  ✓ minItems fails
  ✓ maxItems passes
  ✓ maxItems fails
  ✓ empty array passes minItems 0
  ✓ uniqueItems passes with unique array
  ✓ uniqueItems fails with duplicates
  ✓ uniqueItems passes with empty array
  ✓ items validates each element
  ✓ items rejects invalid element
  ✓ items validates strings
  ✓ tuple items validates by position
  ✓ tuple items fails wrong position type

── Object constraints ──
  ✓ required properties pass when present
  ✓ required properties fail when missing
  ✓ required properties fail with empty object
  ✓ properties validates nested schema
  ✓ properties rejects invalid nested value
  ✓ additionalProperties false rejects extra keys
  ✓ additionalProperties true accepts extra keys
  ✓ additionalProperties schema validates extra keys
  ✓ additionalProperties schema rejects invalid extra keys
  ✓ patternProperties validates matched keys
  ✓ patternProperties rejects mismatched values
  ✓ minProperties passes
  ✓ minProperties fails
  ✓ maxProperties passes
  ✓ maxProperties fails
  ✓ empty object passes minProperties 0

── Combiners ──
  ✓ allOf passes when all sub-schemas match
  ✓ allOf fails when one sub-schema fails
  ✓ anyOf passes when at least one matches
  ✓ anyOf fails when none match
  ✓ oneOf passes when exactly one matches
  ✓ oneOf fails when two match
  ✓ oneOf fails when none match
  ✓ not passes when sub-schema fails
  ✓ not fails when sub-schema passes

── Schema true/false ──
  ✓ schema true accepts any value
  ✓ schema true accepts string
  ✓ schema true accepts null
  ✓ schema true accepts object
  ✓ schema false rejects any value
  ✓ schema false rejects null
  ✓ schema false rejects empty string

── Edge cases ──
  ✓ undefined value with no type constraint
  ✓ NaN with number type
  ✓ Infinity with number type
  ✓ empty string with string type
  ✓ deeply nested object
  ✓ deeply nested object fails

── Nested / complex schemas ──
  ✓ complex: valid user
  ✓ complex: missing required
  ✓ complex: invalid email pattern
  ✓ complex: invalid enum in array
  ✓ complex: additional property rejected
  ✓ complex: nested settings validation
  ✓ address schema: valid
  ✓ address schema: valid with zip+4
  ✓ address schema: invalid zip
  ✓ address schema: missing street

────────────────────────────────────────
Results: 121 passed, 0 failed, 121 total

### Turn 16 (assistant)
All 121 tests pass. The file is at `cache_with_ttl.js`.

**What it does:**
- `cache_with_ttl(value, schema)` returns `{ valid: boolean, errors: Array }` by validating `value` against a JSON Schema definition
- Supports: `type`, `enum`, `const`, `nullable`, string constraints (`minLength`/`maxLength`/`pattern`), number constraints (`minimum`/`maximum`/`exclusiveMinimum`/`exclusiveMaximum`/`multipleOf`), array constraints (`items`/`minItems`/`maxItems`/`uniqueItems`), object constraints (`properties`/`required`/`additionalProperties`/`patternProperties`/`minProperties`/`maxProperties`), combinators (`allOf`/`anyOf`/`oneOf`/`not`), and schema `true`/`false`

**Test coverage (121 cases):**
- Type checks (17) — all JSON types + union types
- Nullable (4) — type arrays, `nullable: true`
- Const (7) — primitives, objects, null
- Enum (4) — valid/invalid, mixed types
- String (11) — boundaries, patterns, email
- Number (17) — inclusive/exclusive bounds, multipleOf, ranges
- Array (13) — size limits, uniqueness, items, tuples
- Object (16) — required, nested, additionalProperties, patternProperties
- Combiners (9) — allOf, anyOf, oneOf, not
- Schema true/false (7)
- Edge cases (6) — NaN, Infinity, deeply nested
- Complex nested schemas (10) — user profile, address validation

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