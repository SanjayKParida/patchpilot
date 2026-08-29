"""
Registry and null adapter: per-file language selection.

The core stays language-free. These tests are allowed to mention Dart
because they are about which adapter is chosen, not about how the
builder ranks or slices.
"""

import json
from pathlib import Path

from app.code_intelligence.dart_adapter import DartCodeIntelligence
from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.protocol import CodeIntelligence
from app.code_intelligence.registry import CodeIntelligenceRegistry
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
    chosen = registry().for_path("app/main.py")
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

    assert dart is intel.for_path("lib/b.dart")
    assert python is typescript
    assert dart is not python
    assert isinstance(dart, DartCodeIntelligence)
    assert isinstance(python, NullCodeIntelligence)


# ============================================================
# FALLBACK PACKAGE
# ============================================================

def test_unsupported_language_still_produces_a_valid_package():
    service = ContextBuilderService(registry())
    path = "app/main.py"

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
    assert by_path["tool/script.py"].language == "unknown"
    assert by_path["tool/script.py"].adapter == "NullCodeIntelligence"
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
