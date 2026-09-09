import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/app_background.dart';

class RepairShell extends StatelessWidget {
  const RepairShell({
    super.key,
    required this.header,
    required this.workflow,
    required this.content,
    required this.statusBar,
    this.inspector,
    this.continueAction,
    this.showInspector = false,
    this.inspectorPanelWidth = 360,
  });

  final Widget header;
  final Widget workflow;
  final Widget content;
  final Widget statusBar;
  final Widget? inspector;
  final Widget? continueAction;
  final bool showInspector;
  final double inspectorPanelWidth;

  @override
  Widget build(BuildContext context) {
    final inspectorOpen = inspector != null && showInspector;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppBackground(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DecoratedBox(
                decoration: const BoxDecoration(
                  border: Border(
                    bottom: BorderSide(color: AppTheme.borderSubtle),
                  ),
                ),
                child: Column(children: [header, workflow]),
              ),
              Expanded(
                child: Stack(
                  clipBehavior: Clip.hardEdge,
                  children: [
                    Positioned.fill(child: ClipRect(child: content)),
                    if (inspectorOpen)
                      Positioned(
                        top: 0,
                        right: 0,
                        bottom: 0,
                        child: TweenAnimationBuilder<double>(
                          tween: Tween(begin: 0, end: 1),
                          duration: const Duration(milliseconds: 160),
                          curve: Curves.easeOut,
                          builder: (context, t, child) => Transform.translate(
                            offset: Offset((1 - t) * 20, 0),
                            child: Opacity(opacity: t, child: child),
                          ),
                          child: SizedBox(
                            width: inspectorPanelWidth,
                            child: inspector,
                          ),
                        ),
                      ),
                    if (continueAction != null)
                      Positioned(right: 20, bottom: 20, child: continueAction!),
                  ],
                ),
              ),
              DecoratedBox(
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: AppTheme.borderSubtle)),
                ),
                child: statusBar,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
