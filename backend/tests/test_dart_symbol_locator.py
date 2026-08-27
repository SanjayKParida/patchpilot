"""
Unit tests for DartSymbolLocator.

The locator exists so the language model is never responsible for a
code location. It names a symbol; this decides where that symbol is.

Two properties matter and are pinned here:

    Correctness — a known symbol resolves to the declaration site a
    developer would jump to.

    Restraint — anything it cannot resolve unambiguously is dropped.
    A missing shortcut costs a click; a wrong one sends someone to
    the wrong code and quietly discredits the diagnosis.
"""

import pytest

from app.utils.dart.dart_symbol_locator import DartSymbolLocator


@pytest.fixture
def locator():
    return DartSymbolLocator()


def _file(path, content):
    return {"path": path, "sha": path, "content": content}


STATE = _file(
    "lib/presentation/bloc/task_state.dart",
    "import 'package:app/task.dart';\n"      # 1
    "\n"                                      # 2
    "abstract class TaskState {}\n"           # 3
    "\n"                                      # 4
    "class TaskLoading extends TaskState {}\n"  # 5
    "\n"                                      # 6
    "class TaskLoaded extends TaskState {\n"  # 7
    "  final List<Task> tasks;\n"             # 8
    "  TaskLoaded(this.tasks);\n"             # 9
    "}\n",                                    # 10
)

EVENT = _file(
    "lib/presentation/bloc/task_event.dart",
    "abstract class TaskEvent {}\n"                    # 1
    "\n"                                                # 2
    "class RefreshTasksRequested extends TaskEvent {}\n",  # 3
)

FILES = [STATE, EVENT]


def _resolved(locator, symbols, files=None):
    return locator.resolve(symbols, files=files or FILES)


# ============================================================
# KNOWN SYMBOL -> CORRECT FILE AND LINE
# ============================================================

@pytest.mark.parametrize(
    "symbol,path,line",
    [
        ("TaskState", STATE["path"], 3),
        ("TaskLoading", STATE["path"], 5),
        ("TaskLoaded", STATE["path"], 7),
        ("TaskEvent", EVENT["path"], 1),
        ("RefreshTasksRequested", EVENT["path"], 3),
    ],
)
def test_known_symbol_resolves(locator, symbol, path, line):
    result = _resolved(locator, [symbol])

    assert result == [
        {
            "symbol": symbol,
            "path": path,
            "line": line,
            "kind": "class",
        }
    ]


def test_multiple_symbols_all_resolve_in_order(locator):
    result = _resolved(
        locator,
        ["RefreshTasksRequested", "TaskLoading", "TaskLoaded"],
    )

    assert [item["symbol"] for item in result] == [
        "RefreshTasksRequested",
        "TaskLoading",
        "TaskLoaded",
    ]
    assert [item["line"] for item in result] == [3, 5, 7]


def test_duplicate_symbols_are_collapsed(locator):
    result = _resolved(
        locator,
        ["TaskLoading", "TaskLoading", "TaskLoading"],
    )

    assert len(result) == 1


# ============================================================
# ANYTHING UNRESOLVABLE IS DROPPED
# ============================================================

def test_unknown_symbol_is_omitted(locator):
    # A Flutter type, not declared in this repository.
    result = _resolved(
        locator,
        ["CircularProgressIndicator", "TaskLoading"],
    )

    assert [item["symbol"] for item in result] == ["TaskLoading"]


def test_ambiguous_symbol_is_omitted(locator):
    """
    Declared in two files, so a bare name cannot say which. Guessing
    would send a developer to the wrong declaration.
    """

    other = _file(
        "lib/other/task_state.dart",
        "class TaskLoading {}\n",
    )

    result = locator.resolve(
        ["TaskLoading"],
        files=FILES + [other],
    )

    assert result == []


def test_declarations_in_comments_and_strings_are_ignored(locator):
    noisy = _file(
        "lib/noisy.dart",
        "// class GhostState {}\n"
        "final label = 'class StringState {}';\n"
        "/* class BlockState {} */\n"
        "class RealState {}\n",
    )

    result = locator.resolve(
        ["GhostState", "StringState", "BlockState", "RealState"],
        files=[noisy],
    )

    assert [item["symbol"] for item in result] == ["RealState"]
    assert result[0]["line"] == 4


@pytest.mark.parametrize("symbols", [None, [], ["", "   "], [42, None]])
def test_empty_and_malformed_input_is_safe(locator, symbols):
    assert _resolved(locator, symbols) == []


def test_non_dart_files_are_ignored(locator):
    kotlin = _file(
        "android/MainActivity.kt",
        "class TaskLoading {}\n",
    )

    result = locator.resolve(["TaskLoading"], files=[kotlin])

    assert result == []


# ============================================================
# DECLARATION KINDS
# ============================================================

@pytest.mark.parametrize(
    "source,symbol,kind",
    [
        ("enum Status { open }", "Status", "enum"),
        ("typedef Json = Map<String, dynamic>;", "Json", "typedef"),
        ("mixin Equatable {}", "Equatable", "mixin"),
        ("extension TaskX on Task {}", "TaskX", "extension"),
        ("abstract class Repo {}", "Repo", "class"),
        ("sealed class Result {}", "Result", "class"),
        ("mixin class Both {}", "Both", "class"),
        ("Future<List<Car>> getCars() async {}", "getCars", "function"),
        ("void initInjection() {}", "initInjection", "function"),
    ],
)
def test_declaration_kind_is_reported(locator, source, symbol, kind):
    result = locator.resolve(
        [symbol],
        files=[_file("lib/kinds.dart", f"{source}\n")],
    )

    assert result == [
        {
            "symbol": symbol,
            "path": "lib/kinds.dart",
            "line": 1,
            "kind": kind,
        }
    ]


# ============================================================
# METHODS: DECLARATIONS ONLY, NEVER CALL SITES
# ============================================================

CALLER = _file(
    "lib/data/repo_impl.dart",
    "class RepoImpl {\n"                       # 1
    "  Future<List<Task>> loadTasks() {\n"      # 2
    "    return dataSource.fetchRemote();\n"    # 3
    "  }\n"                                     # 4
    "}\n",                                      # 5
)

SOURCE = _file(
    "lib/data/remote.dart",
    "class Remote {\n"                          # 1
    "  Future<List<Task>> fetchRemote() async {}\n"  # 2
    "}\n",                                      # 3
)


def test_a_method_resolves_to_its_declaration(locator):
    result = locator.resolve(
        ["fetchRemote"],
        files=[CALLER, SOURCE],
    )

    assert result == [
        {
            "symbol": "fetchRemote",
            "path": "lib/data/remote.dart",
            "line": 2,
            "kind": "function",
        }
    ]


def test_a_call_site_is_not_mistaken_for_a_declaration(locator):
    """
    `dataSource.fetchRemote()` appears in the caller. Only the file
    that declares it may be reported.
    """

    index = locator.build_index([CALLER, SOURCE])

    assert [entry["path"] for entry in index["fetchRemote"]] == [
        "lib/data/remote.dart"
    ]


def test_a_method_name_used_everywhere_is_dropped(locator):
    """
    `build` is declared by every widget. Resolving it would send a
    developer to an arbitrary one, so it resolves to nothing.
    """

    widgets = [
        _file(
            f"lib/w{index}.dart",
            f"class W{index} {{\n  Widget build(context) {{}}\n}}\n",
        )
        for index in range(3)
    ]

    assert locator.resolve(["build"], files=widgets) == []
