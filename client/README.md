# budget-forecast client — U-CS 37

The Flutter app for the budget-forecast service. One Dart codebase, built for
Android and the web (NFR-06), and also for iOS. Chapter 4 of the report is the specification:
FR-10 to FR-16, IR-01 to IR-07, NFR-10 and wireframes 4.12 to 4.14.

**All figures are synthetic.** Every forecast screen says so (FR-16).

## Run it locally

Two terminals, from the repository root.

**1. The service, allowing the client's origin.** The service allows no
cross-origin browser calls unless told to (IR-02), so the web client fails
with a CORS error until this is set:

```bash
docker build -t budget-forecast .
docker run --rm -e PORT=8000 -e CORS_ALLOWED_ORIGINS=http://localhost:5050 \
  -p 8000:8000 budget-forecast
```

Use the container rather than `uvicorn` here. The image holds only
`data/public/`, whose households are **h001 to h060**, the same as the
deployment. A local `uvicorn` prefers the full extract in `data/` when it is
present, and that uses platform UUIDs, so `h015` would come back as
"no forecast can be made yet".

**2. The client, on a fixed port:**

```bash
cd client
flutter run -d chrome --web-port=5050 \
  --dart-define=FORECAST_API_URL=http://localhost:8000 \
  --dart-define=DATA_LAST_MONTH=2026-09
```

Try `h015` for October 2026: it should show *likely between KSh 55,658 and
KSh 75,071*, matching Figure 4.10.

Three things that cost time if you do not know them:

- **Not port 5000 on a Mac.** macOS's AirPlay Receiver listens on 5000 for
  both IPv4 and IPv6, so the browser reaches AirPlay (HTTP 403) instead of the
  app. Any free fixed port works, as long as `CORS_ALLOWED_ORIGINS` names the
  same one.
- **Open `localhost`, not `127.0.0.1`.** They are different origins to a
  browser; only the one in `CORS_ALLOWED_ORIGINS` is allowed. A CORS refusal
  shows in the app as "Cannot reach the service".
- **The port must be fixed.** `flutter run` picks a random port otherwise, and
  the CORS setting would never match it.

## Configuration

Both are build-time `--dart-define`s. Nothing is hard-coded.

| define | meaning |
|---|---|
| `FORECAST_API_URL` | IR-01. The service's base URL. Without it the app shows a "no service address" screen and makes no calls. |
| `DATA_LAST_MONTH` | `YYYY-MM`, the last month the service has data for (`2026-09` for the current slice). Used only to draw later months dashed in the month comparison (FR-14). |

**`DATA_LAST_MONTH` is a workaround.** No endpoint exposes the end of the
data, so the client is told at build time and must be rebuilt if the extract
changes. The real fix is a field on an existing response, which is a contract
change to agree with the consuming teams first.

## Build

```bash
flutter build web --dart-define=FORECAST_API_URL=https://<service>.onrender.com \
  --dart-define=DATA_LAST_MONTH=2026-09
flutter build apk --dart-define=FORECAST_API_URL=https://<service>.onrender.com \
  --dart-define=DATA_LAST_MONTH=2026-09
```

The APK needs an **https** URL: Android blocks cleartext HTTP, and this app
does not turn that off. To try a debug build on an emulator against a local
service, use `http://10.0.2.2:8000` with `flutter run` (debug builds only).

**iOS** is run from Xcode. Xcode does not take `--dart-define`, so write the
defines into the generated config first, then open `ios/Runner.xcworkspace`:

```bash
flutter build ios --config-only \
  --dart-define=FORECAST_API_URL=http://localhost:8000 \
  --dart-define=DATA_LAST_MONTH=2026-09
```

Re-run it whenever a define changes. `flutter run -d <simulator>` with the
same defines also works without Xcode.
`Info.plist` allows cleartext HTTP to local hosts only
(`NSAllowsLocalNetworking`), so the simulator can reach
`http://localhost:8000`; every other host needs https, and the Render URL
needs nothing. On a physical iPhone, `localhost` is the phone, so use the
Mac's address. CI does not build iOS: macOS runners cost ten times Linux
minutes.

For the deployed web app, set the service's `CORS_ALLOWED_ORIGINS` to the web
app's own origin, e.g. `https://<flutter-web-host>`.

## Test

```bash
flutter analyze
flutter test
```

The widget tests run against a fake API client built from the service's
real responses. No test makes a network call. CI runs both on every pull
request that touches `client/`.

## Structure (§4.4.3)

```
lib/
  config.dart                  --dart-define values
  data/                        the only layer that speaks HTTP
    forecast_api.dart          ForecastApi, ForecastApiClient (60 s timeout)
    models.dart                ForecastResult, BudgetResult, RiskFlag, money as Decimal
    api_exception.dart         timeout | network | validation | server
    recent_households.dart     the only thing stored on the device (IR-07)
  state/
    forecast_controller.dart   ChangeNotifier; the state machine of Figure 4.8
  presentation/
    shell.dart                 bottom navigation on phones, side panel from 900 px
    screens/                   household, dashboard, breakdown, budget, comparison
    widgets/common.dart        synthetic notice, loading/waking, error, insufficient history
```

How the specification maps onto the code:

- **Figure 4.8's states.** `LoadState` is `idle | loading | loaded | error`.
  "Loaded, flagged" is `loaded` with a `riskFlag` set. "Waking up" is a flag
  that turns on during `loading` after 5 seconds; it is not a separate state.
- **FR-13: forecast over budget.** Computed in the client by
  `ForecastController.categoriesOverBudget`. The service does not flag
  overspending, and its reserved `overspend_risk` flag is never emitted.
- **FR-14: which months are dashed.** Months after the one straight after the
  data ends. With data to September, October is the real forecast (solid) and
  November adds nothing new (dashed), as in wireframe 4.14e.
