"""
Tests for the Python CodeIntelligence adapter.

Contract first: unresolvable or ambiguous names are None, never a
guess. Coverage is structural — declarations, imports, references,
spans, and test-file conventions — not a type checker.
"""

from app.code_intelligence.adapters.javascript import JavaScriptCodeIntelligence
from app.code_intelligence.adapters.python import PythonCodeIntelligence
from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.protocol import CodeIntelligence, supports
from app.code_intelligence.registry import CodeIntelligenceRegistry
from app.code_intelligence.types import Location, Reference
from app.services.context_builder_service import ContextBuilderService
from app.services.context_budget import ContextBudget


def adapter():
    return PythonCodeIntelligence()


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


def test_adapter_claims_python_not_other_languages():
    intel = adapter()
    assert supports(intel, "app/main.py")
    assert supports(intel, "pkg/MOD.PY")
    assert not supports(intel, "src/app.ts")
    assert not supports(intel, "src/app.js")


def test_registry_selects_python_not_null():
    registry = CodeIntelligenceRegistry.default()
    chosen = registry.for_path("app/main.py")
    assert isinstance(chosen, PythonCodeIntelligence)
    assert chosen.has_intelligence is True
    assert not isinstance(chosen, NullCodeIntelligence)
    assert isinstance(registry.for_path("app/main.js"), JavaScriptCodeIntelligence)


# ============================================================
# DECLARATIONS
# ============================================================

def test_function_declaration():
    intel, index = _index([
        _file("pkg/users.py", "def get_user(user_id):\n    return user_id\n"),
    ])
    found = intel.declaration_of("get_user", index)
    assert found == Location(
        symbol="get_user",
        path="pkg/users.py",
        line=1,
        kind="function",
    )


def test_async_function_declaration():
    intel, index = _index([
        _file("pkg/users.py", "async def load_user(user_id):\n    return user_id\n"),
    ])
    found = intel.declaration_of("load_user", index)
    assert found is not None
    assert found.kind == "function"
    assert found.line == 1


def test_class_and_method_declaration():
    intel, index = _index([
        _file(
            "pkg/service.py",
            "class UserService:\n"
            "    async def get(self, user_id):\n"
            "        return user_id\n",
        ),
    ])
    assert intel.declaration_of("UserService", index).kind == "class"
    methods = [
        item for item in intel.declarations_in("pkg/service.py", index)
        if item.kind == "method"
    ]
    assert [item.symbol for item in methods] == ["get"]
    assert methods[0].line == 2


def test_module_constant():
    intel, index = _index([
        _file("pkg/constants.py", "LIMIT = 10\nconfig = {}\n"),
    ])
    assert intel.declaration_of("LIMIT", index).kind == "constant"
    assert intel.declaration_of("config", index).kind == "variable"


def test_nested_locals_are_not_declarations():
    intel, index = _index([
        _file(
            "pkg/outer.py",
            "def outer():\n"
            "    inner = 1\n"
            "    def nested():\n"
            "        return inner\n"
            "    return nested()\n",
        ),
    ])
    names = {item.symbol for item in intel.declarations_in("pkg/outer.py", index)}
    assert names == {"outer"}
    assert intel.declaration_of("inner", index) is None
    assert intel.declaration_of("nested", index) is None


def test_an_ambiguous_symbol_resolves_to_none():
    intel, index = _index([
        _file("pkg/a.py", "def dup():\n    return 1\n"),
        _file("pkg/b.py", "def dup():\n    return 2\n"),
    ])
    assert intel.declaration_of("dup", index) is None


def test_unknown_symbol_resolves_to_none():
    intel, index = _index([
        _file("pkg/a.py", "def foo():\n    return 1\n"),
    ])
    assert intel.declaration_of("nope", index) is None


# ============================================================
# IMPORTS / REFERENCES
# ============================================================

def test_imported_symbol_and_call_reference():
    files = [
        _file("pkg/module_a.py", "def foo():\n    return 1\n"),
        _file(
            "pkg/module_b.py",
            "from .module_a import foo\n"
            "\n"
            "def run():\n"
            "    return foo()\n",
        ),
    ]
    intel, index = _index(files)
    declaration = intel.declaration_of("foo", index)
    assert declaration.path == "pkg/module_a.py"

    references = intel.references_to("foo", index)
    assert all(isinstance(item, Reference) for item in references)
    assert {item.path for item in references} == {"pkg/module_b.py"}
    kinds = {item.kind for item in references}
    assert "import" in kinds
    assert "call" in kinds
    assert all(item.path != "pkg/module_a.py" for item in references)

    edges = intel.analyze_structure(files)
    assert {
        "source": "pkg/module_b.py",
        "target": "pkg/module_a.py",
        "relationship": "imports",
    } in edges


def test_import_alias_maps_to_the_declared_symbol():
    intel, index = _index([
        _file("pkg/module_a.py", "def foo():\n    return 1\n"),
        _file(
            "pkg/module_b.py",
            "from .module_a import foo as bar\n"
            "\n"
            "def run():\n"
            "    return bar()\n",
        ),
    ])
    references = intel.references_to("foo", index)
    assert any(item.kind == "call" and item.path == "pkg/module_b.py" for item in references)
    assert intel.references_to("bar", index) == []


def test_unresolved_package_import_is_not_an_edge():
    intel = adapter()
    edges = intel.analyze_structure([
        _file(
            "pkg/a.py",
            "import os\n"
            "from typing import List\n"
            "\n"
            "def names() -> List[str]:\n"
            "    return os.listdir('.')\n",
        ),
    ])
    assert edges == []


def test_attribute_access_is_not_a_call_reference():
    intel, index = _index([
        _file("pkg/a.py", "def find():\n    return 1\n"),
        _file(
            "pkg/b.py",
            "from .a import find\n"
            "\n"
            "def run(repo):\n"
            "    return repo.find()\n",
        ),
    ])
    kinds = [
        item.kind
        for item in intel.references_to("find", index)
        if item.path == "pkg/b.py"
    ]
    assert "import" in kinds
    assert "call" not in kinds


def test_inheritance_edge_when_base_is_imported():
    files = [
        _file("pkg/base.py", "class Base:\n    pass\n"),
        _file(
            "pkg/child.py",
            "from .base import Base\n"
            "\n"
            "class Child(Base):\n"
            "    pass\n",
        ),
    ]
    intel = adapter()
    edges = intel.analyze_structure(files)
    assert {
        "source": "pkg/child.py",
        "target": "pkg/base.py",
        "relationship": "extends",
    } in edges


# ============================================================
# SPANS / HEADER
# ============================================================

def test_enclosing_method_span_is_innermost():
    content = (
        "class UserService:\n"
        "    def get(self, user_id):\n"
        "        return user_id\n"
    )
    intel, index = _index([_file("pkg/service.py", content)])
    span = intel.enclosing_span("pkg/service.py", 3, index)
    assert span is not None
    assert span.symbol == "get"
    assert span.kind == "method"
    assert span.start_line == 2
    assert span.end_line == 3


def test_enclosing_span_for_unknown_file_is_none():
    intel, index = _index([
        _file("pkg/a.py", "def foo():\n    return 1\n"),
    ])
    assert intel.enclosing_span("pkg/missing.py", 1, index) is None


def test_header_end_line_is_the_last_leading_import():
    content = (
        "from .a import foo\n"
        "from .types import User\n"
        "\n"
        "def run():\n"
        "    return foo()\n"
    )
    intel, index = _index([_file("pkg/b.py", content)])
    assert intel.header_end_line("pkg/b.py", content, index) == 2


def test_header_end_line_is_none_without_imports():
    content = "def foo():\n    return 1\n"
    intel, index = _index([_file("pkg/a.py", content)])
    assert intel.header_end_line("pkg/a.py", content, index) is None


# ============================================================
# TESTS / SAFETY
# ============================================================

def test_test_file_detection():
    intel = adapter()
    assert intel.is_test_file("pkg/test_users.py")
    assert intel.is_test_file("pkg/users_test.py")
    assert intel.is_test_file("tests/users.py")
    assert intel.is_test_file("pkg/tests/users.py")
    assert intel.is_test_file("conftest.py")
    assert not intel.is_test_file("pkg/users.py")
    assert not intel.is_test_file("pkg/testing.py")
    assert not intel.is_test_file("pkg/contest.py")


def test_broken_syntax_does_not_invent_symbols():
    intel, index = _index([
        _file("pkg/bad.py", "def (:\n    not valid"),
    ])
    assert intel.declarations_in("pkg/bad.py", index) == []
    assert intel.declaration_of("not", index) is None
    assert intel.declaration_of("valid", index) is None
    assert intel.enclosing_span("pkg/bad.py", 1, index) is None


def test_star_import_does_not_invent_references():
    intel, index = _index([
        _file("pkg/a.py", "def foo():\n    return 1\n"),
        _file(
            "pkg/b.py",
            "from .a import *\n"
            "\n"
            "def run():\n"
            "    return foo()\n",
        ),
    ])
    assert intel.references_to("foo", index) == []


# ============================================================
# MULTI-FILE / CONTEXTBUILDER
# ============================================================

def test_module_b_imports_and_calls_module_a():
    files = [
        _file(
            "pkg/module_a.py",
            "def foo():\n"
            "    return 1\n",
        ),
        _file(
            "pkg/module_b.py",
            "from .module_a import foo\n"
            "\n"
            "def run():\n"
            "    return foo()\n",
        ),
    ]
    intel, index = _index(files)
    declaration = intel.declaration_of("foo", index)
    assert declaration.path == "pkg/module_a.py"
    assert declaration.kind == "function"

    references = intel.references_to("foo", index)
    assert {item.path for item in references} == {"pkg/module_b.py"}
    assert any(item.kind == "call" for item in references)

    edges = intel.analyze_structure(files)
    assert {
        "source": "pkg/module_b.py",
        "target": "pkg/module_a.py",
        "relationship": "imports",
    } in edges


def test_context_builder_labels_python_not_null():
    path = "pkg/module_a.py"
    content = "def foo():\n    return 1\n"
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
    assert pkg.language == "python"
    assert pkg.adapter == "PythonCodeIntelligence"
    assert pkg.slices[0].language == "python"
    assert pkg.slices[0].adapter == "PythonCodeIntelligence"
    assert pkg.slices[0].path == path
    assert "foo" in pkg.slices[0].content
