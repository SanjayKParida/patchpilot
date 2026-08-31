"""
Validation profiles: runnability from repository evidence, not issue text.
"""

from app.services.validation_profiles import (
    FlutterValidationProfile,
    NodeTypeScriptValidationProfile,
    select_validation_inspection,
)


def test_missing_pubspec_is_not_runnable():
    inspection = FlutterValidationProfile().inspect(
        [{"path": "lib/main.dart", "content": "void main() {}"}]
    )

    assert inspection.runnable is False
    assert inspection.missing == ["pubspec.yaml"]
    assert inspection.commands == []
    assert "pubspec.yaml" in inspection.reason


def test_pubspec_at_root_is_runnable():
    inspection = FlutterValidationProfile().inspect({
        "pubspec.yaml": "name: demo\n",
        "lib/main.dart": "void main() {}\n",
    })

    assert inspection.runnable is True
    assert inspection.missing == []
    assert [command.argv for command in inspection.commands] == [
        ("flutter", "pub", "get"),
        ("flutter", "analyze"),
        ("flutter", "test"),
    ]
    assert inspection.commands[1].compare_baseline is True
    assert inspection.commands[1].diagnostic_format == "flutter_analyze"
    assert inspection.reason == ""


def test_nested_pubspec_does_not_count():
    inspection = FlutterValidationProfile().inspect([
        {"path": "packages/foo/pubspec.yaml"},
        {"path": "lib/main.dart"},
    ])

    assert inspection.runnable is False
    assert inspection.missing == ["pubspec.yaml"]


def test_node_package_with_test_script_uses_lockfile_and_allowlisted_scripts():
    inspection = NodeTypeScriptValidationProfile().inspect({
        "package.json": (
            '{"scripts": {"test": "vitest", "start": "node server.js", '
            '"db:migrate": "prisma migrate dev"}}'
        ),
        "package-lock.json": "{}",
        "src/index.ts": "export {}\n",
    })

    assert inspection.runnable is True
    argv = [command.argv for command in inspection.commands]
    assert argv[0] == ("npm", "ci", "--ignore-scripts")
    assert ("npm", "run", "test") in argv
    assert not any("migrate" in command.argv for command in inspection.commands)
    assert not any("start" in command.argv for command in inspection.commands)


def test_circle_marketplace_backend_is_independently_typecheckable():
    files = {
        "backend/package.json": (
            '{"name":"circle-marketplace-backend","scripts":{'
            '"dev":"ts-node-dev src/server.ts",'
            '"build":"prisma generate && tsc",'
            '"start":"node dist/server.js",'
            '"db:generate":"prisma generate",'
            '"db:migrate":"prisma migrate dev",'
            '"db:seed":"prisma db seed"}}'
        ),
        "backend/package-lock.json": "{}",
        "backend/tsconfig.json": '{"compilerOptions":{"strict":true}}',
        "backend/prisma/schema.prisma": "generator client { provider = \"prisma-client-js\" }",
        "backend/src/server.ts": "export {}\n",
        "frontend/pubspec.yaml": "name: frontend\n",
        "frontend/lib/main.dart": "void main() {}\n",
    }

    inspection = select_validation_inspection(
        files,
        proposal={"files": [{"path": "backend/src/server.ts"}]},
    )

    assert inspection.runnable is True
    assert [command.argv for command in inspection.commands] == [
        ("npm", "ci", "--ignore-scripts"),
        ("npx", "--no-install", "prisma", "generate"),
        ("npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"),
    ]
    assert all(command.cwd == "backend" for command in inspection.commands)
    assert not any("migrate" in command.argv for command in inspection.commands)
    assert not any(command.argv[:1] == ("flutter",) for command in inspection.commands)


def test_mixed_repo_validates_flutter_frontend_when_the_patch_is_there():
    files = {
        "backend/package.json": '{"scripts":{"test":"vitest"}}',
        "backend/package-lock.json": "{}",
        "frontend/pubspec.yaml": "name: frontend\n",
        "frontend/lib/main.dart": "void main() {}\n",
    }
    inspection = select_validation_inspection(
        files,
        proposal={"files": [{"path": "frontend/lib/main.dart"}]},
    )

    assert inspection.runnable is True
    assert [command.argv for command in inspection.commands] == [
        ("flutter", "pub", "get"),
        ("flutter", "analyze"),
        ("flutter", "test"),
    ]
    assert all(command.cwd == "frontend" for command in inspection.commands)


def test_mixed_repo_runs_both_ecosystems_when_the_patch_touches_both():
    files = {
        "backend/package.json": '{"scripts":{"test":"vitest"}}',
        "backend/package-lock.json": "{}",
        "frontend/pubspec.yaml": "name: frontend\n",
    }
    inspection = select_validation_inspection(
        files,
        proposal={
            "files": [
                {"path": "backend/src/server.ts"},
                {"path": "frontend/lib/main.dart"},
            ]
        },
    )

    argv = [command.argv for command in inspection.commands]
    assert ("flutter", "pub", "get") in argv
    assert ("npm", "ci", "--ignore-scripts") in argv
    assert ("npm", "run", "test") in argv


def test_root_flutter_selection_is_unchanged():
    inspection = select_validation_inspection({
        "pubspec.yaml": "name: demo\n",
        "lib/main.dart": "void main() {}\n",
    })

    assert [command.argv for command in inspection.commands] == [
        ("flutter", "pub", "get"),
        ("flutter", "analyze"),
        ("flutter", "test"),
    ]
    assert all(command.cwd == "" for command in inspection.commands)


def test_unsupported_repo_is_unavailable():
    inspection = select_validation_inspection({
        "README.md": "# hello\n",
        "Makefile": "all:\n",
    })

    assert inspection.runnable is False
    assert inspection.commands == []
    assert inspection.reason == "no suitable validation profile"


def test_dart_without_pubspec_keeps_the_flutter_unavailable_reason():
    inspection = select_validation_inspection({
        "lib/main.dart": "void main() {}\n",
    })

    assert inspection.runnable is False
    assert "pubspec.yaml" in inspection.reason



def test_pubspec_at_root_is_runnable():
    inspection = FlutterValidationProfile().inspect({
        "pubspec.yaml": "name: demo\n",
        "lib/main.dart": "void main() {}\n",
    })

    assert inspection.runnable is True
    assert inspection.missing == []
    assert [command.argv for command in inspection.commands] == [
        ("flutter", "pub", "get"),
        ("flutter", "analyze"),
        ("flutter", "test"),
    ]
    assert inspection.commands[1].compare_baseline is True
    assert inspection.commands[1].diagnostic_format == "flutter_analyze"
    assert inspection.reason == ""


def test_nested_pubspec_does_not_count():
    inspection = FlutterValidationProfile().inspect([
        {"path": "packages/foo/pubspec.yaml"},
        {"path": "lib/main.dart"},
    ])

    assert inspection.runnable is False
    assert inspection.missing == ["pubspec.yaml"]
