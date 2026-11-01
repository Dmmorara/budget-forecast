// The data layer: parsing (IR-05, IR-06), formatting (NFR-10), the HTTP
// client's error mapping (IR-04) and configuration (IR-01). The HTTP tests
// use package:http's MockClient; nothing leaves the process.

import 'dart:async';
import 'dart:convert';

import 'package:budget_forecast_client/config.dart';
import 'package:budget_forecast_client/data/api_exception.dart';
import 'package:budget_forecast_client/data/forecast_api.dart';
import 'package:budget_forecast_client/data/models.dart';
import 'package:budget_forecast_client/data/recent_households.dart';
import 'package:budget_forecast_client/presentation/format.dart';
import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'support.dart';

Decimal d(String s) => Decimal.parse(s);

void main() {
  group('ForecastResult (IR-05, IR-06)', () {
    test('money is parsed into exact decimals', () {
      final r = ForecastResult.fromJson(h015October);
      expect(r.estimatedTotal, d('66284.77'));
      expect(r.low, d('55658.27'));
      expect(r.high, d('75070.63'));
      expect(r.breakdown['Groceries'], d('13627.6'));
      expect(r.riskFlag, isNull);
      expect(r.isSynthetic, isTrue);
    });

    test('the breakdown sums exactly to the total, with no float drift', () {
      final r = ForecastResult.fromJson(h015October);
      expect(sum(r.breakdown.values), r.estimatedTotal);
    });

    test('categories are ordered largest first', () {
      final names = ForecastResult.fromJson(h015October).breakdownLargestFirst
          .map((e) => e.key)
          .toList();
      expect(names.take(3), ['Rent', 'Groceries', 'School Fees']);
      expect(names.last, 'Electronics Upgrade');
    });

    test('every flag in the closed set is accepted', () {
      expect(
        ForecastResult.fromJson(withFlag('insufficient_history')).riskFlag,
        RiskFlag.insufficientHistory,
      );
      expect(
        ForecastResult.fromJson(withFlag('volatile')).riskFlag,
        RiskFlag.volatile,
      );
      expect(
        ForecastResult.fromJson(withFlag('overspend_risk')).riskFlag,
        RiskFlag.overspendRisk,
      );
    });

    test('a flag outside the closed set is an error, not text to display', () {
      expect(
        () => ForecastResult.fromJson(withFlag('mild_concern')),
        throwsA(
          isA<ApiException>()
              .having((e) => e.kind, 'kind', ApiErrorKind.server)
              .having((e) => e.message, 'message', contains('mild_concern')),
        ),
      );
    });

    test('insufficient history has no range', () {
      final r = ForecastResult.fromJson(insufficient);
      expect(r.hasRange, isFalse);
      expect(r.breakdown, isEmpty);
    });

    test('a non-numeric amount is an error', () {
      expect(
        () =>
            ForecastResult.fromJson({...h015October, 'estimatedTotal': 'lots'}),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('BudgetResult', () {
    test('parses allocations, keeping a declared zero', () {
      final b = BudgetResult.fromJson(h015Budget);
      expect(b.allocated['Rent'], d('21499'));
      expect(b.allocated['Electronics Upgrade'], Decimal.zero);
      expect(b.isEmpty, isFalse);
    });

    test('an unknown household is an empty budget, not an error', () {
      expect(BudgetResult.fromJson(emptyBudget).isEmpty, isTrue);
    });
  });

  group('YearMonth', () {
    test('steps across year boundaries', () {
      expect(const YearMonth(2026, 12).plus(1), const YearMonth(2027, 1));
      expect(const YearMonth(2026, 1).plus(-1), const YearMonth(2025, 12));
      expect(const YearMonth(2026, 10).plus(-3), const YearMonth(2026, 7));
    });

    test('parses DATA_LAST_MONTH', () {
      expect(YearMonth.tryParse('2026-09'), const YearMonth(2026, 9));
      expect(YearMonth.tryParse('2026-9'), const YearMonth(2026, 9));
      expect(YearMonth.tryParse(''), isNull);
      expect(YearMonth.tryParse('2026-13'), isNull);
      expect(YearMonth.tryParse('September'), isNull);
    });
  });

  group('kes (NFR-10)', () {
    test('Kenyan shillings with thousands separators', () {
      expect(kes(d('66284.77')), 'KSh 66,285');
      expect(kes(d('1234567.49')), 'KSh 1,234,567');
      expect(kes(d('999')), 'KSh 999');
      expect(kes(d('1000')), 'KSh 1,000');
      expect(kes(Decimal.zero), 'KSh 0');
    });
  });

  group('AppConfig (IR-01)', () {
    test('accepts an absolute http(s) URL and drops a trailing slash', () {
      expect(
        AppConfig.parseApiUrl('https://x.onrender.com/').toString(),
        'https://x.onrender.com',
      );
      expect(
        AppConfig.parseApiUrl(' http://localhost:8000 ').toString(),
        'http://localhost:8000',
      );
    });

    test('rejects a missing or relative address', () {
      expect(AppConfig.parseApiUrl(''), isNull);
      expect(AppConfig.parseApiUrl('localhost:8000'), isNull);
      expect(AppConfig.parseApiUrl('/api'), isNull);
    });
  });

  group('ForecastApiClient (IR-04)', () {
    final base = Uri.parse('https://bf.example.com');

    ForecastApiClient client(
      MockClientHandler handler, {
      Duration timeout = ForecastApiClient.defaultTimeout,
    }) => ForecastApiClient(
      baseUrl: base,
      client: MockClient(handler),
      timeout: timeout,
    );

    test('POSTs the three required fields as JSON', () async {
      late http.Request sent;
      final api = client((request) async {
        sent = request;
        return http.Response(jsonEncode(h015October), 200);
      });
      final r = await api.getForecast('h015', 10, 2026);
      expect(sent.method, 'POST');
      expect(sent.url.toString(), 'https://bf.example.com/forecast');
      expect(sent.headers['Content-Type'], startsWith('application/json'));
      expect(jsonDecode(sent.body), {
        'userId': 'h015',
        'month': 10,
        'year': 2026,
      });
      expect(r.estimatedTotal, d('66284.77'));
    });

    test('GETs the budget with the id as a query parameter', () async {
      late Uri url;
      final api = client((request) async {
        url = request.url;
        return http.Response(jsonEncode(emptyBudget), 200);
      });
      final b = await api.getBudget('h 015');
      expect(url.path, '/budget');
      expect(url.queryParameters['userId'], 'h 015');
      expect(b.isEmpty, isTrue);
    });

    test('422 is a validation error naming the field', () async {
      final api = client(
        (_) async => http.Response(
          jsonEncode({
            'detail': [
              {
                'type': 'less_than_equal',
                'loc': ['body', 'month'],
                'msg': 'Input should be less than or equal to 12',
              },
            ],
          }),
          422,
        ),
      );
      await expectLater(
        api.getForecast('h015', 13, 2026),
        throwsA(
          isA<ApiException>()
              .having((e) => e.kind, 'kind', ApiErrorKind.validation)
              .having((e) => e.field, 'field', 'month'),
        ),
      );
    });

    test('5xx is a server error', () async {
      final api = client((_) async => http.Response('Bad gateway', 502));
      await expectLater(
        api.getForecast('h015', 10, 2026),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.server,
          ),
        ),
      );
    });

    test('a refused connection is a network error', () async {
      final api = client(
        (_) async => throw http.ClientException('Connection refused'),
      );
      await expectLater(
        api.getBudget('h015'),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.network,
          ),
        ),
      );
    });

    test('no answer within the limit is a timeout', () async {
      final never = Completer<http.Response>();
      final api = client(
        (_) => never.future,
        timeout: const Duration(milliseconds: 20),
      );
      await expectLater(
        api.getForecast('h015', 10, 2026),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.timeout,
          ),
        ),
      );
    });

    test('the default limit is 60 seconds', () {
      expect(ForecastApiClient.defaultTimeout, const Duration(seconds: 60));
    });

    test('a non-JSON 200 is a server error', () async {
      final api = client((_) async => http.Response('<html>', 200));
      await expectLater(
        api.getForecast('h015', 10, 2026),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.server,
          ),
        ),
      );
    });
  });

  group('recent households (IR-07)', () {
    test(
      'keeps the five most recent ids, newest first, without repeats',
      () async {
        final store = InMemoryRecentHouseholds(['h001', 'h002']);
        await store.add('h002');
        for (final id in ['h003', 'h004', 'h005', 'h006']) {
          await store.add(id);
        }
        expect(await store.load(), ['h006', 'h005', 'h004', 'h003', 'h002']);
      },
    );
  });
}
