#!/usr/bin/env bash
# Builds the Flutter web app on Render (§4.4.8). render.yaml's static site
# runs this from client/, its root directory; it writes client/build/web,
# which Render publishes. It works from any directory, since it changes to
# client/ itself. The build output is never committed.
#
# Render's static-site build image has no Flutter, so this fetches the SDK at
# the same version CI pins (.github/workflows/ci.yml). Change both together.
#
# Runs locally too, which is how to check it before Render does:
#
#   FORECAST_API_URL=http://localhost:8000 DATA_LAST_MONTH=2026-09 \
#     bash client/tool/render_build.sh
#
# A local run reuses an SDK already at FLUTTER_HOME, or fetches one there.

set -euo pipefail

# Fail the build rather than publish an app with no service address. Flutter
# would build without it and show the "no service address" screen, which
# looks like a deployed app that does nothing.
: "${FORECAST_API_URL:?set FORECAST_API_URL in the Render dashboard to the service URL}"
: "${DATA_LAST_MONTH:?set DATA_LAST_MONTH (YYYY-MM), the last month the service has data for}"

FLUTTER_VERSION="${FLUTTER_VERSION:-3.47.8}"
FLUTTER_HOME="${FLUTTER_HOME:-$HOME/flutter-$FLUTTER_VERSION}"

if [ ! -x "$FLUTTER_HOME/bin/flutter" ]; then
  echo "Fetching Flutter $FLUTTER_VERSION into $FLUTTER_HOME"
  git clone --depth 1 --branch "$FLUTTER_VERSION" \
    https://github.com/flutter/flutter.git "$FLUTTER_HOME"
fi
export PATH="$FLUTTER_HOME/bin:$PATH"

cd "$(dirname "$0")/.."
flutter --version --suppress-analytics
flutter pub get --suppress-analytics
flutter build web --release --suppress-analytics \
  --dart-define=FORECAST_API_URL="$FORECAST_API_URL" \
  --dart-define=DATA_LAST_MONTH="$DATA_LAST_MONTH"
