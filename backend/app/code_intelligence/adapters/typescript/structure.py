"""
TypeScript/TSX structural analysis over a tree-sitter AST.

Conservative on purpose. A missing edge costs ContextBuilder some
context; a guessed one sends a patch generator at the wrong file.
Nested locals, member accesses, path aliases, and ERROR subtrees
are declined rather than interpreted.
"""

from app.code_intelligence.adapters.typescript.parse import parse
from app.code_intelligence.tree_sitter_util import (
    end_line,
    first_child,
    is_identifier,
    node_text,
    normalize_path,
    resolve_relative_import,
    skip_error,
    start_line,
    string_literal,
)
from app.code_intelligence.types import Location, Span


TYPE_KINDS = frozenset({"class", "interface", "type", "enum"})

_TEST_SUFFIXES = (
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
    "_test.ts",
    "_test.tsx",
)
_TEST_DIR_PARTS = frozenset({
    "test",
    "tests",
    "__tests__",
    "__mocks__",
})


def is_typescript_path(path):
    lowered = normalize_path(path).lower()
    return lowered.endswith(".ts") or lowered.endswith(".tsx")


def is_test_path(path):
    lowered = normalize_path(path).lower()
    if not lowered:
        return False
    if any(lowered.endswith(suffix) for suffix in _TEST_SUFFIXES):
        return True
    parts = lowered.split("/")
    return any(part in _TEST_DIR_PARTS for part in parts)


class TypeScriptStructure:
    """Declarations, imports, references, and spans for one snapshot."""

    def analyze(self, files):
        ts_files = [
            file
            for file in files
            if is_typescript_path(file.get("path") or "")
        ]
        by_path = {
            normalize_path(file.get("path") or ""): file
            for file in ts_files
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
        root = parse(path, content)
        declarations = []
        imports = []
        spans = []
        identifiers = []
        header_end = None

        if root is None:
            return {
                "declarations": declarations,
                "imports": imports,
                "spans": spans,
                "identifiers": identifiers,
                "heritage": [],
                "header_end_line": header_end,
            }

        for child in skip_error(root.children):
            if child.type == "import_statement":
                recorded = self._import_from(child)
                if recorded is not None:
                    imports.append(recorded)
                    header_end = end_line(child)
                continue

            if child.type == "export_statement":
                source = string_literal(child.child_by_field_name("source"))
                if source is not None:
                    imports.append({
                        "specifier": source,
                        "names": self._export_names(child),
                        "namespace": None,
                        "default": None,
                        "resolved": None,
                    })
                    header_end = end_line(child)
                self._collect_statement(
                    child, path, declarations, spans, module_level=True,
                )
                continue

            self._collect_statement(
                child, path, declarations, spans, module_level=True,
            )

        self._collect_identifiers(root, identifiers)

        return {
            "declarations": declarations,
            "imports": imports,
            "spans": spans,
            "identifiers": identifiers,
            "heritage": self._collect_heritage(root),
            "header_end_line": header_end,
        }

    def _collect_statement(self, node, path, declarations, spans, *, module_level):
        if node.type == "ERROR":
            return

        if node.type == "export_statement":
            for child in skip_error(node.children):
                if child.type in {"export", "default", "export_clause", "string"}:
                    continue
                if child.type == "from":
                    continue
                self._collect_statement(
                    child, path, declarations, spans, module_level=module_level,
                )
            return

        handler = _DECLARATION_HANDLERS.get(node.type)
        if handler is not None:
            handler(self, node, path, declarations, spans, module_level)
            return

        if module_level and node.type in {
            "lexical_declaration",
            "variable_declaration",
        }:
            self._collect_variables(node, path, declarations, spans)

    def _record(
        self,
        path,
        node,
        symbol,
        kind,
        declarations,
        spans,
        *,
        line=None,
    ):
        if not symbol or not is_identifier(symbol):
            return
        start = start_line(node)
        item_line = line if line is not None else start
        declarations.append({
            "symbol": symbol,
            "line": item_line,
            "kind": kind,
        })
        spans.append(
            Span(
                path=path,
                start_line=start,
                end_line=end_line(node),
                kind=kind,
                symbol=symbol,
            )
        )

    def _collect_function(self, node, path, declarations, spans, module_level):
        if not module_level:
            return
        name = node.child_by_field_name("name")
        self._record(path, node, node_text(name), "function", declarations, spans)

    def _collect_class(self, node, path, declarations, spans, module_level):
        if not module_level:
            return
        name = node.child_by_field_name("name")
        symbol = node_text(name)
        self._record(path, node, symbol, "class", declarations, spans)
        body = node.child_by_field_name("body")
        if body is None:
            body = first_child(node, "class_body")
        if body is not None:
            self._collect_members(body, path, declarations, spans)

    def _collect_interface(self, node, path, declarations, spans, module_level):
        if not module_level:
            return
        name = node.child_by_field_name("name")
        self._record(
            path, node, node_text(name), "interface", declarations, spans,
        )
        body = first_child(node, "interface_body") or first_child(
            node, "object_type",
        )
        if body is not None:
            self._collect_members(body, path, declarations, spans)

    def _collect_type_alias(self, node, path, declarations, spans, module_level):
        if not module_level:
            return
        name = node.child_by_field_name("name")
        self._record(path, node, node_text(name), "type", declarations, spans)

    def _collect_enum(self, node, path, declarations, spans, module_level):
        if not module_level:
            return
        name = node.child_by_field_name("name")
        self._record(path, node, node_text(name), "enum", declarations, spans)

    def _collect_members(self, body, path, declarations, spans):
        for child in skip_error(body.children):
            if child.type in {"method_definition", "method_signature",
                              "abstract_method_signature"}:
                name = child.child_by_field_name("name")
                self._record(
                    path, child, node_text(name), "method", declarations, spans,
                )
            elif child.type == "public_field_definition":
                name = child.child_by_field_name("name")
                if name is None:
                    name = first_child(child, "property_identifier")
                self._record(
                    path, child, node_text(name), "field", declarations, spans,
                )

    def _collect_variables(self, node, path, declarations, spans):
        keyword = None
        for child in node.children:
            if child.type in {"const", "let", "var"}:
                keyword = child.type
                break

        for child in skip_error(node.children):
            if child.type != "variable_declarator":
                continue
            name = child.child_by_field_name("name")
            if name is None or name.type != "identifier":
                continue
            value = child.child_by_field_name("value")
            if value is not None and value.type in {
                "arrow_function",
                "function_expression",
                "function",
                "generator_function",
            }:
                kind = "function"
            elif keyword == "const":
                kind = "constant"
            else:
                kind = "variable"
            self._record(
                path, child, node_text(name), kind, declarations, spans,
            )

    def _import_from(self, node):
        source = string_literal(node.child_by_field_name("source"))
        if not source:
            return None
        names = []
        namespace = None
        default = None
        clause = first_child(node, "import_clause")
        if clause is not None:
            for child in skip_error(clause.children):
                if child.type == "identifier":
                    default = node_text(child)
                elif child.type == "namespace_import":
                    ident = first_child(child, "identifier")
                    namespace = node_text(ident) if ident else None
                elif child.type == "named_imports":
                    for specifier in child.children:
                        if specifier.type != "import_specifier":
                            continue
                        imported = specifier.child_by_field_name("name")
                        alias = specifier.child_by_field_name("alias")
                        if imported is None:
                            continue
                        names.append({
                            "name": node_text(imported),
                            "alias": node_text(alias) if alias else None,
                        })
        return {
            "specifier": source,
            "names": names,
            "namespace": namespace,
            "default": default,
            "resolved": None,
        }

    def _export_names(self, node):
        names = []
        clause = first_child(node, "export_clause")
        if clause is None:
            return names
        for child in clause.children:
            if child.type != "export_specifier":
                continue
            imported = child.child_by_field_name("name")
            if imported is None:
                imported = first_child(child, "identifier")
            if imported is not None:
                names.append({
                    "name": node_text(imported),
                    "alias": None,
                })
        return names

    def _collect_heritage(self, root):
        found = []
        stack = list(skip_error(root.children))
        while stack:
            node = stack.pop()
            if node.type == "ERROR":
                continue
            if node.type == "class_heritage":
                found.extend(
                    self._names_from_clause(
                        first_child(node, "extends_clause"),
                        "extends",
                    )
                )
                found.extend(
                    self._names_from_clause(
                        first_child(node, "implements_clause"),
                        "implements",
                    )
                )
            elif node.type == "extends_type_clause":
                found.extend(self._names_from_clause(node, "extends"))
            stack.extend(skip_error(node.children))
        return found

    def _names_from_clause(self, clause, relationship):
        if clause is None:
            return []
        names = []
        for child in skip_error(clause.children):
            name = _simple_type_name(child)
            if name:
                names.append({
                    "relationship": relationship,
                    "name": name,
                })
        return names

    def _collect_identifiers(self, root, identifiers):
        stack = list(skip_error(root.children))
        while stack:
            node = stack.pop()
            if node.type == "ERROR":
                continue
            if node.type in {"identifier", "type_identifier"}:
                kind = _identifier_kind(node)
                if kind is not None:
                    identifiers.append({
                        "name": node_text(node),
                        "line": start_line(node),
                        "kind": kind,
                    })
            stack.extend(skip_error(list(node.children)))

    # =========================================================
    # REPOSITORY
    # =========================================================

    def _resolve_imports(self, per_file, by_path):
        for path, analysis in per_file.items():
            for item in analysis["imports"]:
                item["resolved"] = resolve_import(
                    path, item["specifier"], by_path,
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
            for symbol, owners in declared_in.items():
                if path in owners:
                    continue
                reachable = owners & imported_paths
                if len(reachable) != 1:
                    continue
                visible[symbol] = next(iter(reachable))

            local_to_remote = {symbol: symbol for symbol in visible}
            for item in analysis["imports"]:
                target = item["resolved"]
                if not target:
                    continue
                for spec in item["names"]:
                    remote = spec["name"]
                    local = spec["alias"] or spec["name"]
                    if visible.get(remote) == target:
                        local_to_remote[local] = remote
                default = item["default"]
                if default and visible.get(default) == target:
                    local_to_remote[default] = default

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


def resolve_import(source_path, specifier, by_path):
    """
    Resolve a relative import to exactly one snapshot path.

    Package specifiers and path aliases are declined. If more than
    one candidate exists, so is the import. A `.js` specifier may
    still resolve to a `.ts` / `.tsx` file.
    """

    return resolve_relative_import(
        source_path,
        specifier,
        by_path,
        (".ts", ".tsx"),
        map_javascript_specifiers=True,
    )


def _simple_type_name(node):
    if node.type in {"identifier", "type_identifier"}:
        return node_text(node)
    if node.type == "generic_type":
        name = (
            node.child_by_field_name("name")
            or first_child(node, "type_identifier")
            or first_child(node, "identifier")
        )
        return node_text(name) if name else None
    return None


def _identifier_kind(node):
    parent = node.parent
    if parent is None:
        return "reference"
    if parent.type in {
        "member_expression",
        "property_signature",
        "public_field_definition",
        "enum_body",
        "pair",
    }:
        return None
    if parent.type in {"jsx_opening_element", "jsx_self_closing_element"}:
        if node_text(node)[:1].isupper():
            return "jsx"
        return None
    if parent.type == "call_expression":
        function = parent.child_by_field_name("function")
        if function == node:
            return "call"
    if parent.type == "import_specifier":
        return "import"
    if parent.type in {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "method_definition",
        "method_signature",
        "variable_declarator",
    }:
        name = parent.child_by_field_name("name")
        if name == node:
            return None
    return "reference"


_DECLARATION_HANDLERS = {
    "function_declaration": TypeScriptStructure._collect_function,
    "generator_function_declaration": TypeScriptStructure._collect_function,
    "class_declaration": TypeScriptStructure._collect_class,
    "abstract_class_declaration": TypeScriptStructure._collect_class,
    "interface_declaration": TypeScriptStructure._collect_interface,
    "type_alias_declaration": TypeScriptStructure._collect_type_alias,
    "enum_declaration": TypeScriptStructure._collect_enum,
}
