import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'package:patchpilot_web/app/app_routes.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/features/repair/context/screens/context_screen.dart';
import 'package:patchpilot_web/features/repair/diagnosis/screens/diagnosis_screen.dart';
import 'package:patchpilot_web/features/repair/patch/widgets/patch_panel.dart';
import 'package:patchpilot_web/features/repair/pull_request/screens/pull_request_models.dart';
import 'package:patchpilot_web/features/repair/pull_request/screens/pull_request_screen.dart';
import 'package:patchpilot_web/features/repair/review/screens/review_models.dart';
import 'package:patchpilot_web/features/repair/review/screens/review_screen.dart';
import 'package:patchpilot_web/features/repair/validation/screens/validation_screen.dart';
import 'package:patchpilot_web/features/repair/shell/repair_header.dart';
import 'package:patchpilot_web/features/repair/shell/repair_inspector.dart';
import 'package:patchpilot_web/features/repair/shell/repair_shell.dart';
import 'package:patchpilot_web/features/repair/shell/repair_status_bar.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/features/repair/shell/widgets/repair_continue_action.dart';
import 'package:patchpilot_web/models/context_package.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/github_redirect.dart';

/// Persistent host for Diagnosis → Patch → Validation → Review → Pull Request.
///
/// Owns one [RepairShell] and the session fields those stages share:
/// repository, issue, ref, [ApiClient], [AnalysisCache], the current
/// [RepairStage], the latest analysis, and stored patch artifacts.
/// Context is not a rail stage; it is shown as an artifact on Patch.
class RepairSession extends StatefulWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final Repository repository;
  final Issue issue;
  final String? ref;
  final VoidCallback onBack;
  final GithubRedirect? redirect;
  final ValueNotifier<AuthUser?>? session;
  final Future<void> Function({String? analysisId, String? stage})?
  onConnectGithub;
  final RepairStage? requestedStage;
  final String? resumeAnalysisId;
  final ValueChanged<RepairStage>? onStageCommitted;
  final ValueChanged<RepairStage>? onStageNormalized;

  const RepairSession({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.onBack,
    this.ref,
    this.redirect,
    this.session,
    this.onConnectGithub,
    this.requestedStage,
    this.resumeAnalysisId,
    this.onStageCommitted,
    this.onStageNormalized,
  });

  @override
  State<RepairSession> createState() => _RepairSessionState();
}

class _RepairSessionState extends State<RepairSession> {
  static const _workflowStages = [
    RepairStage.diagnosis,
    RepairStage.patch,
    RepairStage.validation,
    RepairStage.review,
    RepairStage.pullRequest,
  ];

  RepairStage _stage = RepairStage.diagnosis;
  Analysis? _analysis;
  String? _error;
  bool _fromCache = false;
  bool _showInspector = false;
  bool _openedPatch = false;
  bool _openedValidation = false;
  bool _openedReview = false;
  bool _openedPullRequest = false;
  ContextSlice? _inspectedSlice;

  PatchProposal? _proposal;
  PatchValidationResult? _validation;
  PatchApproval? _approval;
  PatchDelivery? _delivery;
  String? _reviewFeedback;
  String? _hydratedForId;
  bool _patchBusy = false;
  bool _validating = false;
  bool _delivering = false;
  bool _approving = false;
  String? _prError;
  String? _prTitle;
  String? _prDescription;

  String get _cacheKey => AnalysisCache.keyFor(
    widget.repository.owner,
    widget.repository.repo,
    widget.issue.number,
    ref: widget.ref,
  );

  /// The analysis id stages share. Diagnosis writes it here; later
  /// stages only read it, so switching stages cannot drop the job.
  String? get analysisId {
    final id = _analysis?.id;
    if (id == null || id.isEmpty) return null;
    return id;
  }

  bool get _diagnosisReady {
    final analysis = _analysis;
    return analysis != null &&
        analysis.id.isNotEmpty &&
        analysis.status == AnalysisStatus.completed &&
        analysis.diagnosis != null;
  }

  bool get _patchReady => _proposal?.canValidate == true;

  /// Missing/unknown validation is never treated as passed.
  bool get _validationPassed => _validation?.isPassed == true;

  bool get _reviewApproved => _approval?.approved == true;

  bool get _needsGithubConnect =>
      widget.repository.demo && widget.session?.value == null;

  @override
  void initState() {
    super.initState();
    widget.session?.addListener(_onSession);
    final resumeId = widget.resumeAnalysisId?.trim();
    final hasResume = resumeId != null && resumeId.isNotEmpty;

    if (!hasResume) {
      final cached = widget.cache.read(_cacheKey);
      if (cached != null) {
        _analysis = cached;
        _fromCache = true;
      }
    }

    if (hasResume) {
      final requested = widget.requestedStage;
      if (requested != null) {
        _adoptStage(_normalizeStage(requested));
      }
      return;
    }

    if (_diagnosisReady) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _hydrateArtifacts();
      });
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _applyRequestedStage(widget.requestedStage);
      });
    }
  }

  @override
  void didUpdateWidget(RepairSession oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.session != oldWidget.session) {
      oldWidget.session?.removeListener(_onSession);
      widget.session?.addListener(_onSession);
    }
    if (widget.requestedStage != oldWidget.requestedStage) {
      _applyRequestedStage(widget.requestedStage);
    }
  }

  @override
  void dispose() {
    widget.session?.removeListener(_onSession);
    super.dispose();
  }

  void _onSession() {
    if (mounted) setState(() {});
  }

  void _onDiagnosisUpdate(Analysis? analysis, String? error, bool fromCache) {
    var resetToDiagnosis = false;
    setState(() {
      _analysis = analysis;
      _error = error;
      _fromCache = fromCache;
      if (!_diagnosisReady) {
        resetToDiagnosis = _stage != RepairStage.diagnosis;
        _stage = RepairStage.diagnosis;
        _openedPatch = false;
        _openedValidation = false;
        _openedReview = false;
        _openedPullRequest = false;
        _inspectedSlice = null;
        _showInspector = false;
        _clearArtifacts();
      }
    });
    if (resetToDiagnosis) {
      widget.onStageNormalized?.call(RepairStage.diagnosis);
    }
    if (_diagnosisReady) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _hydrateArtifacts();
      });
    }
  }

  void _clearArtifacts() {
    _proposal = null;
    _validation = null;
    _approval = null;
    _delivery = null;
    _reviewFeedback = null;
    _hydratedForId = null;
    _patchBusy = false;
    _validating = false;
    _delivering = false;
    _approving = false;
    _prError = null;
    _prTitle = null;
    _prDescription = null;
  }

  bool _isMissingArtifact(ApiException error) {
    return error.statusCode == 502 || error.statusCode == 404;
  }

  Future<void> _hydrateArtifacts() async {
    final id = analysisId;
    if (id == null || !_diagnosisReady) return;
    if (_hydratedForId == id) return;
    _hydratedForId = id;

    PatchProposal? proposal;
    PatchValidationResult? validation;
    PatchApproval? approval;
    PatchDelivery? delivery;

    try {
      proposal = await widget.api.getPatch(id);
    } on ApiException catch (e) {
      if (e.statusCode != 409 && !_isMissingArtifact(e)) {
        if (mounted) setState(() => _error = e.message);
        if (mounted) _applyRequestedStage(widget.requestedStage);
        return;
      }
    }

    if (proposal != null) {
      try {
        validation = await widget.api.getPatchValidation(id);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) {
          if (mounted) setState(() => _error = e.message);
          if (mounted) _applyRequestedStage(widget.requestedStage);
          return;
        }
      }
    }

    if (validation != null && validation.isPassed) {
      try {
        approval = await widget.api.getPatchApproval(id);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) {
          if (mounted) setState(() => _error = e.message);
          if (mounted) _applyRequestedStage(widget.requestedStage);
          return;
        }
      }
    }

    if (approval != null && approval.approved) {
      try {
        delivery = await widget.api.getPatchDelivery(id);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) {
          if (mounted) setState(() => _error = e.message);
          if (mounted) _applyRequestedStage(widget.requestedStage);
          return;
        }
      }
    }

    if (!mounted) return;
    setState(() {
      _proposal ??= proposal;
      _validation ??= validation;
      _approval ??= approval;
      _delivery ??= delivery;
    });
    _applyRequestedStage(widget.requestedStage);
  }

  bool _canEnter(RepairStage stage) {
    switch (stage) {
      case RepairStage.diagnosis:
      case RepairStage.issue:
        return true;
      case RepairStage.context:
      case RepairStage.patch:
        return _diagnosisReady;
      case RepairStage.validation:
        return _patchReady;
      case RepairStage.review:
        return _validationPassed;
      case RepairStage.pullRequest:
        return _validationPassed && _reviewApproved;
    }
  }

  String _lockedMessage(RepairStage stage) {
    switch (stage) {
      case RepairStage.patch:
      case RepairStage.context:
        return 'Complete diagnosis before opening Patch.';
      case RepairStage.validation:
        return 'Generate a patch before opening Validation.';
      case RepairStage.review:
        return 'Validation must pass before opening Review.';
      case RepairStage.pullRequest:
        if (!_validationPassed) {
          return 'Validation must pass before opening the Pull Request.';
        }
        return 'Approve the patch before opening the Pull Request.';
      case RepairStage.diagnosis:
      case RepairStage.issue:
        return 'This stage is not available yet.';
    }
  }

  void _afterBuild(VoidCallback action) {
    final phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.idle ||
        phase == SchedulerPhase.postFrameCallbacks) {
      action();
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) action();
    });
  }

  void _showSnack(String message) {
    _afterBuild(() {
      final messenger = ScaffoldMessenger.maybeOf(context);
      if (messenger == null) return;
      messenger
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Text(
              message,
              style: const TextStyle(color: AppTheme.text),
            ),
            duration: const Duration(seconds: 3),
            behavior: SnackBarBehavior.floating,
            backgroundColor: AppTheme.surfaceAlt,
          ),
        );
    });
  }

  void _selectStage(RepairStage stage) {
    if (stage == RepairStage.context) stage = RepairStage.patch;
    if (stage == _stage) return;
    if (!_canEnter(stage)) {
      _showSnack(_lockedMessage(stage));
      return;
    }

    setState(() {
      _stage = stage;
      _inspectedSlice = null;
      _showInspector = false;
      if (stage == RepairStage.patch) _openedPatch = true;
      if (stage == RepairStage.validation) _openedValidation = true;
      if (stage == RepairStage.review) _openedReview = true;
      if (stage == RepairStage.pullRequest) _openedPullRequest = true;
    });
    widget.onStageCommitted?.call(stage);
  }

  RepairStage _furthestAllowed() {
    var allowed = RepairStage.diagnosis;
    for (final stage in _workflowStages) {
      if (_canEnter(stage)) allowed = stage;
    }
    return allowed;
  }

  RepairStage _normalizeStage(RepairStage stage) {
    if (stage == RepairStage.context) return RepairStage.patch;
    if (stage == RepairStage.issue) return RepairStage.diagnosis;
    return stage;
  }

  void _adoptStage(RepairStage stage) {
    _stage = stage;
    _inspectedSlice = null;
    _showInspector = false;
    if (stage == RepairStage.patch) _openedPatch = true;
    if (stage == RepairStage.validation) _openedValidation = true;
    if (stage == RepairStage.review) _openedReview = true;
    if (stage == RepairStage.pullRequest) _openedPullRequest = true;
  }

  void _applyRequestedStage(RepairStage? requested) {
    if (requested == null) return;
    final stage = _normalizeStage(requested);
    if (stage == _stage) return;
    if (!_canEnter(stage)) {
      final allowed = _furthestAllowed();
      _showSnack(_lockedMessage(stage));
      _afterBuild(() => widget.onStageNormalized?.call(allowed));
      return;
    }
    setState(() => _adoptStage(stage));
  }

  Set<RepairStage> get _completedStages {
    final completed = <RepairStage>{};
    if (_diagnosisReady) completed.add(RepairStage.diagnosis);
    if (_patchReady) completed.add(RepairStage.patch);
    if (_validationPassed) completed.add(RepairStage.validation);
    if (_reviewApproved) completed.add(RepairStage.review);
    if (_delivery?.isSucceeded == true) completed.add(RepairStage.pullRequest);
    return completed;
  }

  RepairStage? get _continueTarget {
    final index = _workflowStages.indexOf(_stage);
    if (index < 0 || index >= _workflowStages.length - 1) return null;
    return _workflowStages[index + 1];
  }

  bool get _currentStageSuccessfullyComplete {
    if (_workflowBusy) return false;

    switch (_stage) {
      case RepairStage.diagnosis:
        if (_statusBarLoading) return false;
        final analysis = _analysis;
        if (analysis == null) return false;
        if (analysis.status == AnalysisStatus.failed) return false;
        return _diagnosisReady;
      case RepairStage.patch:
        return _patchReady;
      case RepairStage.validation:
        return _validationPassed;
      case RepairStage.review:
        return _reviewApproved;
      case RepairStage.pullRequest:
        return false;
      case RepairStage.issue:
      case RepairStage.context:
        return false;
    }
  }

  bool get _showContinue {
    // Pull Request is terminal — never offer Continue once a PR exists
    // or while already on the PR stage.
    if (_stage == RepairStage.pullRequest) return false;
    if (_delivery?.isSucceeded == true) return false;
    final target = _continueTarget;
    if (target == null) return false;
    if (!_currentStageSuccessfullyComplete) return false;
    return _canEnter(target);
  }

  void _continueToNextStage() {
    final target = _continueTarget;
    if (target == null || !_showContinue) return;
    _selectStage(target);
  }

  void _onPatchArtifacts(
    PatchProposal? proposal,
    PatchValidationResult? validation,
    PatchApproval? approval,
    PatchDelivery? delivery,
  ) {
    setState(() {
      final regenerated = proposal != _proposal && validation == null;
      _proposal = proposal;
      _validation = validation;
      _approval = approval;
      _delivery = delivery;
      if (regenerated) _reviewFeedback = null;
    });
  }

  void _onPatchBusy(bool busy) {
    if (_patchBusy == busy) return;
    setState(() => _patchBusy = busy);
  }

  void _onValidationChanged(PatchValidationResult? result) {
    if (_validation == result) return;
    setState(() => _validation = result);
  }

  void _onValidationProposal(PatchProposal? proposal) {
    if (proposal == null || identical(_proposal, proposal)) return;
    setState(() => _proposal = proposal);
  }

  void _onValidating(bool running) {
    if (_validating == running) return;
    setState(() => _validating = running);
  }

  Future<void> _createDraftPr({String? title, String? description}) async {
    if (_needsGithubConnect) return;
    if (_delivering) return;
    if (_validation?.isPassed != true) return;
    if (_approval?.approved != true) return;
    if (_delivery?.isSucceeded == true) return;
    final id = analysisId;
    if (id == null) return;

    final prTitle = (title ?? _prTitle ?? '').trim();
    final prDescription = (description ?? _prDescription ?? '').trim();

    setState(() {
      _delivering = true;
      _prError = null;
      _prTitle = prTitle;
      _prDescription = prDescription;
    });

    try {
      final result = await widget.api.deliverPatch(
        id,
        title: prTitle,
        description: prDescription,
      );
      if (!mounted) return;
      setState(() => _delivery = result);
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.statusCode == 409) {
        try {
          final polled = await _pollDelivery(id);
          if (!mounted) return;
          if (polled != null) {
            setState(() => _delivery = polled);
          } else {
            setState(() => _prError = e.message);
          }
        } on ApiException catch (pollError) {
          if (!mounted) return;
          setState(() => _prError = pollError.message);
        }
      } else {
        PatchDelivery? stored;
        try {
          stored = await widget.api.getPatchDelivery(id);
        } on ApiException {
          stored = null;
        }
        if (!mounted) return;
        setState(() {
          if (stored != null) {
            _delivery = stored;
          } else {
            _prError = e.message;
          }
        });
      }
    } finally {
      if (mounted) setState(() => _delivering = false);
    }
  }

  Future<PatchDelivery?> _pollDelivery(String id) async {
    for (var attempt = 0; attempt < 45; attempt++) {
      try {
        final current = await widget.api.getPatchDelivery(id);
        if (!current.isRunning) return current;
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) rethrow;
      }
      await Future<void>.delayed(const Duration(milliseconds: 1200));
    }
    try {
      return await widget.api.getPatchDelivery(id);
    } on ApiException catch (e) {
      if (_isMissingArtifact(e)) return null;
      rethrow;
    }
  }

  void _viewPullRequest() {
    final url = _delivery?.prUrl?.trim() ?? '';
    if (url.isEmpty) return;
    (widget.redirect ?? GithubRedirect()).open(url);
  }

  Future<void> _approveFromReview() async {
    if (_validation?.isPassed != true) return;
    final id = analysisId;
    if (id == null || _approving) return;

    setState(() => _approving = true);
    try {
      final approval = await widget.api.approvePatch(id);
      if (!mounted) return;
      setState(() {
        _approval = approval;
        _reviewFeedback = null;
        _approving = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _approving = false);
      _showSnack(e.message);
    }
  }

  void _requestChanges(String feedback) {
    setState(() {
      _reviewFeedback = feedback;
      _stage = RepairStage.patch;
      _openedPatch = true;
      _inspectedSlice = null;
      _showInspector = false;
    });
  }

  void _openFile(String path, {int? line, String? reason}) {
    final id = analysisId;
    if (id == null) return;

    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => CodeViewerScreen(
          api: widget.api,
          cache: widget.cache,
          analysisId: id,
          path: path,
          highlightLine: line,
          reason: reason,
        ),
      ),
    );
  }

  void _onInspectSlice(ContextSlice? slice) {
    setState(() {
      _inspectedSlice = slice;
      _showInspector = slice != null;
    });
  }

  ReviewState get _reviewState => ReviewState.fromArtifacts(
    diagnosis: _analysis?.diagnosis,
    proposal: _proposal,
    validation: _validation,
    approved: _reviewApproved,
    feedback: _reviewFeedback,
  );

  PullRequestState get _pullRequestState => PullRequestState.fromArtifacts(
    repository: widget.repository.fullName,
    baseBranch: _headerBranch,
    diagnosis: _analysis?.diagnosis,
    proposal: _proposal,
    validation: _validation,
    approval: _approval,
    delivery: _delivery,
    delivering: _delivering,
    errorMessage: _prError,
  );

  @override
  Widget build(BuildContext context) {
    return RepairShell(
      inspectorPanelWidth: 340,
      header: RepairHeader(
        repositoryFullName: widget.repository.fullName,
        branch: _headerBranch,
        commitSha: _headerCommitSha,
        statusLabel: _headerStatusLabel,
        statusColor: _headerStatusColor,
        isInspectorVisible: _showInspector,
        onToggleInspector: () {
          setState(() {
            _showInspector = !_showInspector;
            if (!_showInspector) _inspectedSlice = null;
          });
        },
      ),
      workflow: RepairWorkflow(
        currentStage: _stage,
        completedStages: _completedStages,
        stages: _workflowStages,
        onStageSelected: _selectStage,
      ),
      content: _buildContent(),
      continueAction: RepairContinueAction(
        visible: _showContinue,
        nextStageLabel: _continueTarget?.label ?? '',
        onContinue: _continueToNextStage,
        accentColor: _stage.accent,
      ),
      inspector: RepairInspector(
        title: _inspectedSlice?.filePath ?? 'Inspector',
        onClose: () {
          setState(() {
            _showInspector = false;
            _inspectedSlice = null;
          });
        },
        child: _inspectorChild(),
      ),
      showInspector: _showInspector,
      statusBar: RepairStatusBar(
        statusLabel: _statusBarLabel,
        supportingText: _statusBarSupportingText,
        statusIcon: _statusBarIcon,
        tone: _statusBarTone,
        isLoading: _statusBarLoading,
      ),
    );
  }

  Widget _buildContent() {
    final id = analysisId;

    return Stack(
      children: [
        Positioned.fill(
          child: Offstage(
            offstage: _stage != RepairStage.diagnosis,
            child: TickerMode(
              enabled: _stage == RepairStage.diagnosis,
              child: DiagnosisScreen(
                api: widget.api,
                cache: widget.cache,
                repository: widget.repository,
                issue: widget.issue,
                ref: widget.ref,
                resumeAnalysisId: widget.resumeAnalysisId,
                onBack: widget.onBack,
                onSessionUpdate: _onDiagnosisUpdate,
              ),
            ),
          ),
        ),
        if (id != null && _openedPatch)
          Positioned.fill(
            child: Offstage(
              offstage: _stage != RepairStage.patch,
              child: TickerMode(
                enabled: _stage == RepairStage.patch,
                child: _PatchStage(
                  key: ValueKey('patch-$id'),
                  api: widget.api,
                  cache: widget.cache,
                  repository: widget.repository,
                  issue: widget.issue,
                  analysisId: id,
                  commitSha: _analysis?.commitSha,
                  requestedRef: widget.ref,
                  onOpenFile: _openFile,
                  onInspectSlice: _onInspectSlice,
                  onBack: () => _selectStage(RepairStage.diagnosis),
                  onArtifactsChanged: _onPatchArtifacts,
                  onBusyChanged: _onPatchBusy,
                ),
              ),
            ),
          ),
        if (id != null && _openedValidation)
          Positioned.fill(
            child: Offstage(
              offstage: _stage != RepairStage.validation,
              child: TickerMode(
                enabled: _stage == RepairStage.validation,
                child: ValidationScreen(
                  key: ValueKey('validation-$id'),
                  api: widget.api,
                  analysisId: id,
                  initialProposal: _proposal,
                  initialValidation: _validation,
                  onProposalChanged: _onValidationProposal,
                  onValidationChanged: _onValidationChanged,
                  onRunningChanged: _onValidating,
                ),
              ),
            ),
          ),
        if (id != null && _openedReview)
          Positioned.fill(
            child: Offstage(
              offstage: _stage != RepairStage.review,
              child: TickerMode(
                enabled: _stage == RepairStage.review,
                child: ReviewScreen(
                  key: ValueKey('review-$id'),
                  state: _reviewState,
                  onApprove: _approveFromReview,
                  onRequestChanges: _requestChanges,
                  onFileTap: (file) => _openFile(
                    file.path,
                    line: file.highlightLine,
                    reason: 'Changed in the proposed patch',
                  ),
                ),
              ),
            ),
          ),
        if (id != null && _openedPullRequest)
          Positioned.fill(
            child: Offstage(
              offstage: _stage != RepairStage.pullRequest,
              child: TickerMode(
                enabled: _stage == RepairStage.pullRequest,
                child: PullRequestScreen(
                  key: ValueKey('pr-$id'),
                  state: _pullRequestState,
                  needsGithubConnect: _needsGithubConnect,
                  onConnectGithub: widget.onConnectGithub == null
                      ? null
                      : () => widget.onConnectGithub!(
                          analysisId: analysisId,
                          stage: AppRoutes.segmentFor(_stage),
                        ),
                  onCreatePr: (title, description) {
                    _createDraftPr(title: title, description: description);
                  },
                  onRetry: () => _createDraftPr(),
                  onViewPr: (_delivery?.prUrl ?? '').trim().isEmpty
                      ? null
                      : _viewPullRequest,
                  onReturnToIssues: widget.onBack,
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _inspectorChild() {
    final slice = _inspectedSlice;
    if (slice == null) {
      return const Text(
        'Evidence will appear here',
        style: TextStyle(color: AppTheme.textMuted, fontSize: 12.5),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('TIER', style: AppTypography.sectionLabel),
        const SizedBox(height: 4),
        Text(
          '${slice.tier.code} · ${slice.tier.label}',
          style: const TextStyle(
            fontSize: 12.5,
            height: 1.45,
            color: AppTheme.text,
          ),
        ),
        const SizedBox(height: 14),
        if (slice.relevanceScore != null) ...[
          Text('RELEVANCE SCORE', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          Text(
            slice.relevanceScore!.toStringAsFixed(2),
            style: const TextStyle(
              fontSize: 12.5,
              height: 1.45,
              color: AppTheme.text,
            ),
          ),
          const SizedBox(height: 14),
        ],
        if (slice.hasLineRange) ...[
          Text('LINE RANGE', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          Text(
            slice.lineRangeLabel,
            style: const TextStyle(
              fontSize: 12.5,
              height: 1.45,
              color: AppTheme.text,
            ),
          ),
          const SizedBox(height: 14),
        ],
        Text('REASON', style: AppTypography.sectionLabel),
        const SizedBox(height: 4),
        Text(
          slice.reason,
          style: const TextStyle(
            fontSize: 12.5,
            height: 1.45,
            color: AppTheme.text,
          ),
        ),
        if (slice.symbols.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text('SYMBOLS', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          Text(
            slice.symbols.join(', '),
            style: const TextStyle(
              fontSize: 12.5,
              height: 1.45,
              color: AppTheme.text,
            ),
          ),
        ],
        if (slice.truncated) ...[
          const SizedBox(height: 14),
          Text('STATE', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          const Text(
            'Truncated',
            style: TextStyle(
              fontSize: 12.5,
              height: 1.45,
              color: AppTheme.text,
            ),
          ),
        ],
        if (slice.omitted) ...[
          const SizedBox(height: 14),
          Text('STATE', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          const Text(
            'Omitted',
            style: TextStyle(
              fontSize: 12.5,
              height: 1.45,
              color: AppTheme.text,
            ),
          ),
        ],
        if (slice.content != null && slice.content!.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text('SNIPPET', style: AppTypography.sectionLabel),
          const SizedBox(height: 4),
          Text(
            slice.content!,
            style: const TextStyle(
              fontFamily: AppTheme.mono,
              fontSize: 11.5,
              height: 1.5,
              color: AppTheme.textMuted,
            ),
          ),
        ],
      ],
    );
  }

  String get _headerBranch {
    final requested = widget.ref?.trim();
    if (requested != null && requested.isNotEmpty) return requested;
    final resolved = _analysis?.ref?.trim();
    if (resolved != null && resolved.isNotEmpty) return resolved;
    return 'HEAD';
  }

  String get _headerCommitSha => (_analysis?.commitSha ?? '').trim();

  String get _headerStatusLabel {
    if (_error != null &&
        (_analysis == null || _analysis!.status == AnalysisStatus.failed)) {
      return 'Analysis failed';
    }
    final analysis = _analysis;
    if (analysis == null) return '';
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return '';
      case AnalysisStatus.completed:
        return 'Analysis complete';
      case AnalysisStatus.failed:
        return 'Analysis failed';
    }
  }

  Color get _headerStatusColor {
    if (_error != null && _analysis == null) return AppTheme.danger;
    final analysis = _analysis;
    if (analysis == null) return AppTheme.accent;
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return AppTheme.accent;
      case AnalysisStatus.completed:
        return AppTheme.success;
      case AnalysisStatus.failed:
        return AppTheme.danger;
    }
  }

  bool get _workflowBusy =>
      _delivering || _validating || _patchBusy || _approving;

  String get _statusBarLabel {
    if (_delivering) return 'Opening draft PR';
    if (_validating) return 'Running validation';
    if (_approving) return 'Approving patch';
    if (_patchBusy) return 'Working on patch';
    if (_error != null && _analysis == null) return 'Analysis failed';
    final analysis = _analysis;
    if (analysis == null) return 'Analyzing';
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return 'Analyzing';
      case AnalysisStatus.completed:
        return 'Analysis complete';
      case AnalysisStatus.failed:
        return 'Analysis failed';
    }
  }

  String? get _statusBarSupportingText {
    if (_workflowBusy) return null;
    if (_error != null && _analysis == null) return _error;
    final analysis = _analysis;
    if (analysis == null) return 'Starting analysis';
    if (analysis.status == AnalysisStatus.queued ||
        analysis.status == AnalysisStatus.running) {
      return analysis.stageLabel;
    }
    if (analysis.status == AnalysisStatus.failed) {
      return analysis.error;
    }
    if (analysis.status == AnalysisStatus.completed && _fromCache) {
      return 'Showing the result from earlier in this session';
    }
    return null;
  }

  RepairStatusTone get _statusBarTone {
    if (_delivering || _validating || _approving || _patchBusy) {
      return RepairStatusTone.accent;
    }
    if (_error != null && _analysis == null) return RepairStatusTone.danger;
    final analysis = _analysis;
    if (analysis == null) return RepairStatusTone.accent;
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return RepairStatusTone.accent;
      case AnalysisStatus.completed:
        return RepairStatusTone.success;
      case AnalysisStatus.failed:
        return RepairStatusTone.danger;
    }
  }

  bool get _statusBarLoading {
    if (_workflowBusy) return true;
    if (_error != null) return false;
    final analysis = _analysis;
    if (analysis == null) return true;
    return analysis.status == AnalysisStatus.queued ||
        analysis.status == AnalysisStatus.running;
  }

  IconData? get _statusBarIcon {
    if (_statusBarLoading) return null;
    if (_error != null && _analysis == null) return Icons.error_outline;
    final analysis = _analysis;
    if (analysis == null) return null;
    switch (analysis.status) {
      case AnalysisStatus.completed:
        return Icons.check_circle_outline;
      case AnalysisStatus.failed:
        return Icons.error_outline;
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return null;
    }
  }
}

class _PatchStage extends StatelessWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final Repository repository;
  final Issue issue;
  final String analysisId;
  final String? commitSha;
  final String? requestedRef;
  final void Function(String path, {int? line, String? reason}) onOpenFile;
  final ValueChanged<ContextSlice?> onInspectSlice;
  final VoidCallback onBack;
  final void Function(
    PatchProposal? proposal,
    PatchValidationResult? validation,
    PatchApproval? approval,
    PatchDelivery? delivery,
  )?
  onArtifactsChanged;
  final ValueChanged<bool>? onBusyChanged;

  const _PatchStage({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.analysisId,
    required this.onOpenFile,
    required this.onInspectSlice,
    required this.onBack,
    this.commitSha,
    this.requestedRef,
    this.onArtifactsChanged,
    this.onBusyChanged,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContextScreen(
            api: api,
            cache: cache,
            repository: repository,
            issue: issue,
            analysisId: analysisId,
            ref: requestedRef,
            onBack: onBack,
            onInspectedSliceChanged: onInspectSlice,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 28),
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1040),
                child: PatchPanel(
                  api: api,
                  analysisId: analysisId,
                  commitSha: commitSha,
                  requestedRef: requestedRef,
                  onOpenFile: onOpenFile,
                  onArtifactsChanged: onArtifactsChanged,
                  onBusyChanged: onBusyChanged,
                  showLifecycleActions: false,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
