"""
Registry and null adapter: per-file language selection.

The core stays language-free. These tests are allowed to mention Dart
because they are about which adapter is chosen, not about how the
builder ranks or slices.
"""

import inspect
import json
from pathlib import Path

from app.code_intelligence.adapters.dart import DartCodeIntelligence
from app.code_intelligence.adapters.javascript import JavaScriptCodeIntelligence
from app.code_intelligence.adapters.python import PythonCodeIntelligence
from app.code_intelligence.adapters.typescript import TypeScriptCodeIntelligence
from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.protocol import CodeIntelligence, supports
from app.code_intelligence.registry import CodeIntelligenceRegistry
from app.services.analysis_runner import AnalysisRunner
from app.services.context_builder_service import ContextBuilderService
from app.services.context_budget import ContextBudget


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "fixtures"
    / "car_rental_app.json"
)


def registry():
    return CodeIntelligenceRegistry.default()


def numbered(path, n):
    return {
        "path": path,
        "content": "\n".join(f"line {i}" for i in range(1, n + 1)),
    }


# ============================================================
# SELECTION
# ============================================================

def test_null_adapter_satisfies_the_protocol():
    assert isinstance(NullCodeIntelligence(), CodeIntelligence)


def test_registry_satisfies_the_protocol():
    assert isinstance(registry(), CodeIntelligence)


def test_dart_file_selects_the_dart_adapter():
    chosen = registry().for_path("lib/presentation/bloc/task_bloc.dart")
    assert isinstance(chosen, DartCodeIntelligence)
    assert chosen.name == "dart"


def test_unsupported_extension_selects_the_null_adapter():
    chosen = registry().for_path("app/main.rb")
    assert isinstance(chosen, NullCodeIntelligence)
    assert chosen.name == "unknown"


def test_unknown_extension_selects_the_null_adapter():
    intel = registry()
    assert isinstance(intel.for_path("notes.txt"), NullCodeIntelligence)
    assert isinstance(intel.for_path("Makefile"), NullCodeIntelligence)
    assert isinstance(intel.for_path("README"), NullCodeIntelligence)


def test_mixed_language_files_select_adapters_independently():
    intel = registry()
    dart = intel.for_path("lib/a.dart")
    python = intel.for_path("tool/script.py")
    typescript = intel.for_path("web/app.ts")
    javascript = intel.for_path("web/app.js")

    assert dart is intel.for_path("lib/b.dart")
    assert python is intel.for_path("app/other.py")
    assert javascript is intel.for_path("web/other.js")
    assert dart is not python
    assert dart is not typescript
    assert python is not typescript
    assert python is not javascript
    assert isinstance(dart, DartCodeIntelligence)
    assert isinstance(typescript, TypeScriptCodeIntelligence)
    assert isinstance(python, PythonCodeIntelligence)
    assert isinstance(javascript, JavaScriptCodeIntelligence)


# ============================================================
# FALLBACK PACKAGE
# ============================================================

def test_unsupported_language_still_produces_a_valid_package():
    service = ContextBuilderService(registry())
    path = "app/main.rb"

    pkg = service.build(
        diagnosis={
            "root_cause_locations": [
                {
                    "symbol": "main",
                    "path": path,
                    "line": 10,
                    "kind": "function",
                }
            ],
        },
        ranked=[{"path": path, "rank": 1, "total_score": 9}],
        files=[numbered(path, 40)],
        budget=ContextBudget(pad_lines=0, whole_file_fraction=1.01),
    )

    assert pkg.slices
    assert pkg.language == "unknown"
    assert pkg.adapter == "NullCodeIntelligence"
    assert pkg.slices[0].path == path
    assert pkg.slices[0].language == "unknown"
    assert pkg.slices[0].adapter == "NullCodeIntelligence"
    assert pkg.slices[0].truncated is True
    assert pkg.slices[0].content
    assert pkg.to_json()
    assert pkg.to_json() == service.build(
        diagnosis={
            "root_cause_locations": [
                {
                    "symbol": "main",
                    "path": path,
                    "line": 10,
                    "kind": "function",
                }
            ],
        },
        ranked=[{"path": path, "rank": 1, "total_score": 9}],
        files=[numbered(path, 40)],
        budget=ContextBudget(pad_lines=0, whole_file_fraction=1.01),
    ).to_json()


def test_mixed_repository_labels_slices_per_language():
    service = ContextBuilderService(registry())

    pkg = service.build(
        diagnosis={"relevant_files": ["lib/a.dart"]},
        ranked=[
            {"path": "lib/a.dart", "rank": 1, "total_score": 9},
            {"path": "tool/script.py", "rank": 2, "total_score": 8},
        ],
        files=[
            {"path": "lib/a.dart", "content": "class A {}\n"},
            {"path": "tool/script.py", "content": "print(1)\nprint(2)\n"},
        ],
        budget=ContextBudget(pad_lines=0, whole_file_fraction=1.01),
    )

    by_path = {item.path: item for item in pkg.slices}
    assert by_path["lib/a.dart"].language == "dart"
    assert by_path["lib/a.dart"].adapter == "DartCodeIntelligence"
    assert by_path["tool/script.py"].language == "python"
    assert by_path["tool/script.py"].adapter == "PythonCodeIntelligence"
    assert pkg.language == "mixed"
    assert pkg.adapter == "mixed"


# ============================================================
# DART BEHAVIOUR UNCHANGED
# ============================================================

def test_existing_dart_behaviour_is_unchanged_through_the_registry():
    files = json.loads(FIXTURE.read_text())["files"]
    standalone = DartCodeIntelligence()
    dart = registry().for_path("lib/anything.dart")

    assert isinstance(dart, DartCodeIntelligence)

    standalone_index = standalone.build_index(files)
    registry_index = dart.build_index(files)

    assert standalone.declaration_of(
        "CarBloc", standalone_index
    ) == dart.declaration_of("CarBloc", registry_index)
    assert standalone.analyze_structure(files) == dart.analyze_structure(files)
    assert standalone.enclosing_span(
        "lib/presentation/bloc/car_bloc.dart",
        6,
        standalone_index,
    ) == dart.enclosing_span(
        "lib/presentation/bloc/car_bloc.dart",
        6,
        registry_index,
    )


# ============================================================
# PLACEHOLDER BOUNDARIES
# ============================================================

def _registered(intel, cls):
    matches = [adapter for adapter in intel.adapters if isinstance(adapter, cls)]
    assert len(matches) == 1, f"expected one {cls.__name__} in the registry"
    return matches[0]


def test_typescript_adapter_is_selected_for_typescript_files():
    intel = registry()
    chosen = _registered(intel, TypeScriptCodeIntelligence)

    assert chosen.name == "typescript"
    assert chosen.has_intelligence is True
    assert supports(chosen, "src/app.ts")
    assert supports(chosen, "src/app.tsx")
    assert isinstance(intel.for_path("src/app.ts"), TypeScriptCodeIntelligence)
    assert isinstance(intel.for_path("src/app.tsx"), TypeScriptCodeIntelligence)
    assert intel.for_path("src/app.ts") is chosen
    assert not isinstance(intel.for_path("src/app.ts"), NullCodeIntelligence)
    assert isinstance(intel.for_path("src/app.js"), JavaScriptCodeIntelligence)


def test_javascript_adapter_is_selected_for_javascript_files():
    intel = registry()
    chosen = _registered(intel, JavaScriptCodeIntelligence)

    assert chosen.name == "javascript"
    assert chosen.has_intelligence is True
    assert supports(chosen, "src/app.js")
    assert supports(chosen, "src/app.jsx")
    assert isinstance(intel.for_path("src/app.js"), JavaScriptCodeIntelligence)
    assert isinstance(intel.for_path("src/app.jsx"), JavaScriptCodeIntelligence)
    assert intel.for_path("src/app.js") is chosen
    assert not isinstance(intel.for_path("src/app.js"), NullCodeIntelligence)
    assert isinstance(intel.for_path("src/app.ts"), TypeScriptCodeIntelligence)


def test_python_adapter_is_selected_for_python_files():
    intel = registry()
    chosen = _registered(intel, PythonCodeIntelligence)

    assert chosen.name == "python"
    assert chosen.has_intelligence is True
    assert supports(chosen, "app/main.py")
    assert isinstance(intel.for_path("app/main.py"), PythonCodeIntelligence)
    assert intel.for_path("app/main.py") is chosen
    assert not isinstance(intel.for_path("app/main.py"), NullCodeIntelligence)
    assert isinstance(intel.for_path("src/app.js"), JavaScriptCodeIntelligence)


def test_registry_selection_is_deterministic():
    first = registry()
    second = registry()

    assert [type(adapter).__name__ for adapter in first.adapters] == [
        "DartCodeIntelligence",
        "TypeScriptCodeIntelligence",
        "JavaScriptCodeIntelligence",
        "PythonCodeIntelligence",
    ]
    assert [type(adapter).__name__ for adapter in first.adapters] == [
        type(adapter).__name__ for adapter in second.adapters
    ]

    dart_path = "lib/a.dart"
    assert first.for_path(dart_path) is first.for_path("lib/b.dart")
    assert type(first.for_path(dart_path)) is type(second.for_path(dart_path))
    assert first.for_path("app/main.py") is first.for_path("pkg/mod.py")
    assert type(first.for_path("app/main.py")) is PythonCodeIntelligence
    assert type(first.for_path("web/app.ts")) is TypeScriptCodeIntelligence
    assert type(second.for_path("web/app.js")) is JavaScriptCodeIntelligence


def test_consumers_do_not_select_adapters():
    """ContextBuilder and the analysis runner never name a language."""

    builder_source = inspect.getsource(ContextBuilderService)
    runner_source = inspect.getsource(AnalysisRunner)

    for name in (
        "DartCodeIntelligence",
        "TypeScriptCodeIntelligence",
        "JavaScriptCodeIntelligence",
        "PythonCodeIntelligence",
        "NullCodeIntelligence",
    ):
        assert name not in builder_source
        assert name not in runner_source

    assert "for_path" in builder_source
