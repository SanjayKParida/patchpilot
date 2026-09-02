"""
Tests for the JavaScript CodeIntelligence adapter.

Contract first: unresolvable or ambiguous names are None, never a
guess. Coverage is structural — declarations, ESM imports, JSX
references, and test-file conventions — not a type checker.
"""

from app.code_intelligence.adapters.javascript import JavaScriptCodeIntelligence
from app.code_intelligence.adapters.typescript import TypeScriptCodeIntelligence
from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.protocol import CodeIntelligence, supports
from app.code_intelligence.registry import CodeIntelligenceRegistry
from app.code_intelligence.types import Location, Reference
from app.services.context_builder_service import ContextBuilderService
from app.services.context_budget import ContextBudget


def adapter():
    return JavaScriptCodeIntelligence()


def _file(path, content):
    return {"path": path, "sha": path, "content": content}


def _index(files, intel=None):
    intel = intel or adapter()
    return intel, intel.build_index(files)


# ============================================================
# PROTOCOL / REGISTRY
# ============================================================

def test_adapter_satisfies_the_protocol():
    assert isinstance(adapter(), CodeIntelligence)


def test_adapter_claims_javascript_not_typescript():
    intel = adapter()
    assert supports(intel, "src/app.js")
    assert supports(intel, "src/APP.JSX")
    assert not supports(intel, "src/app.ts")
    assert not supports(intel, "src/app.py")


def test_registry_selects_javascript_not_null_or_typescript():
    registry = CodeIntelligenceRegistry.default()
    chosen = registry.for_path("src/app.js")
    assert isinstance(chosen, JavaScriptCodeIntelligence)
    assert chosen.has_intelligence is True
    assert not isinstance(chosen, NullCodeIntelligence)
    assert isinstance(registry.for_path("src/app.jsx"), JavaScriptCodeIntelligence)
    assert isinstance(registry.for_path("src/app.ts"), TypeScriptCodeIntelligence)


# ============================================================
# DECLARATIONS
# ============================================================

def test_function_declaration():
    intel, index = _index([
        _file("src/users.js", "export function getUser(id) {\n  return id;\n}\n"),
    ])
    found = intel.declaration_of("getUser", index)
    assert found == Location(
        symbol="getUser",
        path="src/users.js",
        line=1,
        kind="function",
    )


def test_async_function_declaration():
    intel, index = _index([
        _file("src/users.js", "export async function loadUser(id) {\n  return id;\n}\n"),
    ])
    found = intel.declaration_of("loadUser", index)
    assert found is not None
    assert found.kind == "function"
    assert found.line == 1


def test_class_and_method_declaration():
    intel, index = _index([
        _file(
            "src/service.js",
            "export class UserService {\n"
            "  async get(id) {\n"
            "    return id;\n"
            "  }\n"
            "}\n",
        ),
    ])
    assert intel.declaration_of("UserService", index).kind == "class"
    methods = [
        item for item in intel.declarations_in("src/service.js", index)
        if item.kind == "method"
    ]
    assert [item.symbol for item in methods] == ["get"]
    assert methods[0].line == 2


def test_exported_constant():
    intel, index = _index([
        _file("src/constants.js", "export const LIMIT = 10;\n"),
    ])
    assert intel.declaration_of("LIMIT", index).kind == "constant"


def test_nested_locals_are_not_declarations():
    intel, index = _index([
        _file(
            "src/outer.js",
            "export function outer() {\n"
            "  const inner = 1;\n"
            "  function nested() { return inner; }\n"
            "  return nested();\n"
            "}\n",
        ),
    ])
    names = {item.symbol for item in intel.declarations_in("src/outer.js", index)}
    assert names == {"outer"}
    assert intel.declaration_of("inner", index) is None
    assert intel.declaration_of("nested", index) is None


def test_an_ambiguous_symbol_resolves_to_none():
    intel, index = _index([
        _file("src/a.js", "export function dup() { return 1; }\n"),
        _file("src/b.js", "export function dup() { return 2; }\n"),
    ])
    assert intel.declaration_of("dup", index) is None


def test_unknown_symbol_resolves_to_none():
    intel, index = _index([
        _file("src/a.js", "export function foo() { return 1; }\n"),
    ])
    assert intel.declaration_of("nope", index) is None


# ============================================================
# IMPORTS / REFERENCES
# ============================================================

def test_imported_symbol_and_call_reference():
    files = [
        _file("src/module_a.js", "export function foo() {\n  return 1;\n}\n"),
        _file(
            "src/module_b.js",
            "import { foo } from \"./module_a.js\";\n"
            "export function run() {\n"
            "  return foo();\n"
            "}\n",
        ),
    ]
    intel, index = _index(files)
    declaration = intel.declaration_of("foo", index)
    assert declaration.path == "src/module_a.js"

    references = intel.references_to("foo", index)
    assert all(isinstance(item, Reference) for item in references)
    assert {item.path for item in references} == {"src/module_b.js"}
    kinds = {item.kind for item in references}
    assert "import" in kinds
    assert "call" in kinds
    assert all(item.path != "src/module_a.js" for item in references)

    edges = intel.analyze_structure(files)
    assert {
        "source": "src/module_b.js",
        "target": "src/module_a.js",
        "relationship": "imports",
    } in edges


def test_import_alias_maps_to_the_declared_symbol():
    intel, index = _index([
        _file("src/a.js", "export function foo() {\n  return 1;\n}\n"),
        _file(
            "src/b.js",
            "import { foo as bar } from \"./a.js\";\n"
            "export function run() {\n"
            "  return bar();\n"
            "}\n",
        ),
    ])
    references = intel.references_to("foo", index)
    assert any(item.kind == "call" and item.path == "src/b.js" for item in references)
    assert intel.references_to("bar", index) == []


def test_unresolved_package_import_is_not_an_edge():
    intel = adapter()
    edges = intel.analyze_structure([
        _file(
            "src/a.js",
            "import express from \"express\";\n"
            "export const app = express();\n",
        ),
    ])
    assert edges == []


def test_member_access_is_not_a_reference_to_the_property_name():
    intel, index = _index([
        _file("src/a.js", "export function find() {\n  return 1;\n}\n"),
        _file(
            "src/b.js",
            "import { find } from \"./a.js\";\n"
            "export function run(repo) {\n"
            "  return repo.find();\n"
            "}\n",
        ),
    ])
    kinds = [
        item.kind
        for item in intel.references_to("find", index)
        if item.path == "src/b.js"
    ]
    assert "import" in kinds
    assert "call" not in kinds


# ============================================================
# SPANS / HEADER
# ============================================================

def test_enclosing_method_span_is_innermost():
    content = (
        "export class UserService {\n"
        "  async get(id) {\n"
        "    return id;\n"
        "  }\n"
        "}\n"
    )
    intel, index = _index([_file("src/service.js", content)])
    span = intel.enclosing_span("src/service.js", 3, index)
    assert span is not None
    assert span.symbol == "get"
    assert span.kind == "method"
    assert span.start_line == 2
    assert span.end_line == 4


def test_enclosing_span_for_unknown_file_is_none():
    intel, index = _index([
        _file("src/a.js", "export function foo() { return 1; }\n"),
    ])
    assert intel.enclosing_span("src/missing.js", 1, index) is None


def test_header_end_line_is_the_last_import():
    content = (
        "import { foo } from \"./a.js\";\n"
        "import { bar } from \"./b.js\";\n"
        "\n"
        "export function run() {\n"
        "  return foo();\n"
        "}\n"
    )
    intel, index = _index([_file("src/c.js", content)])
    assert intel.header_end_line("src/c.js", content, index) == 2


def test_header_end_line_is_none_without_imports():
    content = "export function foo() {\n  return 1;\n}\n"
    intel, index = _index([_file("src/a.js", content)])
    assert intel.header_end_line("src/a.js", content, index) is None


# ============================================================
# JSX / TESTS / SAFETY
# ============================================================

def test_jsx_component_reference():
    files = [
        _file(
            "src/Button.jsx",
            "export function Button(props) {\n"
            "  return <button>{props.label}</button>;\n"
            "}\n",
        ),
        _file(
            "src/App.jsx",
            "import { Button } from \"./Button.jsx\";\n"
            "export function App() {\n"
            "  return <div><Button label=\"Go\" /></div>;\n"
            "}\n",
        ),
    ]
    intel, index = _index(files)
    assert intel.declaration_of("Button", index).path == "src/Button.jsx"
    assert intel.declaration_of("App", index).kind == "function"
    references = intel.references_to("Button", index)
    assert any(item.kind == "jsx" and item.path == "src/App.jsx" for item in references)
    names = {item.symbol for item in intel.declarations_in("src/App.jsx", index)}
    assert "div" not in names
    assert "button" not in names
    assert intel.declaration_of("div", index) is None


def test_test_file_detection():
    intel = adapter()
    assert intel.is_test_file("src/users.test.js")
    assert intel.is_test_file("src/users.test.jsx")
    assert intel.is_test_file("src/users.spec.js")
    assert intel.is_test_file("src/users_test.js")
    assert intel.is_test_file("src/__tests__/users.js")
    assert intel.is_test_file("tests/users.js")
    assert not intel.is_test_file("src/users.js")
    assert not intel.is_test_file("src/testing.js")
    assert not intel.is_test_file("src/contest.js")


def test_broken_syntax_does_not_invent_symbols():
    intel, index = _index([
        _file("src/bad.js", "function ( {{{{ not valid"),
    ])
    assert intel.declarations_in("src/bad.js", index) == []
    assert intel.declaration_of("not", index) is None
    assert intel.declaration_of("valid", index) is None
    assert intel.enclosing_span("src/bad.js", 1, index) is None


def test_path_alias_is_not_resolved():
    intel = adapter()
    edges = intel.analyze_structure([
        _file("src/a.js", "export function foo() { return 1; }\n"),
        _file("src/b.js", "import { foo } from \"@/a\";\n"),
    ])
    assert edges == []
    _, index = _index([
        _file("src/a.js", "export function foo() { return 1; }\n"),
        _file("src/b.js", "import { foo } from \"@/a\";\n"),
    ], intel)
    assert intel.references_to("foo", index) == []


# ============================================================
# MULTI-FILE / CONTEXTBUILDER
# ============================================================

def test_module_b_imports_and_calls_module_a():
    files = [
        _file(
            "src/module_a.js",
            "export function foo() {\n"
            "  return 1;\n"
            "}\n",
        ),
        _file(
            "src/module_b.js",
            "import { foo } from \"./module_a.js\";\n"
            "\n"
            "export function run() {\n"
            "  return foo();\n"
            "}\n",
        ),
    ]
    intel, index = _index(files)
    declaration = intel.declaration_of("foo", index)
    assert declaration.path == "src/module_a.js"
    assert declaration.kind == "function"

    references = intel.references_to("foo", index)
    assert {item.path for item in references} == {"src/module_b.js"}
    assert any(item.kind == "import" for item in references)
    assert any(item.kind == "call" for item in references)

    edges = intel.analyze_structure(files)
    assert {
        "source": "src/module_b.js",
        "target": "src/module_a.js",
        "relationship": "imports",
    } in edges


def test_context_builder_labels_javascript_not_null():
    path = "src/module_a.js"
    content = "export function foo() {\n  return 1;\n}\n"
    service = ContextBuilderService(CodeIntelligenceRegistry.default())
    pkg = service.build(
        diagnosis={
            "root_cause_locations": [
                {
                    "symbol": "foo",
                    "path": path,
                    "line": 1,
                    "kind": "function",
                }
            ],
        },
        ranked=[{"path": path, "rank": 1, "total_score": 9}],
        files=[{"path": path, "content": content}],
        budget=ContextBudget(pad_lines=0, whole_file_fraction=1.01),
    )

    assert pkg.slices
    assert pkg.language == "javascript"
    assert pkg.adapter == "JavaScriptCodeIntelligence"
    assert pkg.slices[0].language == "javascript"
    assert pkg.slices[0].adapter == "JavaScriptCodeIntelligence"
    assert pkg.slices[0].path == path
    assert "foo" in pkg.slices[0].content
