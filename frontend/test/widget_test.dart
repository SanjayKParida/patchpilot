import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/main.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/widgets/common.dart';

void main() {
  testWidgets('landing screen offers the demo without GitHub login',
      (tester) async {
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.url.path.endsWith('/auth/me')) {
          return http.Response(
            jsonEncode({'authenticated': false, 'user': null}),
            200,
            headers: const {'content-type': 'application/json; charset=utf-8'},
          );
        }
        if (request.url.path.endsWith('/repositories/demo')) {
          return http.Response(
            jsonEncode({
              'owner': 'SanjayKParida',
              'repo': 'patchpilot-diagnosis-demo',
              'full_name': 'SanjayKParida/patchpilot-diagnosis-demo',
              'description': 'Try PatchPilot on prepared issues',
              'demo': true,
            }),
            200,
            headers: const {'content-type': 'application/json; charset=utf-8'},
          );
        }
        return http.Response('nope', 404);
      }),
    );

    await tester.pumpWidget(PatchPilotApp(api: api));
    await tester.pumpAndSettle();

    expect(find.text('PatchPilot'), findsOneWidget);
    expect(find.text('Open Demo'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Connect GitHub'), findsOneWidget);
  });

  testWidgets('short text does not show a more control', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 400,
            child: ExpandableText(text: 'A short issue body.'),
          ),
        ),
      ),
    );

    expect(find.text('Show more'), findsNothing);
  });

  testWidgets('long text collapses then expands', (tester) async {
    final body = List.generate(
      10,
      (i) => 'Line ${i + 1} of a long issue description.',
    ).join('\n');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 400,
            child: ExpandableText(text: body, maxLines: 5),
          ),
        ),
      ),
    );

    expect(find.text('Show more'), findsOneWidget);

    await tester.tap(find.text('Show more'));
    await tester.pump();

    expect(find.text('Show less'), findsOneWidget);
    expect(find.text('Show more'), findsNothing);
  });
}
