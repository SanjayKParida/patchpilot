"""
Tests for the TypeScript CodeIntelligence adapter.

Contract first: unresolvable or ambiguous names are None, never a
guess. Coverage is structural — declarations, imports, references,
spans, TSX, and test-file conventions — not a TypeScript type checker.
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
    return TypeScriptCodeIntelligence()


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


def test_adapter_claims_typescript_not_javascript():
    intel = adapter()
    assert supports(intel, "src/app.ts")
    assert supports(intel, "src/APP.TSX")
    assert not supports(intel, "src/app.js")
    assert not supports(intel, "src/app.py")


def test_registry_selects_typescript_not_null():
    registry = CodeIntelligenceRegistry.default()
    chosen = registry.for_path("backend/src/server.ts")
    assert isinstance(chosen, TypeScriptCodeIntelligence)
    assert chosen.has_intelligence is True
    assert not isinstance(chosen, NullCodeIntelligence)
    assert isinstance(registry.for_path("backend/src/server.js"), JavaScriptCodeIntelligence)


# ============================================================
# DECLARATIONS
# ============================================================

def test_function_declaration():
    intel, index = _index([
        _file("src/users.ts", "export function getUser(id: string) {\n  return id;\n}\n"),
    ])
    found = intel.declaration_of("getUser", index)
    assert found == Location(
        symbol="getUser",
        path="src/users.ts",
        line=1,
        kind="function",
    )


def test_class_and_method_declaration():
    intel, index = _index([
        _file(
            "src/service.ts",
            "export class UserService {\n"
            "  async get(id: string) {\n"
            "    return id;\n"
            "  }\n"
            "}\n",
        ),
    ])
    assert intel.declaration_of("UserService", index).kind == "class"
    methods = [
        item for item in intel.declarations_in("src/service.ts", index)
        if item.kind == "method"
    ]
    assert [item.symbol for item in methods] == ["get"]
    assert methods[0].line == 2


def test_interface_and_type_alias():
    intel, index = _index([
        _file(
            "src/types.ts",
            "export interface User { id: string }\n"
            "export type UserId = string;\n",
        ),
    ])
    assert intel.declaration_of("User", index).kind == "interface"
    assert intel.declaration_of("UserId", index).kind == "type"


def test_enum_and_exported_constant():
    intel, index = _index([
        _file(
            "src/constants.ts",
            "export enum Role { Admin, User }\n"
            "export const LIMIT = 10;\n",
        ),
    ])
    assert intel.declaration_of("Role", index).kind == "enum"
    assert intel.declaration_of("LIMIT", index).kind == "constant"


def test_arrow_function_constant_is_a_function():
    intel, index = _index([
        _file("src/load.ts", "export const load = async () => 1;\n"),
    ])
    assert intel.declaration_of("load", index).kind == "function"


def test_nested_locals_are_not_declarations():
    intel, index = _index([
        _file(
            "src/outer.ts",
            "export function outer() {\n"
            "  const inner = 1;\n"
            "  function nested() { return inner; }\n"
            "  return nested();\n"
            "}\n",
        ),
    ])
    names = {item.symbol for item in intel.declarations_in("src/outer.ts", index)}
    assert names == {"outer"}
    assert intel.declaration_of("inner", index) is None
    assert intel.declaration_of("nested", index) is None


def test_an_ambiguous_symbol_resolves_to_none():
    intel, index = _index([
        _file("src/a.ts", "export function dup() { return 1; }\n"),
        _file("src/b.ts", "export function dup() { return 2; }\n"),
    ])
    assert intel.declaration_of("dup", index) is None


def test_unknown_symbol_resolves_to_none():
    intel, index = _index([
        _file("src/a.ts", "export function foo() { return 1; }\n"),
    ])
    assert intel.declaration_of("nope", index) is None


# ============================================================
# IMPORTS / REFERENCES
# ============================================================

def test_imported_symbol_and_call_reference():
    intel, index = _index([
        _file("src/a.ts", "export function foo() {\n  return 1;\n}\n"),
        _file(
            "src/b.ts",
            "import { foo } from \"./a\";\n"
            "export function run() {\n"
            "  return foo();\n"
            "}\n",
        ),
    ])
    declaration = intel.declaration_of("foo", index)
    assert declaration.path == "src/a.ts"

    references = intel.references_to("foo", index)
    assert all(isinstance(item, Reference) for item in references)
    assert {item.path for item in references} == {"src/b.ts"}
    kinds = {item.kind for item in references}
    assert "import" in kinds
    assert "call" in kinds
    assert all(item.path != "src/a.ts" for item in references)

    edges = intel.analyze_structure([
        _file("src/a.ts", "export function foo() {\n  return 1;\n}\n"),
        _file(
            "src/b.ts",
            "import { foo } from \"./a\";\n"
            "export function run() {\n"
            "  return foo();\n"
            "}\n",
        ),
    ])
    assert {
        "source": "src/b.ts",
        "target": "src/a.ts",
        "relationship": "imports",
    } in edges


def test_import_alias_maps_to_the_declared_symbol():
    intel, index = _index([
        _file("src/a.ts", "export function foo() {\n  return 1;\n}\n"),
        _file(
            "src/b.ts",
            "import { foo as bar } from \"./a\";\n"
            "export function run() {\n"
            "  return bar();\n"
            "}\n",
        ),
    ])
    references = intel.references_to("foo", index)
    assert any(item.kind == "call" and item.path == "src/b.ts" for item in references)
    assert intel.references_to("bar", index) == []


def test_unresolved_package_import_is_not_an_edge():
    intel = adapter()
    edges = intel.analyze_structure([
        _file(
            "src/a.ts",
            "import express from \"express\";\n"
            "export const app = express();\n",
        ),
    ])
    assert edges == []


def test_member_access_is_not_a_reference_to_the_property_name():
    intel, index = _index([
        _file("src/a.ts", "export function find() {\n  return 1;\n}\n"),
        _file(
            "src/b.ts",
            "import { find } from \"./a\";\n"
            "export function run(repo: { find: () => number }) {\n"
            "  return repo.find();\n"
            "}\n",
        ),
    ])
    # The import still counts. repo.find must not add a call/reference
    # on the property name beyond that conservative import.
    kinds = [
        item.kind
        for item in intel.references_to("find", index)
        if item.path == "src/b.ts"
    ]
    assert "import" in kinds
    assert "call" not in kinds


# ============================================================
# SPANS / HEADER
# ============================================================

def test_enclosing_method_span_is_innermost():
    content = (
        "export class UserService {\n"
        "  async get(id: string) {\n"
        "    return id;\n"
        "  }\n"
        "}\n"
    )
    intel, index = _index([_file("src/service.ts", content)])
    span = intel.enclosing_span("src/service.ts", 3, index)
    assert span is not None
    assert span.symbol == "get"
    assert span.kind == "method"
    assert span.start_line == 2
    assert span.end_line == 4


def test_enclosing_span_for_unknown_file_is_none():
    intel, index = _index([
        _file("src/a.ts", "export function foo() { return 1; }\n"),
    ])
    assert intel.enclosing_span("src/missing.ts", 1, index) is None


def test_header_end_line_is_the_last_import():
    content = (
        "import { foo } from \"./a\";\n"
        "import type { User } from \"./types\";\n"
        "\n"
        "export function run() {\n"
        "  return foo();\n"
        "}\n"
    )
    intel, index = _index([_file("src/b.ts", content)])
    assert intel.header_end_line("src/b.ts", content, index) == 2


def test_header_end_line_is_none_without_imports():
    content = "export function foo() {\n  return 1;\n}\n"
    intel, index = _index([_file("src/a.ts", content)])
    assert intel.header_end_line("src/a.ts", content, index) is None


# ============================================================
# TSX / TESTS / SAFETY
# ============================================================

def test_tsx_function_and_component_reference():
    files = [
        _file(
            "src/Title.tsx",
            "export function Title(props: { text: string }) {\n"
            "  return <h1>{props.text}</h1>;\n"
            "}\n",
        ),
        _file(
            "src/Card.tsx",
            "import { Title } from \"./Title\";\n"
            "export function Card(props: { title: string }) {\n"
            "  return <div><Title text={props.title} /></div>;\n"
            "}\n",
        ),
    ]
    intel, index = _index(files)
    assert intel.declaration_of("Card", index).kind == "function"
    assert intel.declaration_of("Title", index).path == "src/Title.tsx"
    references = intel.references_to("Title", index)
    assert any(item.kind == "jsx" and item.path == "src/Card.tsx" for item in references)
    names = {item.symbol for item in intel.declarations_in("src/Card.tsx", index)}
    assert "div" not in names
    assert intel.declaration_of("div", index) is None


def test_test_file_detection():
    intel = adapter()
    assert intel.is_test_file("src/users.test.ts")
    assert intel.is_test_file("src/users.spec.tsx")
    assert intel.is_test_file("src/__tests__/users.ts")
    assert intel.is_test_file("backend/tests/users.ts")
    assert not intel.is_test_file("src/users.ts")
    assert not intel.is_test_file("src/testing.ts")
    assert not intel.is_test_file("src/contest.ts")


def test_broken_syntax_does_not_invent_symbols():
    intel, index = _index([
        _file("src/bad.ts", "function ( {{{{ not valid"),
    ])
    assert intel.declarations_in("src/bad.ts", index) == []
    assert intel.declaration_of("not", index) is None
    assert intel.declaration_of("valid", index) is None
    assert intel.enclosing_span("src/bad.ts", 1, index) is None


def test_path_alias_is_not_resolved():
    intel = adapter()
    edges = intel.analyze_structure([
        _file("src/a.ts", "export function foo() { return 1; }\n"),
        _file("src/b.ts", "import { foo } from \"@/a\";\n"),
    ])
    assert edges == []
    _, index = _index([
        _file("src/a.ts", "export function foo() { return 1; }\n"),
        _file("src/b.ts", "import { foo } from \"@/a\";\n"),
    ], intel)
    assert intel.references_to("foo", index) == []


# ============================================================
# MULTI-FILE / CONTEXTBUILDER
# ============================================================

def test_circle_marketplace_style_controller_imports_service():
    files = [
        _file(
            "backend/src/users/userService.ts",
            "export function getUser(id: string) {\n"
            "  return { id, name: \"Ada\" };\n"
            "}\n",
        ),
        _file(
            "backend/src/users/userController.ts",
            "import { getUser } from \"./userService\";\n"
            "\n"
            "export function showUser(id: string) {\n"
            "  return getUser(id);\n"
            "}\n",
        ),
    ]
    intel, index = _index(files)
    declaration = intel.declaration_of("getUser", index)
    assert declaration.path == "backend/src/users/userService.ts"
    assert declaration.kind == "function"

    references = intel.references_to("getUser", index)
    assert {item.path for item in references} == {
        "backend/src/users/userController.ts",
    }
    assert any(item.kind == "call" for item in references)

    edges = intel.analyze_structure(files)
    assert {
        "source": "backend/src/users/userController.ts",
        "target": "backend/src/users/userService.ts",
        "relationship": "imports",
    } in edges


def test_context_builder_labels_typescript_not_null():
    path = "backend/src/users/userService.ts"
    content = (
        "export function getUser(id: string) {\n"
        "  return { id };\n"
        "}\n"
    )
    service = ContextBuilderService(CodeIntelligenceRegistry.default())
    pkg = service.build(
        diagnosis={
            "root_cause_locations": [
                {
                    "symbol": "getUser",
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
    assert pkg.language == "typescript"
    assert pkg.adapter == "TypeScriptCodeIntelligence"
    assert pkg.slices[0].language == "typescript"
    assert pkg.slices[0].adapter == "TypeScriptCodeIntelligence"
    assert pkg.slices[0].path == path
    assert "getUser" in pkg.slices[0].content
