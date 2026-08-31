import 'api_http_stub.dart'
    if (dart.library.js_interop) 'api_http_web.dart';

import 'package:http/http.dart' as http;

http.Client createApiHttpClient() => createApiHttpClientImpl();
