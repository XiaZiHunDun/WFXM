"""Code structure indexing: Tree-sitter when available, else ast (Python) / regex (other)."""

from __future__ import annotations

import ast
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from butler.tools.registry import register_tool

logger = logging.getLogger(__name__)

_ts_python_language: Any = None
_ts_python_checked: bool = False


def _get_tree_sitter_python_language() -> Any:
    """Return tree_sitter Language for Python, or None if unavailable."""
    global _ts_python_language, _ts_python_checked
    if _ts_python_checked:
        return _ts_python_language
    _ts_python_checked = True
    try:
        from tree_sitter import Language  # type: ignore[import-not-found]
        import tree_sitter_python as tsp  # type: ignore[import-not-found]

        _ts_python_language = Language(tsp.language())
    except Exception as e:
        logger.debug("tree-sitter Python not available: %s", e)
        _ts_python_language = None
    return _ts_python_language


def _norm_file_path(path: Path, project_root: str) -> str:
    p = path.resolve()
    if project_root:
        root = Path(project_root).resolve()
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    return str(p)


class CodeGraphIndex:
    """Indexes code structure (functions, classes, imports, calls) into SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS symbols(
                    id INTEGER PRIMARY KEY,
                    file TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line_start INT,
                    line_end INT,
                    parent TEXT,
                    signature TEXT
                );
                CREATE TABLE IF NOT EXISTS imports(
                    id INTEGER PRIMARY KEY,
                    file TEXT NOT NULL,
                    module TEXT NOT NULL,
                    name TEXT,
                    alias TEXT
                );
                CREATE TABLE IF NOT EXISTS calls(
                    id INTEGER PRIMARY KEY,
                    caller_file TEXT NOT NULL,
                    caller_name TEXT NOT NULL,
                    callee TEXT NOT NULL,
                    line INT
                );
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module);
                CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee);
                """
            )

    def _clear_file_rows(self, file_key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM symbols WHERE file = ?", (file_key,))
            conn.execute("DELETE FROM imports WHERE file = ?", (file_key,))
            conn.execute("DELETE FROM calls WHERE caller_file = ?", (file_key,))

    def _count_symbols_file(self, file_key: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM symbols WHERE file = ?", (file_key,)
            ).fetchone()
            return int(row[0]) if row else 0

    def _func_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        try:
            return f"def {node.name}({ast.unparse(node.args)})"
        except AttributeError:
            args: list[str] = []
            a = node.args
            for x in a.posonlyargs:
                args.append(x.arg)
            if a.posonlyargs:
                args.append("/")
            for x in a.args:
                args.append(x.arg)
            if a.vararg:
                args.append("*" + a.vararg.arg)
            elif a.kwonlyargs:
                args.append("*")
            for x in a.kwonlyargs:
                args.append(x.arg)
            if a.kwarg:
                args.append("**" + a.kwarg.arg)
            return f"def {node.name}({', '.join(args)})"

    def _class_signature(self, node: ast.ClassDef) -> str:
        try:
            bases = ", ".join(ast.unparse(b) for b in node.bases)
        except AttributeError:
            bases = ", ".join(getattr(b, "id", str(b)) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"

    def _callee_from_ast(self, call_node: ast.Call) -> str | None:
        f = call_node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
        return None

    def _index_python_ast(self, path: Path, source: str, project_root: str) -> int:
        file_key = _norm_file_path(path, project_root)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            logger.warning("AST parse failed for %s: %s", path, e)
            return 0

        symbols_batch: list[tuple] = []
        imports_batch: list[tuple] = []
        calls_batch: list[tuple] = []

        class Visitor(ast.NodeVisitor):
            """Tracks class vs function scope so nested functions are not marked as methods."""

            def __init__(self) -> None:
                self.scope_stack: list[tuple[str, str]] = []

            def _enclosing_class(self) -> str:
                for kind, nm in reversed(self.scope_stack):
                    if kind == "class":
                        return nm
                return ""

            def visit_ClassDef(self, node: ast.ClassDef) -> Any:
                sig = self._outer._class_signature(node)
                symbols_batch.append(
                    (
                        file_key,
                        node.name,
                        "class",
                        node.lineno,
                        node.end_lineno or node.lineno,
                        "",
                        sig,
                    )
                )
                self.scope_stack.append(("class", node.name))
                self.generic_visit(node)
                self.scope_stack.pop()
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
                self._add_function(node, is_async=False)
                return node

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
                self._add_function(node, is_async=True)
                return node

            def _add_function(
                self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
            ) -> None:
                cls = self._enclosing_class()
                parent = cls
                kind = "method" if cls else "function"
                sig = self._outer._func_signature(node)
                if is_async and sig.startswith("def "):
                    sig = "async " + sig
                symbols_batch.append(
                    (
                        file_key,
                        node.name,
                        kind,
                        node.lineno,
                        node.end_lineno or node.lineno,
                        parent,
                        sig,
                    )
                )
                self.scope_stack.append(("func", node.name))
                self.generic_visit(node)
                self.scope_stack.pop()

        Visitor._outer = self  # type: ignore[attr-defined]
        v = Visitor()

        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node: ast.Import) -> Any:
                for alias in node.names:
                    mods = alias.name.split(".")
                    top = mods[0] if mods else alias.name
                    imports_batch.append(
                        (file_key, top, alias.name, alias.asname or "")
                    )
                return node

            def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
                base = node.module or ""
                for alias in node.names:
                    imports_batch.append(
                        (
                            file_key,
                            base,
                            alias.name,
                            alias.asname or "",
                        )
                    )
                return node

        ImportVisitor().visit(tree)

        class CallVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scope_stack: list[str] = []

            @property
            def current_caller(self) -> str:
                return self.scope_stack[-1] if self.scope_stack else "<module>"

            def visit_ClassDef(self, node: ast.ClassDef) -> Any:
                self.generic_visit(node)
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
                self.scope_stack.append(node.name)
                self.generic_visit(node)
                self.scope_stack.pop()
                return node

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
                self.scope_stack.append(node.name)
                self.generic_visit(node)
                self.scope_stack.pop()
                return node

            def visit_Call(self, node: ast.Call) -> Any:
                callee = self._outer._callee_from_ast(node)
                if callee:
                    calls_batch.append(
                        (
                            file_key,
                            self.current_caller,
                            callee,
                            node.lineno,
                        )
                    )
                self.generic_visit(node)
                return node

        CallVisitor._outer = self  # type: ignore[attr-defined]
        v.visit(tree)
        CallVisitor().visit(tree)

        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO symbols(file, name, kind, line_start, line_end, parent, signature) "
                "VALUES (?,?,?,?,?,?,?)",
                symbols_batch,
            )
            conn.executemany(
                "INSERT INTO imports(file, module, name, alias) VALUES (?,?,?,?)",
                imports_batch,
            )
            conn.executemany(
                "INSERT INTO calls(caller_file, caller_name, callee, line) VALUES (?,?,?,?)",
                calls_batch,
            )

        return len(symbols_batch)

    def _ts_node_text(self, source: bytes, node: Any) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _index_python_tree_sitter(
        self, path: Path, source: str, project_root: str
    ) -> bool:
        lang = _get_tree_sitter_python_language()
        if lang is None:
            return False
        try:
            from tree_sitter import Parser  # type: ignore[import-not-found]
        except ImportError:
            return False

        file_key = _norm_file_path(path, project_root)
        data = source.encode("utf-8")
        parser = Parser(lang)
        tree = parser.parse(data)
        root = tree.root_node

        symbols_batch: list[tuple] = []
        imports_batch: list[tuple] = []
        calls_batch: list[tuple] = []

        def line_start(n: Any) -> int:
            return n.start_point[0] + 1

        def line_end(n: Any) -> int:
            return n.end_point[0] + 1

        def walk_collect_calls(
            node: Any, caller_stack: list[str], current_class: str | None
        ) -> None:
            caller = caller_stack[-1] if caller_stack else "<module>"
            t = node.type
            if t == "function_definition" or t == "async_function_definition":
                name_child = node.child_by_field_name("name")
                fname = (
                    self._ts_node_text(data, name_child).strip()
                    if name_child
                    else "<anon>"
                )
                parent = current_class or ""
                kind = "method" if current_class else "function"
                sig = self._ts_node_text(data, node).split("\n")[0].strip()
                if len(sig) > 500:
                    sig = sig[:500] + "..."
                symbols_batch.append(
                    (
                        file_key,
                        fname,
                        kind,
                        line_start(node),
                        line_end(node),
                        parent,
                        sig,
                    )
                )
                caller_stack.append(fname)
                for ch in node.children:
                    walk_collect_calls(ch, caller_stack, current_class)
                caller_stack.pop()
                return
            if t == "class_definition":
                name_child = node.child_by_field_name("name")
                cname = (
                    self._ts_node_text(data, name_child).strip()
                    if name_child
                    else "<class>"
                )
                sig = self._ts_node_text(data, node).split("\n")[0].strip()
                if len(sig) > 500:
                    sig = sig[:500] + "..."
                symbols_batch.append(
                    (
                        file_key,
                        cname,
                        "class",
                        line_start(node),
                        line_end(node),
                        "",
                        sig,
                    )
                )
                for ch in node.children:
                    walk_collect_calls(ch, caller_stack, cname)
                return
            if t == "call":
                fn = node.child_by_field_name("function")
                callee: str | None = None
                if fn:
                    callee = self._extract_callee_name_from_ts(data, fn)
                if callee:
                    calls_batch.append((file_key, caller, callee, line_start(node)))
            for ch in node.children:
                walk_collect_calls(ch, caller_stack, current_class)

        def walk_imports(node: Any) -> None:
            if node.type == "import_statement":
                for ch in node.children:
                    if ch.type == "dotted_name":
                        mod = self._ts_node_text(data, ch).strip()
                        imports_batch.append(
                            (file_key, mod.split(".")[0], mod, "")
                        )
                    elif ch.type == "aliased_import":
                        nm = ch.child_by_field_name("name")
                        al = ch.child_by_field_name("alias")
                        if nm:
                            full = self._ts_node_text(data, nm).strip()
                            alias = (
                                self._ts_node_text(data, al).strip()
                                if al
                                else ""
                            )
                            imports_batch.append(
                                (file_key, full.split(".")[0], full, alias)
                            )
            elif node.type == "import_from_statement":
                mod_n = node.child_by_field_name("module_name")
                base = (
                    self._ts_node_text(data, mod_n).strip() if mod_n else ""
                )
                for ch in node.children:
                    if ch.type == "dotted_name" and ch != mod_n:
                        nm = self._ts_node_text(data, ch).strip()
                        imports_batch.append((file_key, base, nm, ""))
                    elif ch.type == "wildcard_import":
                        imports_batch.append((file_key, base, "*", ""))
            for ch in node.children:
                walk_imports(ch)

        walk_collect_calls(root, [], None)
        walk_imports(root)

        if not symbols_batch and not imports_batch and not calls_batch:
            return False

        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO symbols(file, name, kind, line_start, line_end, parent, signature) "
                "VALUES (?,?,?,?,?,?,?)",
                symbols_batch,
            )
            conn.executemany(
                "INSERT INTO imports(file, module, name, alias) VALUES (?,?,?,?)",
                imports_batch,
            )
            conn.executemany(
                "INSERT INTO calls(caller_file, caller_name, callee, line) VALUES (?,?,?,?)",
                calls_batch,
            )
        return True

    def _extract_callee_name_from_ts(self, data: bytes, fn: Any) -> str | None:
        t = fn.type
        if t == "identifier":
            return self._ts_node_text(data, fn).strip()
        if t == "attribute":
            attr = fn.child_by_field_name("attribute")
            if attr:
                return self._ts_node_text(data, attr).strip()
        if t == "parenthesized_expression" and fn.children:
            inner = fn.children[1] if len(fn.children) > 1 else fn.children[0]
            return self._extract_callee_name_from_ts(data, inner)
        return None

    _RE_DEF = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
        re.MULTILINE,
    )
    _RE_CLASS = re.compile(
        r"^\s*(?:export\s+)?class\s+(\w+)\b", re.MULTILINE
    )
    _RE_PY_DEF = re.compile(
        r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE
    )
    _RE_PY_CLASS = re.compile(r"^\s*class\s+(\w+)\s*(?:\(.*\))?\s*:", re.MULTILINE)
    _RE_IMPORT = re.compile(
        r"^\s*import\s+([\w\s,]+)(?:;|$)", re.MULTILINE
    )
    _RE_FROM = re.compile(
        r"^\s*from\s+([\w.]+)\s+import\s+([\w\s,.*]+)", re.MULTILINE
    )

    def _index_regex(self, path: Path, source: str, project_root: str) -> int:
        file_key = _norm_file_path(path, project_root)
        symbols_batch: list[tuple] = []
        lines = source.splitlines()
        ext = path.suffix.lower()

        def add_sym(name: str, kind: str, line_no: int) -> None:
            line_end = min(line_no + 1, len(lines)) if lines else line_no
            symbols_batch.append(
                (file_key, name, kind, line_no, line_end, "", f"{kind} {name}")
            )

        if ext == ".py":
            for m in self._RE_PY_CLASS.finditer(source):
                add_sym(m.group(1), "class", source[: m.start()].count("\n") + 1)
            for m in self._RE_PY_DEF.finditer(source):
                add_sym(m.group(1), "function", source[: m.start()].count("\n") + 1)
        else:
            for m in self._RE_CLASS.finditer(source):
                add_sym(m.group(1), "class", source[: m.start()].count("\n") + 1)
            for m in self._RE_DEF.finditer(source):
                add_sym(m.group(1), "function", source[: m.start()].count("\n") + 1)

        imports_batch: list[tuple] = []
        for m in self._RE_IMPORT.finditer(source):
            parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
            for part in parts:
                rhs = part.split(" as ", 1)[0].strip()
                alias = ""
                if " as " in part:
                    alias = part.split(" as ", 1)[1].strip()
                if rhs:
                    top = rhs.split(".")[0]
                    imports_batch.append((file_key, top, rhs, alias))
        for m in self._RE_FROM.finditer(source):
            base = m.group(1).strip()
            names_raw = m.group(2).strip()
            for nm in names_raw.split(","):
                nm_st = nm.strip().split()[0].strip()
                if nm_st and nm_st != "*":
                    imports_batch.append((file_key, base, nm_st, ""))

        callee_re = re.compile(r"\b(\w+)\s*\(")
        calls_batch: list[tuple] = []
        for i, line in enumerate(lines, start=1):
            for cm in callee_re.finditer(line):
                calls_batch.append((file_key, "<module>", cm.group(1), i))

        with self._connect() as conn:
            if symbols_batch:
                conn.executemany(
                    "INSERT INTO symbols(file, name, kind, line_start, line_end, parent, signature) "
                    "VALUES (?,?,?,?,?,?,?)",
                    symbols_batch,
                )
            if imports_batch:
                conn.executemany(
                    "INSERT INTO imports(file, module, name, alias) VALUES (?,?,?,?)",
                    imports_batch,
                )
            if calls_batch:
                conn.executemany(
                    "INSERT INTO calls(caller_file, caller_name, callee, line) VALUES (?,?,?,?)",
                    calls_batch[:5000],
                )

        return len(symbols_batch)

    def index_file(self, file_path: str, project_root: str = "") -> int:
        """Index a single file. Returns number of symbols found."""
        path = Path(file_path)
        if not path.is_file():
            return 0
        file_key = _norm_file_path(path, project_root)
        self._clear_file_rows(file_key)

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Read failed %s: %s", path, e)
            return 0

        ext = path.suffix.lower()
        if ext == ".py":
            if self._index_python_tree_sitter(path, source, project_root):
                return self._count_symbols_file(file_key)
            return self._index_python_ast(path, source, project_root)
        return self._index_regex(path, source, project_root)

    def index_directory(
        self,
        directory: str,
        extensions: tuple[str, ...] = (".py",),
        max_files: int = 500,
    ) -> dict[str, Any]:
        """Index all matching files. Returns counts summary."""
        root = Path(directory).resolve()
        if not root.is_dir():
            return {
                "files_indexed": 0,
                "symbols_found": 0,
                "imports_found": 0,
                "error": f"Not a directory: {directory}",
            }

        with self._connect() as conn:
            conn.executescript(
                "DELETE FROM symbols; DELETE FROM imports; DELETE FROM calls;"
            )

        files_indexed = 0
        symbols_found = 0
        imports_found = 0
        proj_root = str(root)

        for path in sorted(root.rglob("*")):
            if files_indexed >= max_files:
                break
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            if any(p.startswith(".") for p in path.parts):
                continue
            n = self.index_file(str(path), proj_root)
            if n >= 0:
                files_indexed += 1
                symbols_found += n
                with self._connect() as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM imports WHERE file = ?",
                        (_norm_file_path(path, proj_root),),
                    ).fetchone()
                    imports_found += int(row[0]) if row else 0

        return {
            "files_indexed": files_indexed,
            "symbols_found": symbols_found,
            "imports_found": imports_found,
        }

    def find_symbol(self, name: str, kind: str = "") -> list[dict[str, Any]]:
        q = "SELECT file, name, kind, line_start, line_end, signature FROM symbols WHERE name = ?"
        args: list[Any] = [name]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        with self._connect() as conn:
            rows = conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def find_callers(self, function_name: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT caller_file, caller_name, line FROM calls WHERE callee = ?",
                (function_name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_imports_of(self, module: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT file, name, alias FROM imports
                WHERE module = ? OR module LIKE ? OR name = ? OR name LIKE ?
                """,
                (
                    module,
                    f"{module}.%",
                    module,
                    f"{module}.%",
                ),
            ).fetchall()
        return [dict(r) for r in rows]

    def impact_analysis(self, symbol_name: str) -> dict[str, Any]:
        direct = self.find_callers(symbol_name)
        direct_keys = {(d["caller_file"], d["caller_name"]) for d in direct}
        transitive: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int]] = set()
        for d in direct:
            caller_fn = d.get("caller_name", "")
            if not caller_fn or caller_fn == "<module>":
                continue
            for t in self.find_callers(caller_fn):
                key = (
                    t["caller_file"],
                    t["caller_name"],
                    int(t["line"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                if (
                    t["caller_file"],
                    t["caller_name"],
                ) not in direct_keys:
                    transitive.append(dict(t))

        sym_rows = self.find_symbol(symbol_name)
        importing_files: list[str] = []
        if sym_rows:
            fp = sym_rows[0]["file"].replace("\\", "/")
            mod_from_file = fp[:-3].replace("/", ".") if fp.endswith(".py") else fp.replace("/", ".")
            parts = mod_from_file.split(".")
            prefix_candidates = {".".join(parts[:i]) for i in range(1, len(parts) + 1)}
            prefixes = sorted(prefix_candidates, key=len, reverse=True)
            seen_imp: set[str] = set()
            for pref in prefixes:
                for row in self.find_imports_of(pref):
                    fid = row["file"]
                    if fid not in seen_imp:
                        seen_imp.add(fid)
                        importing_files.append(fid)

        return {
            "direct_callers": direct,
            "transitive_callers": transitive,
            "importing_files": sorted(set(importing_files)),
        }

    def generate_project_map(self, max_entries: int = 200) -> str:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file, kind, signature FROM symbols ORDER BY file, line_start"
            ).fetchall()
        by_file: dict[str, list[str]] = {}
        for r in rows:
            f, _kind, sig = r["file"], r["kind"], r["signature"] or ""
            by_file.setdefault(f, []).append(sig.strip())

        parts: list[str] = []
        count = 0
        for f, sigs in sorted(by_file.items()):
            if count >= max_entries:
                break
            chunk = sigs[: max(1, max_entries - count)]
            line = f"{f}: " + ", ".join(chunk)
            parts.append(line)
            count += len(chunk)
        if count >= max_entries and len(parts) > 0:
            parts.append("... (truncated)")
        return "\n".join(parts) if parts else "(empty index)"


_graph_index: CodeGraphIndex | None = None


def _get_butler_db_path() -> Path:
    from butler.core.project_manager import project_manager

    proj = project_manager.get_current()
    root = Path(proj.workspace) if proj else Path.cwd()
    d = root / ".butler"
    d.mkdir(parents=True, exist_ok=True)
    return d / "code_graph.sqlite"


def _get_graph_index() -> CodeGraphIndex:
    global _graph_index
    if _graph_index is None:
        _graph_index = CodeGraphIndex(_get_butler_db_path())
    return _graph_index


@register_tool(
    name="code_graph_index",
    description="索引项目代码结构（函数、类、导入、调用关系）。首次使用或代码变更后需重新索引。",
    parameters={
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "要索引的目录路径"},
        },
        "required": ["directory"],
    },
    category="code",
)
def code_graph_index(directory: str) -> dict[str, Any]:
    idx = _get_graph_index()
    return idx.index_directory(directory)


@register_tool(
    name="code_graph_query",
    description="查询代码结构：查找函数/类定义、调用者、导入关系、变更影响分析。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: find_symbol|find_callers|find_imports|impact_analysis|project_map",
            },
            "name": {"type": "string", "description": "要查询的符号名或模块名"},
            "kind": {
                "type": "string",
                "description": "符号类型过滤: function|class|method（可选）",
            },
        },
        "required": ["action"],
    },
    category="code",
)
def code_graph_query(action: str, name: str = "", kind: str = "") -> dict[str, Any]:
    idx = _get_graph_index()
    a = action.strip().lower()
    if a == "find_symbol":
        if not name:
            return {"error": "name required"}
        return {"symbols": idx.find_symbol(name, kind)}
    if a == "find_callers":
        if not name:
            return {"error": "name required"}
        return {"callers": idx.find_callers(name)}
    if a in ("find_imports", "find_imports_of"):
        if not name:
            return {"error": "name required"}
        return {"imports": idx.find_imports_of(name)}
    if a == "impact_analysis":
        if not name:
            return {"error": "name required"}
        return idx.impact_analysis(name)
    if a == "project_map":
        return {"map": idx.generate_project_map()}
    return {"error": f"unknown action: {action}"}
