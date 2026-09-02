import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';

// Dashboard-only cards and rows. State and API calls stay on
// DashboardScreen.

class UserChip extends StatelessWidget {
  final AuthUser user;

  const UserChip({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (user.avatarUrl.isNotEmpty)
          CircleAvatar(
            radius: 12,
            backgroundImage: NetworkImage(user.avatarUrl),
          )
        else
          const CircleAvatar(
            radius: 12,
            backgroundColor: AppTheme.surfaceAlt,
            child: Icon(Icons.person_outline, size: 14),
          ),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              user.githubLogin,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            const Text(
              'Connected',
              style: TextStyle(fontSize: 11, color: AppTheme.success),
            ),
          ],
        ),
      ],
    );
  }
}

class DemoCard extends StatelessWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const DemoCard({super.key, required this.repository, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    return Panel(
      background: const Color(0xFF141A28),
      borderColor: AppTheme.accent.withValues(alpha: 0.45),
      padding: const EdgeInsets.all(24),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: AppTheme.accent.withValues(alpha: 0.16),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Text(
                        'Demo',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.4,
                          color: AppTheme.accent,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        repository.fullName,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  repository.description ?? 'Try PatchPilot on prepared issues',
                  style: const TextStyle(
                    fontSize: 13.5,
                    height: 1.5,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(onPressed: onOpen, child: const Text('Open Demo')),
        ],
      ),
    );
  }
}

class ConnectCard extends StatelessWidget {
  final bool connecting;
  final VoidCallback onConnect;

  const ConnectCard({
    super.key,
    required this.connecting,
    required this.onConnect,
  });

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: const EdgeInsets.all(24),
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Connect GitHub',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
                SizedBox(height: 6),
                Text(
                  'Authorize PatchPilot and choose the repositories it may use.',
                  style: TextStyle(
                    fontSize: 13.5,
                    height: 1.5,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(
            onPressed: connecting ? null : onConnect,
            child: connecting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Connect GitHub'),
          ),
        ],
      ),
    );
  }
}

class AuthorizedList extends StatelessWidget {
  final bool loading;
  final bool managing;
  final TextEditingController controller;
  final List<Repository> repositories;
  final ValueChanged<String> onQuery;
  final void Function(Repository) onOpen;
  final VoidCallback onManage;

  const AuthorizedList({
    super.key,
    required this.loading,
    required this.managing,
    required this.controller,
    required this.repositories,
    required this.onQuery,
    required this.onOpen,
    required this.onManage,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!loading && repositories.isEmpty)
          SelectRepositoriesCard(managing: managing, onSelect: onManage)
        else
          Panel(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              children: [
                TextField(
                  controller: controller,
                  onChanged: onQuery,
                  decoration: const InputDecoration(
                    hintText: 'Search repositories...',
                    prefixIcon: Icon(Icons.search, color: AppTheme.textMuted),
                  ),
                ),
                const SizedBox(height: 12),
                if (loading)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 32),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else
                  ...repositories.map(
                    (repo) =>
                        RepoRow(repository: repo, onOpen: () => onOpen(repo)),
                  ),
              ],
            ),
          ),
        if (!loading && repositories.isNotEmpty) ...[
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: managing ? null : onManage,
              child: const Text('Manage GitHub access'),
            ),
          ),
        ],
      ],
    );
  }
}

class SelectRepositoriesCard extends StatelessWidget {
  final bool managing;
  final VoidCallback onSelect;

  const SelectRepositoriesCard({
    super.key,
    required this.managing,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Connect a repository',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          const Text(
            'Choose the repositories PatchPilot can access.',
            style: TextStyle(
              fontSize: 13.5,
              height: 1.5,
              color: AppTheme.textMuted,
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: managing ? null : onSelect,
            child: managing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Select repositories on GitHub'),
          ),
        ],
      ),
    );
  }
}

class RepoRow extends StatelessWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const RepoRow({super.key, required this.repository, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final visibility = repository.private ? 'Private' : 'Public';
    final access = repository.canWrite == true
        ? 'Write'
        : repository.canRead == false
        ? 'No access'
        : 'Read';

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: repository.canRead == false ? null : onOpen,
          borderRadius: BorderRadius.circular(10),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              children: [
                Icon(
                  repository.private
                      ? Icons.lock_outline
                      : Icons.folder_outlined,
                  size: 18,
                  color: AppTheme.textMuted,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    repository.fullName,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                Text(
                  visibility,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  access,
                  style: TextStyle(
                    fontSize: 12,
                    color: repository.canWrite == true
                        ? AppTheme.success
                        : AppTheme.textMuted,
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(
                  Icons.chevron_right,
                  size: 18,
                  color: AppTheme.textMuted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
