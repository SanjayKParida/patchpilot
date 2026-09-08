import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/models/models.dart';

/// Dashboard-only presentation.
///
/// State and API calls stay on DashboardScreen.
class UserChip extends StatelessWidget {
  final AuthUser user;

  const UserChip({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (user.avatarUrl.isNotEmpty)
          CircleAvatar(
            radius: 10,
            backgroundImage: NetworkImage(user.avatarUrl),
          )
        else
          const CircleAvatar(
            radius: 10,
            backgroundColor: AppTheme.surfaceAlt,
            child: Icon(
              Icons.person_outline,
              size: 12,
              color: AppTheme.textMuted,
            ),
          ),
        const SizedBox(width: 8),
        Text(
          user.githubLogin,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}

class _ShimmerPulse extends StatefulWidget {
  final Widget child;

  const _ShimmerPulse({required this.child});

  @override
  State<_ShimmerPulse> createState() => _ShimmerPulseState();
}

class _ShimmerPulseState extends State<_ShimmerPulse>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(
        begin: 0.35,
        end: 0.75,
      ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut)),
      child: widget.child,
    );
  }
}

class ConnectPrompt extends StatelessWidget {
  final bool connecting;
  final VoidCallback onConnect;

  const ConnectPrompt({
    super.key,
    required this.connecting,
    required this.onConnect,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 18, 0, 18),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: AppTheme.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: const Icon(
              Icons.account_tree_outlined,
              size: 17,
              color: AppTheme.textMuted,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Connect GitHub',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                ),
                SizedBox(height: 3),
                Text(
                  'Choose repositories for PatchPilot to work with.',
                  style: TextStyle(fontSize: 11.5, color: AppTheme.textMuted),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              minimumSize: const Size(0, 40),
              textStyle: const TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            onPressed: connecting ? null : onConnect,
            child: connecting
                ? const SizedBox(
                    width: 15,
                    height: 15,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Connect'),
          ),
        ],
      ),
    );
  }
}

class EmptyRepositoriesPrompt extends StatelessWidget {
  final bool managing;
  final VoidCallback onSelect;

  const EmptyRepositoriesPrompt({
    super.key,
    required this.managing,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 18, 0, 18),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: AppTheme.surfaceAlt,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: const Icon(
              Icons.folder_open_outlined,
              size: 17,
              color: AppTheme.textMuted,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'No repositories selected',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                ),
                SizedBox(height: 3),
                Text(
                  'Choose repositories from your GitHub installation.',
                  style: TextStyle(fontSize: 11.5, color: AppTheme.textMuted),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppTheme.surfaceElevated,
              foregroundColor: AppTheme.text,
              disabledBackgroundColor: AppTheme.surfaceAlt,
              disabledForegroundColor: AppTheme.textMuted,
              elevation: 0,
              padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 11),
              minimumSize: const Size(0, 40),
              textStyle: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            onPressed: managing ? null : onSelect,
            child: managing
                ? const SizedBox(
                    width: 15,
                    height: 15,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Select repositories'),
          ),
        ],
      ),
    );
  }
}

class _RepoSearchField extends StatefulWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  const _RepoSearchField({required this.controller, required this.onChanged});

  @override
  State<_RepoSearchField> createState() => _RepoSearchFieldState();
}

class _RepoSearchFieldState extends State<_RepoSearchField> {
  bool _focused = false;

  @override
  Widget build(BuildContext context) {
    return Focus(
      onFocusChange: (hasFocus) {
        setState(() => _focused = hasFocus);
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 140),
        height: 38,
        decoration: BoxDecoration(
          color: _focused ? AppTheme.surfaceElevated : AppTheme.surfaceAlt,
          borderRadius: BorderRadius.circular(7),
          border: Border.all(
            color: _focused
                ? AppTheme.accent.withValues(alpha: 0.65)
                : AppTheme.borderSubtle,
          ),
        ),
        child: TextField(
          controller: widget.controller,
          onChanged: widget.onChanged,
          style: const TextStyle(fontSize: 12.5, fontFamily: AppTheme.mono),
          decoration: const InputDecoration(
            isDense: true,
            border: InputBorder.none,
            enabledBorder: InputBorder.none,
            focusedBorder: InputBorder.none,
            contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 11),
            hintText: 'Search repositories',
            hintStyle: TextStyle(
              fontSize: 12,
              fontFamily: AppTheme.mono,
              color: AppTheme.textMuted,
            ),
            prefixIcon: Icon(Icons.search, size: 15, color: AppTheme.textMuted),
            prefixIconConstraints: BoxConstraints(minWidth: 34, minHeight: 38),
          ),
        ),
      ),
    );
  }
}

class AuthorizedWorkspace extends StatelessWidget {
  final bool loading;
  final bool managing;
  final TextEditingController controller;
  final bool hasAnyRepositories;
  final List<Repository> repositories;
  final int totalCount;
  final String query;
  final ValueChanged<String> onQuery;
  final void Function(Repository) onOpen;
  final VoidCallback onManage;

  const AuthorizedWorkspace({
    super.key,
    required this.loading,
    required this.managing,
    required this.controller,
    required this.hasAnyRepositories,
    required this.repositories,
    required this.totalCount,
    required this.query,
    required this.onQuery,
    required this.onOpen,
    required this.onManage,
  });

  @override
  Widget build(BuildContext context) {
    if (!loading && !hasAnyRepositories) {
      return EmptyRepositoriesPrompt(managing: managing, onSelect: onManage);
    }

    final filtering = query.trim().isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 14, bottom: 10),
          child: Row(
            children: [
              Expanded(
                child: _RepoSearchField(
                  controller: controller,
                  onChanged: onQuery,
                ),
              ),
              if (filtering && !loading) ...[
                const SizedBox(width: 10),
                Container(
                  height: 30,
                  padding: const EdgeInsets.symmetric(horizontal: 9),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppTheme.surfaceAlt,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: AppTheme.borderSubtle),
                  ),
                  child: Text(
                    '${repositories.length}/$totalCount',
                    style: const TextStyle(
                      fontSize: 10.5,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.textMuted,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (loading)
          const RepoListSkeleton()
        else if (repositories.isEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(2, 20, 2, 24),
            child: Row(
              children: [
                const Icon(
                  Icons.search_off_outlined,
                  size: 16,
                  color: AppTheme.textMuted,
                ),
                const SizedBox(width: 8),
                Text(
                  filtering
                      ? 'No matches for "$query".'
                      : 'No repositories to show.',
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          )
        else
          for (var i = 0; i < repositories.length; i++) ...[
            if (i > 0)
              Container(
                height: 1,
                margin: const EdgeInsets.only(left: 44),
                color: AppTheme.borderSubtle,
              ),
            RepoRow(
              repository: repositories[i],
              onOpen: () => onOpen(repositories[i]),
            ),
          ],
      ],
    );
  }
}

class _RowHoverBar extends StatelessWidget {
  final bool hovering;

  const _RowHoverBar({required this.hovering});

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 120),
      opacity: hovering ? 1 : 0,
      child: Container(
        width: 2,
        height: 34,
        decoration: BoxDecoration(
          color: AppTheme.accent,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}

class _RowArrow extends StatelessWidget {
  final bool hovering;
  final bool disabled;

  const _RowArrow({required this.hovering, this.disabled = false});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      transform: Matrix4.translationValues(hovering && !disabled ? 2 : 0, 0, 0),
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 120),
        opacity: disabled ? 0.25 : (hovering ? 1 : 0.4),
        child: Icon(
          Icons.arrow_forward,
          size: 15,
          color: hovering && !disabled ? AppTheme.accent : AppTheme.textMuted,
        ),
      ),
    );
  }
}

class RepoRow extends StatefulWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const RepoRow({super.key, required this.repository, required this.onOpen});

  @override
  State<RepoRow> createState() => _RepoRowState();
}

class _RepoRowState extends State<RepoRow> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    final repository = widget.repository;
    final disabled = repository.canRead == false;
    final canWrite = repository.canWrite == true;
    final description = (repository.description ?? '').trim();

    final accessLabel = canWrite ? 'WRITE' : (disabled ? 'NO ACCESS' : 'READ');

    final accessColor = canWrite ? AppTheme.success : AppTheme.textMuted;

    return MouseRegion(
      cursor: disabled ? SystemMouseCursors.basic : SystemMouseCursors.click,
      onEnter: disabled ? null : (_) => setState(() => _hovering = true),
      onExit: disabled ? null : (_) => setState(() => _hovering = false),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: disabled ? null : widget.onOpen,
          hoverColor: AppTheme.surfaceAlt.withValues(alpha: 0.45),
          splashColor: AppTheme.accent.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(7),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                _RowHoverBar(hovering: _hovering),
                const SizedBox(width: 10),
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: _hovering
                        ? AppTheme.surfaceElevated
                        : AppTheme.surfaceAlt,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(
                    repository.private
                        ? Icons.lock_outline
                        : Icons.folder_outlined,
                    size: 14,
                    color: _hovering ? AppTheme.text : AppTheme.textMuted,
                  ),
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        repository.fullName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13.5,
                          fontFamily: AppTheme.mono,
                          fontWeight: FontWeight.w600,
                          letterSpacing: -0.1,
                          color: disabled ? AppTheme.textMuted : null,
                        ),
                      ),
                      if (description.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          description,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 11.5,
                            color: AppTheme.textMuted,
                            height: 1.25,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 14),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 7,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: canWrite
                        ? AppTheme.success.withValues(alpha: 0.08)
                        : AppTheme.surfaceAlt,
                    borderRadius: BorderRadius.circular(5),
                  ),
                  child: Text(
                    accessLabel,
                    style: TextStyle(
                      fontSize: 9.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.4,
                      color: accessColor,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                _RowArrow(hovering: _hovering, disabled: disabled),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class RepoRowSkeleton extends StatelessWidget {
  const RepoRowSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(width: 2),
          _bar(width: 28, height: 28, radius: 6),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _bar(width: double.infinity, height: 13),
                const SizedBox(height: 6),
                _bar(width: 220, height: 9),
              ],
            ),
          ),
          const SizedBox(width: 14),
          _bar(width: 48, height: 18, radius: 5),
          const SizedBox(width: 10),
          _bar(width: 15, height: 15, radius: 2),
        ],
      ),
    );
  }

  static Widget _bar({
    required double width,
    required double height,
    double radius = 2,
  }) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppTheme.surfaceAlt,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

class RepoListSkeleton extends StatelessWidget {
  final int rows;

  const RepoListSkeleton({super.key, this.rows = 4});

  @override
  Widget build(BuildContext context) {
    return _ShimmerPulse(
      child: Column(
        children: [
          for (var i = 0; i < rows; i++) ...[
            if (i > 0)
              Container(
                height: 1,
                margin: const EdgeInsets.only(left: 44),
                color: AppTheme.borderSubtle,
              ),
            const RepoRowSkeleton(),
          ],
        ],
      ),
    );
  }
}

class DemoRow extends StatefulWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const DemoRow({super.key, required this.repository, required this.onOpen});

  @override
  State<DemoRow> createState() => _DemoRowState();
}

class _DemoRowState extends State<DemoRow> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    final repository = widget.repository;

    final description = (repository.description ?? '').trim().isNotEmpty
        ? repository.description!.trim()
        : 'Run the workflow without connecting GitHub.';

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: InkWell(
        onTap: widget.onOpen,
        hoverColor: Colors.transparent,
        splashColor: AppTheme.accent.withValues(alpha: 0.04),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
          child: Row(
            children: [
              _RowHoverBar(hovering: _hovering),
              const SizedBox(width: 10),
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: AppTheme.surface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppTheme.borderSubtle),
                ),
                child: const Icon(
                  Icons.play_arrow_rounded,
                  size: 15,
                  color: AppTheme.textMuted,
                ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'DEMO',
                          style: TextStyle(
                            fontSize: 9.5,
                            fontFamily: AppTheme.mono,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.7,
                            color: AppTheme.accent,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            repository.fullName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 13,
                              fontFamily: AppTheme.mono,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: AppTheme.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              _RowArrow(hovering: _hovering),
            ],
          ),
        ),
      ),
    );
  }
}

class DemoRowSkeleton extends StatelessWidget {
  const DemoRowSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return _ShimmerPulse(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
        child: Row(
          children: [
            const SizedBox(width: 2),
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: AppTheme.surface,
                borderRadius: BorderRadius.circular(6),
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 190,
                    height: 12,
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Container(
                    width: 260,
                    height: 9,
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Container(
              width: 15,
              height: 15,
              decoration: BoxDecoration(
                color: AppTheme.surface,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
