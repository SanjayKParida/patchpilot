"""
Language-specific validation recipes.

The snapshotter does not know Flutter or Node. Profiles inspect a
file map and decide whether a tree is runnable and which argv to
run. PatchValidator remains language-agnostic.

Commands are operator recipes built from repository evidence
(package.json scripts, lockfiles, tsconfig). They are never taken
from issue text.
"""

import json
from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from app.services.patch_validation_types import ValidationCommand


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
            )

        return ProfileInspection(
            runnable=True,
            missing=[],
            commands=list(self.COMMANDS),
            reason="",
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

    candidates.extend(_nested_flutter_inspections(files))
    candidates.extend(NodeTypeScriptValidationProfile().inspect_packages(files))
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

    return ProfileInspection(
        runnable=False,
        missing=[],
        commands=[],
        reason="no suitable validation profile",
    )
