import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

class RepairShell extends StatelessWidget {
  const RepairShell({
    super.key,
    required this.header,
    required this.workflow,
    required this.content,
    required this.statusBar,
    this.inspector,
    this.showInspector = true,
    this.workflowRailWidth = 240,
    this.inspectorPanelWidth = 320,
    this.collapseInspectorBreakpoint = 1100,
  });

  final Widget header;
  final Widget workflow;
  final Widget content;
  final Widget statusBar;
  final Widget? inspector;
  final bool showInspector;
  final double workflowRailWidth;
  final double inspectorPanelWidth;
  final double collapseInspectorBreakpoint;

  bool _shouldShowInspector(double availableWidth) {
    if (inspector == null || !showInspector) return false;
    return availableWidth >= collapseInspectorBreakpoint;
  }

  @override
  Widget build(BuildContext context) {
    final borderColor = AppTheme.border;

    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Persistent header.
            header,
            Divider(height: 1, thickness: 1, color: borderColor),

            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final inspectorVisible = _shouldShowInspector(
                    constraints.maxWidth,
                  );

                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      // Fixed-width workflow rail.
                      SizedBox(width: workflowRailWidth, child: workflow),
                      VerticalDivider(
                        width: 1,
                        thickness: 1,
                        color: borderColor,
                      ),

                      Expanded(child: ClipRect(child: content)),

                      // Optional inspector panel.
                      if (inspectorVisible) ...[
                        VerticalDivider(
                          width: 1,
                          thickness: 1,
                          color: borderColor,
                        ),
                        SizedBox(width: inspectorPanelWidth, child: inspector),
                      ],
                    ],
                  );
                },
              ),
            ),

            // Persistent bottom status/action bar.
            Divider(height: 1, thickness: 1, color: borderColor),
            statusBar,
          ],
        ),
      ),
    );
  }
}
