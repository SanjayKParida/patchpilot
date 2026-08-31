"""
Baseline diagnostic comparison for Flutter analyze.

Exit-code-only is too coarse: flutter analyze exits 1 for pre-existing
infos. Infos are not ignored; a patch fails only when it introduces
diagnostics the unpatched tree did not already have.
"""

from app.services.patch_types import (
    PatchFile,
    PatchHunk,
    PatchProposal,
    STATUS_OK,
)
from app.services.patch_validation_types import (
    STATUS_PASSED,
    STATUS_VALIDATION_FAILED,
    CommandResult,
    ValidationConfig,
)
from app.services.patch_validator_service import PatchValidatorService
from app.services.validation_diagnostics import (
    extra_diagnostics,
    parse_flutter_analyze,
)
from app.services.validation_profiles import FlutterValidationProfile
from app.services.validation_command_runner import FakeValidationCommandRunner


INFO_A = (
    "   info • Use key in widget constructors • "
    "lib/main.dart:10:9 • use_key_in_widget_constructors"
)
INFO_B = (
    "   info • Avoid print calls in production code • "
    "lib/main.dart:20:5 • avoid_print"
)
INFO_C = (
    "   info • Use key in widget constructors • "
    "lib/extra.dart:3:9 • use_key_in_widget_constructors"
)
ERROR = (
    "  error • Undefined name 'x' • "
    "lib/main.dart:4:5 • undefined_identifier"
)


def _analyze_stdout(*lines):
    body = "\n".join(lines)
    return (
        f"Analyzing demo...\n\n{body}\n\n"
        f"{len(lines)} issues found. (ran in 0.1s)\n"
    )


def _result(name, argv, exit_code, stdout=""):
    return CommandResult(
        name=name,
        argv=list(argv),
        exit_code=exit_code,
        timed_out=False,
        stdout=stdout,
        stderr="",
        duration_ms=1,
        passed=exit_code == 0,
    )


def _flutter_sequence(analyze_baseline, analyze_patched, test_exit=0):
    pub = ("flutter", "pub", "get")
    analyze = ("flutter", "analyze")
    test = ("flutter", "test")
    return [
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 1, analyze_baseline),
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 1, analyze_patched),
        _result("test", test, test_exit),
    ]


def _proposal():
    return PatchProposal(
        status=STATUS_OK,
        summary="test",
        reasoning="test",
        confidence=1.0,
        files=[
            PatchFile(
                path="lib/a.fake",
                language="fake",
                hunks=(PatchHunk(2, 2, "two", "TWO"),),
            )
        ],
    )


FILES = {
    "lib/a.fake": "one\ntwo\nthree\nfour",
    "pubspec.yaml": "name: demo\n",
}


def _validate(sequence):
    service = PatchValidatorService(
        command_runner=FakeValidationCommandRunner(results=list(sequence)),
    )
    return service.validate(
        _proposal(),
        FILES,
        config=ValidationConfig(
            commands=list(FlutterValidationProfile.COMMANDS),
        ),
    )


def test_flutter_analyze_parser_uses_path_severity_code():
    text = _analyze_stdout(INFO_A, INFO_B, ERROR)
    assert parse_flutter_analyze(text) == [
        ("lib/main.dart", "info", "use_key_in_widget_constructors"),
        ("lib/main.dart", "info", "avoid_print"),
        ("lib/main.dart", "error", "undefined_identifier"),
    ]


def test_line_shift_is_not_a_new_diagnostic():
    shifted = INFO_A.replace(":10:9", ":12:9")
    extra = extra_diagnostics(
        _analyze_stdout(INFO_A),
        _analyze_stdout(shifted),
        "flutter_analyze",
    )
    assert extra == []


def test_pre_existing_analyzer_diagnostics_remain_pass():
    stdout = _analyze_stdout(INFO_A, INFO_B)
    result = _validate(_flutter_sequence(stdout, stdout))

    assert result.status == STATUS_PASSED
    assert result.validation_passed is True
    analyze = [item for item in result.commands if item.name == "analyze"][0]
    assert analyze.exit_code == 1
    assert analyze.passed is True
    assert any("pre-existing" in warning for warning in result.warnings)


def test_new_analyzer_error_introduced_fails():
    baseline = _analyze_stdout(INFO_A, INFO_B)
    patched = _analyze_stdout(INFO_A, INFO_B, ERROR)
    result = _validate(_flutter_sequence(baseline, patched))

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.validation_passed is False
    analyze = [item for item in result.commands if item.name == "analyze"][0]
    assert analyze.passed is False
    assert any("new diagnostic" in error for error in result.errors)


def test_existing_diagnostics_increase_fails():
    baseline = _analyze_stdout(INFO_A, INFO_B)
    patched = _analyze_stdout(INFO_A, INFO_B, INFO_C)
    result = _validate(_flutter_sequence(baseline, patched))

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.validation_passed is False
    assert any("new diagnostic" in error for error in result.errors)


def test_analyzer_clean_passes():
    pub = ("flutter", "pub", "get")
    analyze = ("flutter", "analyze")
    test = ("flutter", "test")
    result = _validate([
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 0, "No issues found!\n"),
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 0, "No issues found!\n"),
        _result("test", test, 0),
    ])

    assert result.status == STATUS_PASSED
    assert result.validation_passed is True
    analyze_result = [
        item for item in result.commands if item.name == "analyze"
    ][0]
    assert analyze_result.exit_code == 0
    assert analyze_result.passed is True


def test_tests_fail_even_when_analyze_is_clean():
    pub = ("flutter", "pub", "get")
    analyze = ("flutter", "analyze")
    test = ("flutter", "test")
    result = _validate([
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 0, "No issues found!\n"),
        _result("pub_get", pub, 0),
        _result("analyze", analyze, 0, "No issues found!\n"),
        _result("test", test, 1, "some test failed\n"),
    ])

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.validation_passed is False
    test_result = [item for item in result.commands if item.name == "test"][0]
    assert test_result.exit_code == 1
    assert test_result.passed is False


def test_unparseable_analyzer_failure_is_not_passed():
    result = _validate(_flutter_sequence("boom\n", "boom\n"))

    assert result.status == STATUS_VALIDATION_FAILED
    assert result.validation_passed is False


def test_analyze_command_opts_into_baseline_compare():
    analyze = FlutterValidationProfile.COMMANDS[1]
    assert analyze.name == "analyze"
    assert analyze.compare_baseline is True
    assert analyze.diagnostic_format == "flutter_analyze"
    assert FlutterValidationProfile.COMMANDS[2].compare_baseline is False
