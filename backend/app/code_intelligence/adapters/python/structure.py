"""
Python structural analysis over the standard-library AST.

Conservative on purpose. Nested locals, attribute access, star
imports, and unresolved packages are declined rather than guessed.
"""

import ast
import posixpath

from app.code_intelligence.types import Location, Span


TYPE_KINDS = frozenset({"class", "type"})

_TEST_DIR_PARTS = frozenset({"test", "tests"})
_TEST_FILENAMES = frozenset({"test.py", "conftest.py"})


def normalize_path(path):
    normalized = posixpath.normpath((path or "").replace("\\", "/"))
    return "" if normalized == "." else normalized


def is_python_path(path):
    return normalize_path(path).lower().endswith(".py")


def is_test_path(path):
    lowered = normalize_path(path).lower()
    if not lowered:
        return False
    name = lowered.rsplit("/", 1)[-1]
    if name in _TEST_FILENAMES:
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    parts = lowered.split("/")
    return any(part in _TEST_DIR_PARTS for part in parts[:-1])


class PythonStructure:
    """Declarations, imports, references, and spans for one snapshot."""

    def analyze(self, files):
        py_files = [
            file
            for file in files
            if is_python_path(file.get("path") or "")
        ]
        by_path = {
            normalize_path(file.get("path") or ""): file
            for file in py_files
            if file.get("path")
        }

        per_file = {}
        for path, file in by_path.items():
            per_file[path] = self._analyze_file(path, file.get("content") or "")

        self._resolve_imports(per_file, by_path)

        symbols = {}
        declarations_by_path = {}
        spans_by_path = {}
        header_end_by_path = {}

        for path, analysis in per_file.items():
            header_end_by_path[path] = analysis["header_end_line"]
            spans_by_path[path] = list(analysis["spans"])
            declarations = []
            for item in analysis["declarations"]:
                location = Location(
                    symbol=item["symbol"],
                    path=path,
                    line=item["line"],
                    kind=item["kind"],
                )
                declarations.append(location)
                symbols.setdefault(item["symbol"], []).append({
                    "symbol": item["symbol"],
                    "path": path,
                    "line": item["line"],
                    "kind": item["kind"],
                })
            declarations.sort(key=lambda item: (item.line, item.symbol))
            declarations_by_path[path] = declarations

        usages = self._references(per_file, symbols)
        relationships = self._relationships(per_file, symbols)

        return {
            "symbols": symbols,
            "declarations_by_path": declarations_by_path,
            "spans_by_path": spans_by_path,
            "header_end_by_path": header_end_by_path,
            "usages": usages,
            "relationships": relationships,
            "contents": {
                path: file.get("content") or ""
                for path, file in by_path.items()
            },
        }

    def resolve(self, symbol, symbols):
        declarations = self._disambiguate(symbols.get(symbol) or [])
        if len(declarations) != 1:
            return None
        return declarations[0]

    def enclosing_span(self, path, line, spans_by_path):
        if line is None or line < 1:
            return None
        candidates = [
            span
            for span in spans_by_path.get(normalize_path(path), ())
            if span.start_line <= line <= span.end_line
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda span: (span.line_count, -span.start_line, span.kind)
        )
        return candidates[0]

    # =========================================================
    # FILE
    # =========================================================

    def _analyze_file(self, path, content):
        empty = {
            "declarations": [],
            "imports": [],
            "spans": [],
            "identifiers": [],
            "heritage": [],
            "header_end_line": None,
        }
        tree = _parse(path, content)
        if tree is None:
            return empty

        declarations = []
        spans = []
        imports = []
        heritage = []

        for stmt in tree.body:
            self._collect_statement(
                stmt, path, declarations, spans, heritage, imports,
            )

        identifiers = _collect_identifiers(tree)

        return {
            "declarations": declarations,
            "imports": imports,
            "spans": spans,
            "identifiers": identifiers,
            "heritage": heritage,
            "header_end_line": _header_end_line(tree),
        }

    def _collect_statement(
        self, stmt, path, declarations, spans, heritage, imports,
    ):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._record(
                path, stmt, stmt.name, "function", declarations, spans,
            )
            return

        if isinstance(stmt, ast.ClassDef):
            self._record(path, stmt, stmt.name, "class", declarations, spans)
            for base in stmt.bases:
                name = _simple_name(base)
                if name:
                    heritage.append({"relationship": "extends", "name": name})
            for child in stmt.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._record(
                        path, child, child.name, "method", declarations, spans,
                    )
                elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                    for target, kind in _binding_targets(child):
                        if _is_dunder(target):
                            continue
                        self._record(
                            path, child, target, "field", declarations, spans,
                        )
            return

        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            for target, kind in _binding_targets(stmt):
                if _is_dunder(target):
                    continue
                self._record(path, stmt, target, kind, declarations, spans)
            return

        if hasattr(ast, "TypeAlias") and isinstance(stmt, ast.TypeAlias):
            name = stmt.name.id if isinstance(stmt.name, ast.Name) else None
            if name:
                self._record(path, stmt, name, "type", declarations, spans)
            return

        if isinstance(stmt, ast.ImportFrom):
            imports.extend(self._import_from(stmt))
            return

        if isinstance(stmt, ast.Import):
            imports.extend(self._import_modules(stmt))

    def _record(self, path, node, symbol, kind, declarations, spans):
        if not symbol or not _is_identifier(symbol):
            return
        start = getattr(node, "lineno", None)
        if not start:
            return
        end = getattr(node, "end_lineno", None) or start
        declarations.append({
            "symbol": symbol,
            "line": start,
            "kind": kind,
        })
        spans.append(
            Span(
                path=path,
                start_line=start,
                end_line=end,
                kind=kind,
                symbol=symbol,
            )
        )

    def _import_from(self, stmt):
        if stmt.module is None:
            records = []
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                records.append({
                    "module": alias.name,
                    "level": stmt.level,
                    "names": [],
                    "resolved": None,
                })
            return records

        names = []
        for alias in stmt.names:
            if alias.name == "*":
                continue
            names.append({
                "name": alias.name,
                "alias": alias.asname,
            })
        return [{
            "module": stmt.module,
            "level": stmt.level,
            "names": names,
            "resolved": None,
        }]

    def _import_modules(self, stmt):
        records = []
        for alias in stmt.names:
            records.append({
                "module": alias.name,
                "level": 0,
                "names": [],
                "resolved": None,
            })
        return records

    # =========================================================
    # REPOSITORY
    # =========================================================

    def _resolve_imports(self, per_file, by_path):
        for path, analysis in per_file.items():
            for item in analysis["imports"]:
                item["resolved"] = resolve_import(
                    path,
                    item["module"],
                    item["level"],
                    by_path,
                )

    def _references(self, per_file, symbols):
        declared_in = {
            symbol: {entry["path"] for entry in entries}
            for symbol, entries in symbols.items()
        }
        usages = []
        seen = set()

        for path, analysis in per_file.items():
            imported_paths = {
                item["resolved"]
                for item in analysis["imports"]
                if item["resolved"]
            }
            if not imported_paths:
                continue

            visible = {}
            local_to_remote = {}
            for item in analysis["imports"]:
                target = item["resolved"]
                if not target:
                    continue
                for spec in item["names"]:
                    remote = spec["name"]
                    local = spec["alias"] or spec["name"]
                    owners = declared_in.get(remote, set())
                    if path in owners or target not in owners:
                        continue
                    reachable = owners & imported_paths
                    if len(reachable) != 1:
                        continue
                    local_to_remote[local] = remote
                    visible[remote] = target

            if not local_to_remote:
                continue

            for ident in analysis["identifiers"]:
                remote = local_to_remote.get(ident["name"])
                if remote is None:
                    continue
                owner_path = visible.get(remote)
                if owner_path is None or owner_path == path:
                    continue
                key = (path, remote, ident["line"], ident["kind"])
                if key in seen:
                    continue
                seen.add(key)
                usages.append({
                    "path": path,
                    "identifier": remote,
                    "declared_in": owner_path,
                    "line": ident["line"],
                    "kind": ident["kind"],
                })

        return usages

    def _relationships(self, per_file, symbols):
        edges = []
        seen = set()
        declared_in = {
            symbol: {entry["path"] for entry in entries}
            for symbol, entries in symbols.items()
        }

        def add(source, target, relationship):
            if not source or not target or source == target:
                return
            key = (source, target, relationship)
            if key in seen:
                return
            seen.add(key)
            edges.append({
                "source": source,
                "target": target,
                "relationship": relationship,
            })

        for path, analysis in per_file.items():
            imported_paths = {
                item["resolved"]
                for item in analysis["imports"]
                if item["resolved"]
            }
            for item in analysis["imports"]:
                add(path, item["resolved"], "imports")

            for heritage in analysis["heritage"]:
                owners = declared_in.get(heritage["name"], set())
                reachable = owners & imported_paths
                if len(reachable) != 1:
                    continue
                add(path, next(iter(reachable)), heritage["relationship"])

        return edges

    def _disambiguate(self, declarations):
        if not declarations:
            return []
        collapsed = self._prefer_type_in_same_file(declarations)
        return self._prefer_product_over_test(collapsed)

    @staticmethod
    def _prefer_type_in_same_file(declarations):
        by_path = {}
        for entry in declarations:
            by_path.setdefault(entry["path"], []).append(entry)
        collapsed = []
        for entries in by_path.values():
            types = [entry for entry in entries if entry["kind"] in TYPE_KINDS]
            collapsed.extend(types if types else entries)
        return collapsed

    @staticmethod
    def _prefer_product_over_test(declarations):
        product = [
            entry
            for entry in declarations
            if not is_test_path(entry["path"])
        ]
        return product if product else declarations


def resolve_import(source_path, module, level, by_path):
    """
    Resolve a Python import to exactly one snapshot path.

    Stdlib/third-party names are declined. Multiple matching files
    are also declined.
    """

    if not source_path or not module:
        return None

    parts = module.split(".")
    stems = []

    if level:
        directory = posixpath.dirname(source_path)
        for _ in range(level - 1):
            parent = posixpath.dirname(directory)
            if parent == directory:
                return None
            directory = parent
        if directory and directory != ".":
            stems.append(posixpath.join(directory, *parts))
        else:
            stems.append("/".join(parts))
    else:
        stems.append("/".join(parts))
        directory = posixpath.dirname(source_path)
        while True:
            if directory and directory != ".":
                stems.append(posixpath.join(directory, *parts))
            else:
                stems.append("/".join(parts))
            if not directory or directory == ".":
                break
            parent = posixpath.dirname(directory)
            if parent == directory:
                break
            directory = parent

    found = []
    for stem in stems:
        for candidate in _module_files(stem):
            if candidate in by_path and candidate not in found:
                found.append(candidate)

    if len(found) == 1:
        return found[0]
    return None


def _module_files(stem):
    normalized = normalize_path(stem)
    if not normalized:
        return []
    return [
        normalized + ".py",
        normalize_path(posixpath.join(normalized, "__init__.py")),
    ]


def _parse(path, content):
    if not content or not content.strip():
        try:
            return ast.parse(content or "", filename=path)
        except (SyntaxError, ValueError):
            return None
    try:
        return ast.parse(content, filename=path)
    except (SyntaxError, ValueError):
        return None


def _header_end_line(tree):
    body = list(tree.body)
    if not body:
        return None
    index = 0
    if _is_docstring(body[0]):
        index = 1
    last = None
    for stmt in body[index:]:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            last = getattr(stmt, "end_lineno", None) or stmt.lineno
            continue
        break
    return last


def _is_docstring(stmt):
    if not isinstance(stmt, ast.Expr):
        return False
    value = stmt.value
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _binding_targets(stmt):
    """Simple Name bindings at this statement. Skip unpacking."""

    value = None
    names = []
    if isinstance(stmt, ast.AnnAssign):
        if isinstance(stmt.target, ast.Name):
            names.append(stmt.target.id)
        value = stmt.value
    elif isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            else:
                return []
        value = stmt.value
    kind = _value_kind(value, names)
    return [(name, kind) for name in names]


def _value_kind(value, names):
    if isinstance(value, ast.Lambda):
        return "function"
    if names and all(_is_constant_name(name) for name in names):
        return "constant"
    return "variable"


def _is_constant_name(name):
    letters = [ch for ch in name if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _simple_name(node):
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_dunder(name):
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def _is_identifier(name):
    return bool(name) and name.isidentifier()


def _collect_identifiers(tree):
    collector = _NameCollector()
    collector.visit(tree)
    return collector.identifiers


class _NameCollector(ast.NodeVisitor):
    """Load-context names, excluding attribute tails and definitions."""

    def __init__(self):
        self.identifiers = []

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)

    def visit_ClassDef(self, node):
        for child in node.bases:
            self.visit(child)
        for child in node.keywords:
            self.visit(child)
        for child in node.decorator_list:
            self.visit(child)
        for child in node.body:
            self.visit(child)

    def _visit_function(self, node):
        for child in node.decorator_list:
            self.visit(child)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        for child in node.body:
            self.visit(child)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self._add(node.func.id, node.func.lineno, "call")
        else:
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_Attribute(self, node):
        self.visit(node.value)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self._add(node.id, node.lineno, "reference")

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self._add(local, node.lineno, "import")

    def visit_Import(self, node):
        return

    def _add(self, name, line, kind):
        if not name or not line:
            return
        self.identifiers.append({
            "name": name,
            "line": line,
            "kind": kind,
        })
