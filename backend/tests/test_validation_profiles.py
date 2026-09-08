"""
Validation profiles: runnability from repository evidence, not issue text.
"""

from app.services.validation_profiles import (
    FlutterValidationProfile,
    GoValidationProfile,
    NodeTypeScriptValidationProfile,
    PythonValidationProfile,
    RustValidationProfile,
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


def test_nested_pubspec_does_not_count_for_root_flutter_profile():
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


def test_python_requirements_with_pytest_dependency_runs_pytest():
    inspection = PythonValidationProfile().inspect({
        "requirements.txt": "flask==3.0.0\npytest==8.0.0\n",
        "app/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert True\n",
    })

    assert inspection.runnable is True
    assert inspection.profile == "python"
    assert [command.argv for command in inspection.commands] == [
        ("pip", "install", "-r", "requirements.txt"),
        ("python", "-m", "pytest"),
    ]


def test_python_pytest_ini_selects_pytest_without_explicit_dep_line():
    inspection = PythonValidationProfile().inspect({
        "pyproject.toml": "[project]\nname = \"demo\"\nversion = \"0.1.0\"\n",
        "pytest.ini": "[pytest]\ntestpaths = tests\n",
        "tests/test_demo.py": "def test_ok():\n    assert True\n",
    })

    assert inspection.runnable is True
    argv = [command.argv for command in inspection.commands]
    assert argv[0] == ("pip", "install", "-e", ".")
    assert ("python", "-m", "pytest") in argv


def test_python_nose2_dependency_selects_nose2():
    inspection = PythonValidationProfile().inspect({
        "requirements.txt": "nose2>=0.14\n",
        "tests/test_demo.py": "def test_ok():\n    assert True\n",
    })

    assert [command.argv for command in inspection.commands] == [
        ("pip", "install", "-r", "requirements.txt"),
        ("python", "-m", "nose2"),
    ]


def test_python_unittest_discover_when_tests_exist_without_pytest():
    inspection = PythonValidationProfile().inspect({
        "requirements.txt": "requests==2.32.0\n",
        "tests/test_demo.py": "import unittest\n",
    })

    assert [command.argv for command in inspection.commands] == [
        ("pip", "install", "-r", "requirements.txt"),
        ("python", "-m", "unittest", "discover"),
    ]


def test_python_poetry_lock_uses_poetry_install():
    inspection = PythonValidationProfile().inspect({
        "pyproject.toml": "[tool.poetry]\nname = \"demo\"\nversion = \"0.1.0\"\n",
        "poetry.lock": "# lock\n",
        "tests/test_demo.py": "def test_ok():\n    assert True\n",
        "pytest.ini": "[pytest]\n",
    })

    assert inspection.commands[0].argv == ("poetry", "install", "--no-interaction")
    assert ("python", "-m", "pytest") in [c.argv for c in inspection.commands]


def test_nested_python_package_validates_when_patch_touches_it():
    files = {
        "services/api/requirements.txt": "fastapi\npytest\n",
        "services/api/app.py": "x = 1\n",
        "frontend/pubspec.yaml": "name: ui\n",
    }
    inspection = select_validation_inspection(
        files,
        proposal={"files": [{"path": "services/api/app.py"}]},
    )

    assert inspection.runnable is True
    assert inspection.profile == "python"
    assert all(command.cwd == "services/api" for command in inspection.commands)
    assert ("python", "-m", "pytest") in [c.argv for c in inspection.commands]


def test_python_sources_without_manifest_are_unavailable():
    inspection = select_validation_inspection({
        "app/main.py": "print('hi')\n",
    })

    assert inspection.runnable is False
    assert inspection.profile == "python"
    assert "Python package manifest" in inspection.reason


def test_go_module_runs_test_and_vet():
    inspection = GoValidationProfile().inspect({
        "go.mod": "module example.com/demo\n\ngo 1.22\n",
        "main.go": "package main\n",
    })

    assert inspection.runnable is True
    assert [command.argv for command in inspection.commands] == [
        ("go", "test", "./..."),
        ("go", "vet", "./..."),
    ]


def test_nested_go_module_selected_by_patch():
    files = {
        "backend/go.mod": "module example.com/backend\n\ngo 1.22\n",
        "backend/main.go": "package main\n",
        "frontend/pubspec.yaml": "name: ui\n",
    }
    inspection = select_validation_inspection(
        files,
        proposal={"files": [{"path": "backend/main.go"}]},
    )

    assert inspection.profile == "go"
    assert all(command.cwd == "backend" for command in inspection.commands)


def test_rust_crate_runs_check_and_test():
    inspection = RustValidationProfile().inspect({
        "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\n',
        "src/lib.rs": "pub fn f() {}\n",
    })

    assert inspection.runnable is True
    assert [command.argv for command in inspection.commands] == [
        ("cargo", "check"),
        ("cargo", "test"),
    ]


def test_rust_clippy_added_when_clippy_toml_present():
    inspection = RustValidationProfile().inspect({
        "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\n',
        "clippy.toml": "msrv = \"1.70\"\n",
        "src/lib.rs": "pub fn f() {}\n",
    })

    assert [command.argv for command in inspection.commands] == [
        ("cargo", "check"),
        ("cargo", "clippy", "--", "-D", "warnings"),
        ("cargo", "test"),
    ]


def test_go_sources_without_mod_are_unavailable():
    inspection = select_validation_inspection({
        "main.go": "package main\n",
    })

    assert inspection.runnable is False
    assert inspection.profile == "go"
    assert "go.mod" in inspection.reason
