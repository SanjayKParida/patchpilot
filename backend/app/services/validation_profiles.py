"""
Language-specific validation recipes.

The snapshotter does not know Flutter, Node, Python, Go, or Rust.
Profiles inspect a file map and decide whether a tree is runnable and
which argv to run. PatchValidator remains language-agnostic.

Commands are operator recipes built from repository evidence
(manifests, lockfiles, config files, declared dependencies). They are
never taken from issue text.
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from app.services.patch_validation_types import ValidationCommand

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore


def _paths_from_files(files):
    if files is None:
        return set()

    if isinstance(files, dict):
        return set(files)

    paths = set()

    for item in files:
        if isinstance(item, dict):
            path = item.get("path")
        elif isinstance(item, str):
            path = item
        else:
            path = getattr(item, "path", None)

        if path:
            paths.add(path)

    return paths


def _contents_from_files(files):
    if files is None:
        return {}

    if isinstance(files, dict):
        return {
            path: content if isinstance(content, str) else ""
            for path, content in files.items()
        }

    contents = {}
    for item in files:
        if isinstance(item, dict):
            path = item.get("path")
            if path:
                contents[path] = item.get("content") or ""
        elif isinstance(item, str):
            contents[item] = ""
        else:
            path = getattr(item, "path", None)
            if path:
                contents[path] = getattr(item, "content", "") or ""
    return contents


def _proposal_paths(proposal):
    if proposal is None:
        return []

    files = getattr(proposal, "files", None)
    if files is None and isinstance(proposal, dict):
        files = proposal.get("files") or []

    paths = []
    for item in files or []:
        if isinstance(item, dict):
            path = item.get("path")
        else:
            path = getattr(item, "path", None)
        if path:
            paths.append(path)
    return paths


def _path_under(path, root):
    if not root:
        return True
    return path == root or path.startswith(root + "/")


def _longest_root(path, roots):
    matching = [root for root in roots if _path_under(path, root)]
    if not matching:
        return None
    return max(matching, key=lambda root: len(root))


def _skip_package_path(path):
    parts = path.split("/")
    return any(
        part in {
            "node_modules",
            "dist",
            "build",
            ".dart_tool",
            "coverage",
            "vendor",
            ".venv",
            "venv",
            "__pycache__",
            ".tox",
            ".mypy_cache",
            "target",
            ".git",
        }
        for part in parts
    )


@dataclass
class ProfileInspection:
    runnable: bool
    missing: List[str] = field(default_factory=list)
    commands: List[ValidationCommand] = field(default_factory=list)
    reason: str = ""
    profile: str = ""
    cwd: str = ""


@runtime_checkable
class ValidationProfile(Protocol):
    def inspect(self, files) -> ProfileInspection:
        ...


class FlutterValidationProfile:
    """
    A Flutter project is runnable when pubspec.yaml is at the repo root.

    Commands are operator recipes, not issue-supplied shell.
    """

    REQUIRED = ("pubspec.yaml",)

    COMMANDS = (
        ValidationCommand("pub_get", ("flutter", "pub", "get")),
        ValidationCommand(
            "analyze",
            ("flutter", "analyze"),
            compare_baseline=True,
            diagnostic_format="flutter_analyze",
        ),
        ValidationCommand("test", ("flutter", "test")),
    )

    def inspect(self, files):
        paths = _paths_from_files(files)
        missing = [
            required for required in self.REQUIRED
            if required not in paths
        ]

        if missing:
            return ProfileInspection(
                runnable=False,
                missing=list(missing),
                commands=[],
                reason="missing " + ", ".join(missing),
                profile="flutter",
            )

        return ProfileInspection(
            runnable=True,
            missing=[],
            commands=list(self.COMMANDS),
            reason="",
            profile="flutter",
        )


SAFE_NODE_SCRIPTS = ("test", "lint", "typecheck", "types", "tsc", "check")

_SKIP_NODE_SCRIPTS = {
    "start",
    "dev",
    "serve",
    "preview",
    "build",
    "studio",
    "postinstall",
    "preinstall",
    "prepare",
    "prepublish",
    "publish",
    "deploy",
    "release",
}


class NodeTypeScriptValidationProfile:
    """
    A Node/TypeScript package is runnable when package.json is present.

    Install uses the lockfile in that directory. Extra scripts run
    only when their names are in SAFE_NODE_SCRIPTS. Runtime, migrate,
    seed, and start scripts are never selected.
    """

    def inspect(self, files):
        packages = self.inspect_packages(files)
        if len(packages) == 1:
            return packages[0]
        if not packages:
            return ProfileInspection(
                runnable=False,
                missing=["package.json"],
                commands=[],
                reason="missing package.json",
                profile="node",
            )
        return _merge_inspections(packages)

    def inspect_packages(self, files):
        contents = _contents_from_files(files)
        inspections = []

        for path in sorted(contents):
            if _skip_package_path(path):
                continue
            if not path.endswith("package.json"):
                continue
            inspection = self._inspect_package(path, contents)
            if inspection.runnable:
                inspections.append(inspection)

        return inspections

    def _inspect_package(self, manifest_path, contents):
        directory = _parent_dir(manifest_path)
        parsed = _parse_json_object(contents.get(manifest_path, ""))
        if parsed is None:
            return ProfileInspection(
                runnable=False,
                missing=[],
                commands=[],
                reason=f"invalid {manifest_path}",
                profile="node",
                cwd=directory,
            )

        scripts = parsed.get("scripts") or {}
        if not isinstance(scripts, dict):
            scripts = {}

        commands = [_install_command(directory, contents)]

        schema_path = _join(directory, "prisma/schema.prisma")
        if schema_path in contents:
            commands.append(
                ValidationCommand(
                    "prisma_generate",
                    ("npx", "--no-install", "prisma", "generate"),
                    cwd=directory,
                )
            )

        tsconfig_path = _join(directory, "tsconfig.json")
        has_typecheck_script = any(
            name in scripts for name in ("typecheck", "types", "tsc")
        )
        if tsconfig_path in contents and not has_typecheck_script:
            commands.append(
                ValidationCommand(
                    "tsc",
                    ("npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"),
                    cwd=directory,
                )
            )

        for name in SAFE_NODE_SCRIPTS:
            if name not in scripts:
                continue
            if name in _SKIP_NODE_SCRIPTS:
                continue
            runner = _package_runner(directory, contents)
            commands.append(
                ValidationCommand(
                    name,
                    runner + ("run", name),
                    cwd=directory,
                )
            )

        return ProfileInspection(
            runnable=True,
            missing=[],
            commands=commands,
            reason="",
            profile="node",
            cwd=directory,
        )


class PythonValidationProfile:
    """
    A Python project is runnable when a package manifest is present.

    Evidence (requirements.txt, pyproject.toml, Pipfile, setup.py) picks
    the install recipe. Test runners are chosen from declared deps and
    config: pytest, nose2, then unittest discover when tests exist.
    """

    _MANIFEST_NAMES = (
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "setup.py",
    )

    def inspect(self, files):
        packages = self.inspect_packages(files)
        if len(packages) == 1:
            return packages[0]
        if not packages:
            return ProfileInspection(
                runnable=False,
                missing=["requirements.txt or pyproject.toml"],
                commands=[],
                reason="missing Python package manifest",
                profile="python",
            )
        return _merge_inspections(packages)

    def inspect_packages(self, files):
        contents = _contents_from_files(files)
        roots = set()

        for path in contents:
            if _skip_package_path(path):
                continue
            name = path.rsplit("/", 1)[-1]
            if name in self._MANIFEST_NAMES:
                roots.add(_parent_dir(path))

        inspections = []
        for directory in sorted(roots, key=lambda item: (item.count("/"), item)):
            inspection = self._inspect_directory(directory, contents)
            if inspection.runnable:
                inspections.append(inspection)
        return inspections

    def _inspect_directory(self, directory, contents):
        install = _python_install_command(directory, contents)
        if install is None:
            return ProfileInspection(
                runnable=False,
                missing=["requirements.txt or pyproject.toml"],
                commands=[],
                reason="missing Python package manifest",
                profile="python",
                cwd=directory,
            )

        commands = [install]
        test_command = _python_test_command(directory, contents)
        if test_command is not None:
            commands.append(test_command)

        return ProfileInspection(
            runnable=True,
            missing=[],
            commands=commands,
            reason="",
            profile="python",
            cwd=directory,
        )


class GoValidationProfile:
    """
    A Go module is runnable when go.mod is present.

    Commands: go test ./... and go vet ./...
    """

    def inspect(self, files):
        packages = self.inspect_packages(files)
        if len(packages) == 1:
            return packages[0]
        if not packages:
            return ProfileInspection(
                runnable=False,
                missing=["go.mod"],
                commands=[],
                reason="missing go.mod",
                profile="go",
            )
        return _merge_inspections(packages)

    def inspect_packages(self, files):
        contents = _contents_from_files(files)
        inspections = []

        for path in sorted(contents):
            if _skip_package_path(path):
                continue
            if path != "go.mod" and not path.endswith("/go.mod"):
                continue
            directory = _parent_dir(path)
            inspections.append(
                ProfileInspection(
                    runnable=True,
                    missing=[],
                    commands=[
                        ValidationCommand(
                            "test",
                            ("go", "test", "./..."),
                            cwd=directory,
                        ),
                        ValidationCommand(
                            "vet",
                            ("go", "vet", "./..."),
                            cwd=directory,
                        ),
                    ],
                    reason="",
                    profile="go",
                    cwd=directory,
                )
            )
        return inspections


class RustValidationProfile:
    """
    A Rust crate is runnable when Cargo.toml is present.

    Commands: cargo check and cargo test. Clippy is used only when
    clippy.toml / .clippy.toml evidence exists.
    """

    def inspect(self, files):
        packages = self.inspect_packages(files)
        if len(packages) == 1:
            return packages[0]
        if not packages:
            return ProfileInspection(
                runnable=False,
                missing=["Cargo.toml"],
                commands=[],
                reason="missing Cargo.toml",
                profile="rust",
            )
        return _merge_inspections(packages)

    def inspect_packages(self, files):
        contents = _contents_from_files(files)
        inspections = []

        for path in sorted(contents):
            if _skip_package_path(path):
                continue
            if path != "Cargo.toml" and not path.endswith("/Cargo.toml"):
                continue
            directory = _parent_dir(path)
            commands = [
                ValidationCommand(
                    "check",
                    ("cargo", "check"),
                    cwd=directory,
                ),
                ValidationCommand(
                    "test",
                    ("cargo", "test"),
                    cwd=directory,
                ),
            ]
            if (
                _join(directory, "clippy.toml") in contents
                or _join(directory, ".clippy.toml") in contents
            ):
                commands.insert(
                    1,
                    ValidationCommand(
                        "clippy",
                        ("cargo", "clippy", "--", "-D", "warnings"),
                        cwd=directory,
                    ),
                )
            inspections.append(
                ProfileInspection(
                    runnable=True,
                    missing=[],
                    commands=commands,
                    reason="",
                    profile="rust",
                    cwd=directory,
                )
            )
        return inspections


def _parent_dir(path):
    if "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]


def _join(directory, name):
    if not directory:
        return name
    return f"{directory}/{name}"


def _parse_json_object(raw):
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_toml_object(raw):
    if tomllib is None or not raw:
        return None
    try:
        data = tomllib.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _install_command(directory, contents):
    if _join(directory, "pnpm-lock.yaml") in contents:
        return ValidationCommand(
            "install",
            ("pnpm", "install", "--frozen-lockfile", "--ignore-scripts"),
            cwd=directory,
        )
    if _join(directory, "yarn.lock") in contents:
        return ValidationCommand(
            "install",
            ("yarn", "install", "--frozen-lockfile", "--ignore-scripts"),
            cwd=directory,
        )
    if _join(directory, "package-lock.json") in contents:
        return ValidationCommand(
            "install",
            ("npm", "ci", "--ignore-scripts"),
            cwd=directory,
        )
    return ValidationCommand(
        "install",
        ("npm", "install", "--ignore-scripts"),
        cwd=directory,
    )


def _package_runner(directory, contents):
    if _join(directory, "pnpm-lock.yaml") in contents:
        return ("pnpm",)
    if _join(directory, "yarn.lock") in contents:
        return ("yarn",)
    return ("npm",)


_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _requirement_names(text):
    names = set()
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = _REQ_NAME_RE.match(stripped.split(";")[0].split("#")[0])
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def _python_dependency_names(directory, contents):
    names = set()

    requirements = contents.get(_join(directory, "requirements.txt"), "")
    names |= _requirement_names(requirements)

    for extra in (
        "requirements-dev.txt",
        "requirements_dev.txt",
        "dev-requirements.txt",
        "requirements/dev.txt",
        "requirements/test.txt",
    ):
        names |= _requirement_names(contents.get(_join(directory, extra), ""))

    pipfile = contents.get(_join(directory, "Pipfile"), "")
    if pipfile:
        names |= _requirement_names(pipfile)

    pyproject_raw = contents.get(_join(directory, "pyproject.toml"), "")
    parsed = _parse_toml_object(pyproject_raw)
    if parsed:
        project = parsed.get("project") or {}
        for item in project.get("dependencies") or []:
            if isinstance(item, str):
                names |= _requirement_names(item)
        optional = project.get("optional-dependencies") or {}
        if isinstance(optional, dict):
            for group in optional.values():
                for item in group or []:
                    if isinstance(item, str):
                        names |= _requirement_names(item)
        poetry = (parsed.get("tool") or {}).get("poetry") or {}
        for key, value in (poetry.get("dependencies") or {}).items():
            if key != "python":
                names.add(key.lower().replace("_", "-"))
        for key in (poetry.get("dev-dependencies") or {}):
            names.add(key.lower().replace("_", "-"))
        for group in (poetry.get("group") or {}).values():
            if not isinstance(group, dict):
                continue
            deps = group.get("dependencies") or {}
            if isinstance(deps, dict):
                for key in deps:
                    if key != "python":
                        names.add(key.lower().replace("_", "-"))
    elif pyproject_raw:
        for token in ("pytest", "nose2", "nose"):
            if re.search(rf"\b{token}\b", pyproject_raw, re.IGNORECASE):
                names.add(token)

    return names


def _python_install_command(directory, contents):
    if _join(directory, "poetry.lock") in contents or _pyproject_is_poetry(
        contents.get(_join(directory, "pyproject.toml"), "")
    ):
        return ValidationCommand(
            "install",
            ("poetry", "install", "--no-interaction"),
            cwd=directory,
        )

    if _join(directory, "Pipfile.lock") in contents or _join(
        directory, "Pipfile"
    ) in contents:
        return ValidationCommand(
            "install",
            ("pipenv", "install", "--deploy", "--dev"),
            cwd=directory,
        )

    requirements = _join(directory, "requirements.txt")
    if requirements in contents:
        return ValidationCommand(
            "install",
            ("pip", "install", "-r", "requirements.txt"),
            cwd=directory,
        )

    if _join(directory, "pyproject.toml") in contents or _join(
        directory, "setup.py"
    ) in contents:
        return ValidationCommand(
            "install",
            ("pip", "install", "-e", "."),
            cwd=directory,
        )

    return None


def _pyproject_is_poetry(raw):
    parsed = _parse_toml_object(raw)
    if parsed:
        tool = parsed.get("tool") or {}
        return isinstance(tool.get("poetry"), dict)
    return bool(raw) and "[tool.poetry]" in raw


def _python_has_pytest_config(directory, contents):
    if _join(directory, "pytest.ini") in contents:
        return True
    if _join(directory, "conftest.py") in contents:
        return True
    tox = contents.get(_join(directory, "tox.ini"), "")
    if "pytest" in tox.lower():
        return True
    pyproject = contents.get(_join(directory, "pyproject.toml"), "")
    parsed = _parse_toml_object(pyproject)
    if parsed:
        tool = parsed.get("tool") or {}
        if isinstance(tool.get("pytest"), dict):
            return True
    elif "[tool.pytest" in pyproject:
        return True
    return False


def _python_has_unittest_layout(directory, contents):
    prefix = f"{directory}/" if directory else ""
    for path in contents:
        if directory and not (path == directory or path.startswith(prefix)):
            continue
        name = path.rsplit("/", 1)[-1]
        if name.startswith("test_") and name.endswith(".py"):
            return True
        if name.endswith("_test.py"):
            return True
    return False


def _python_test_command(directory, contents):
    deps = _python_dependency_names(directory, contents)

    if "pytest" in deps or _python_has_pytest_config(directory, contents):
        return ValidationCommand(
            "pytest",
            ("python", "-m", "pytest"),
            cwd=directory,
        )

    if "nose2" in deps:
        return ValidationCommand(
            "nose2",
            ("python", "-m", "nose2"),
            cwd=directory,
        )

    if "nose" in deps:
        return ValidationCommand(
            "nose",
            ("python", "-m", "nose"),
            cwd=directory,
        )

    if _python_has_unittest_layout(directory, contents):
        return ValidationCommand(
            "unittest",
            ("python", "-m", "unittest", "discover"),
            cwd=directory,
        )

    return None


def _nested_flutter_inspections(files):
    contents = _contents_from_files(files)
    inspections = []

    for path in sorted(contents):
        if path == "pubspec.yaml" or not path.endswith("/pubspec.yaml"):
            continue
        if _skip_package_path(path):
            continue
        directory = _parent_dir(path)
        commands = [
            ValidationCommand(
                command.name,
                command.argv,
                cwd=directory,
                compare_baseline=command.compare_baseline,
                diagnostic_format=command.diagnostic_format,
            )
            for command in FlutterValidationProfile.COMMANDS
        ]
        inspections.append(
            ProfileInspection(
                runnable=True,
                missing=[],
                commands=commands,
                reason="",
                profile="flutter",
                cwd=directory,
            )
        )

    return inspections


def _merge_inspections(inspections):
    runnable = [item for item in inspections if item.runnable]
    if not runnable:
        return inspections[0] if inspections else ProfileInspection(
            runnable=False,
            reason="no suitable validation profile",
        )

    commands = []
    for item in runnable:
        commands.extend(item.commands)

    return ProfileInspection(
        runnable=True,
        missing=[],
        commands=commands,
        reason="",
        profile=",".join(
            item.profile or "unknown" for item in runnable if item.profile
        ),
        cwd=runnable[0].cwd if len(runnable) == 1 else "",
    )


def _candidates(files):
    flutter = FlutterValidationProfile().inspect(files)
    candidates = []
    if flutter.runnable:
        candidates.append(flutter)

    candidates.extend(PythonValidationProfile().inspect_packages(files))
    candidates.extend(_nested_flutter_inspections(files))
    candidates.extend(NodeTypeScriptValidationProfile().inspect_packages(files))
    candidates.extend(GoValidationProfile().inspect_packages(files))
    candidates.extend(RustValidationProfile().inspect_packages(files))
    return flutter, candidates


def select_validation_inspection(files, proposal=None):
    """
    Choose validation commands from repository evidence.

    Root Flutter projects keep the historical Flutter profile. Mixed
    trees validate the ecosystem the patch actually touches. Issue
    text is never consulted.
    """

    flutter, candidates = _candidates(files)
    patched = _proposal_paths(proposal)

    if patched:
        roots = [item.cwd for item in candidates]
        matched = []
        seen = set()
        for path in patched:
            root = _longest_root(path, roots)
            if root is None:
                continue
            for item in candidates:
                if item.cwd == root and id(item) not in seen:
                    matched.append(item)
                    seen.add(id(item))
        if matched:
            return _merge_inspections(matched)

    if flutter.runnable:
        return flutter

    if candidates:
        return _merge_inspections(candidates)

    paths = _paths_from_files(files)
    if any(path.endswith(".dart") for path in paths):
        return flutter

    if any(path.endswith((".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")) for path in paths):
        return ProfileInspection(
            runnable=False,
            missing=["package.json"],
            commands=[],
            reason="missing package.json",
            profile="node",
        )

    if any(path.endswith(".py") for path in paths):
        return ProfileInspection(
            runnable=False,
            missing=["requirements.txt or pyproject.toml"],
            commands=[],
            reason="missing Python package manifest",
            profile="python",
        )

    if any(path.endswith(".go") for path in paths):
        return ProfileInspection(
            runnable=False,
            missing=["go.mod"],
            commands=[],
            reason="missing go.mod",
            profile="go",
        )

    if any(path.endswith(".rs") for path in paths):
        return ProfileInspection(
            runnable=False,
            missing=["Cargo.toml"],
            commands=[],
            reason="missing Cargo.toml",
            profile="rust",
        )

    return ProfileInspection(
        runnable=False,
        missing=[],
        commands=[],
        reason="no suitable validation profile",
    )
