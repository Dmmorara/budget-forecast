# Running the service and the client locally

The service in a container, the Flutter web client in Chrome, talking to each
other on one machine. Each step below has a reason, and most of them were
learned by getting it wrong once.

All data is synthetic. Every response carries `isSynthetic: true`.

## 1. Build the image, and rebuild it after any code change

```bash
docker build -t budget-forecast .
```

The Dockerfile does `COPY . .` at build time, so the image holds the code as it
was when it was built. A running container does not see later edits, and there
is no `--reload`. **After any change to `app/`, `requirements.txt` or
`data/public/`, rebuild before testing**, or you are testing the old code.
Dependencies are installed in an earlier layer, so a code-only rebuild is quick.

## 2. Run it with PORT and CORS_ALLOWED_ORIGINS

```bash
docker run --rm -e PORT=8000 \
  -e CORS_ALLOWED_ORIGINS=http://localhost:5050 \
  -p 8000:8000 budget-forecast
```

- `PORT` is the port uvicorn listens on inside the container, as Render
  injects it. `-p 8000:8000` publishes it on the host; keep the two the same.
- `CORS_ALLOWED_ORIGINS` must be exactly the web app's origin: scheme, host
  and port, no path, no trailing slash. Unset, the service allows no
  cross-origin browser calls at all (IR-02), and the app shows "Cannot reach
  the service" while the browser console shows a CORS error.

Check it answers:

```bash
curl http://localhost:8000/health
```

## 3. Run the client on a fixed port: 5050

```bash
cd client
flutter run -d chrome --web-port=5050 \
  --dart-define=FORECAST_API_URL=http://localhost:8000 \
  --dart-define=DATA_LAST_MONTH=2026-09
```

`--web-port` is required. Without it `flutter run` picks a random port on
every launch, and the origin would never match `CORS_ALLOWED_ORIGINS`.

Try `h015` for October 2026: *likely between KSh 55,658 and KSh 75,071*
(Figure 4.10).

## Why not port 5000 on macOS

macOS's AirPlay Receiver (part of Control Center) listens on port 5000, on
both IPv4 and IPv6. The browser reaches AirPlay instead of the app and gets
HTTP 403 with an `AirTunes` server header, which looks like a broken app
rather than the wrong process. Any free port works; 5050 is used throughout
these notes. Whatever you choose, `--web-port` and `CORS_ALLOWED_ORIGINS` must
name the same one. (AirPlay Receiver can be switched off in System Settings,
but choosing another port is simpler than asking everyone to.)

## Why localhost and 127.0.0.1 are different

To a browser an origin is scheme + host + port, compared as text. It does not
resolve names first, so `http://localhost:5050` and `http://127.0.0.1:5050`
are two different origins even though they reach the same server. Only the
one named in `CORS_ALLOWED_ORIGINS` is allowed. Open the app at
`http://localhost:5050`, the one configured above; opened at `127.0.0.1` it
loads, and then every request is refused.

## Why a local uvicorn cannot serve h001 to h060, and the container can

`app/data.py` looks for data in two places and takes the first it finds:

1. `data/` — the full sandbox extract, 500 households with platform UUIDs as
   ids. Gitignored; present only on a machine that ran
   `scripts/fetch_data.py`.
2. `data/public/` — the committed, minimised slice: 60 households with the
   pseudonymous ids **h001 to h060**.

On a machine with the extract, `uvicorn app.main:app` reads `data/` and
finds no `h015`: it answers "no forecast can be made yet" for every `h0xx`
id. The image cannot make that choice, because `.dockerignore` keeps
`data/*.csv` out of the build and lets only `data/public/*.csv` in. So the
container serves the same 60 households as the Render deployment, which is
why it is the one to test the client against.

A local uvicorn is still fine for working with the full extract. Use a UUID
from `data/spending_records.csv` as the household id, and set
`CORS_ALLOWED_ORIGINS` in the same shell:

```bash
CORS_ALLOWED_ORIGINS=http://localhost:5050 uvicorn app.main:app --port 8000
```
