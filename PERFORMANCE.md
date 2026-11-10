# Performance — NFR-04 (old NFR-07)

> When the service is warm, at least 95% of forecast requests shall return
> within 2 seconds. *Verified by timed calls against the deployed URL.*

This is **NFR-04** (performance and availability) in the report's consolidated
numbering. The code and the script call it NFR-07, its original ID; see the
README's "Requirement numbering" table.

```bash
python3 -m scripts.measure_latency https://budget-forecast-e8ad.onrender.com
python3 -m scripts.measure_latency https://budget-forecast-e8ad.onrender.com --requests 400
```

**Data:** synthetic. Households h001–h060 of the committed slice, October 2026.

## With the model: 10 November 2026

Measured against `main` at 78e0aaa, with `/health` reporting
`"forecaster": "model:extratrees-v2"` and `"fallbackReason": null`. The sources
are the developer's MacBook Air and the Render free plan in Frankfurt. Each
timing is the full round trip as the client sees it: the network both ways and
the service's work in between.

### Warm

| run (UTC) | warm requests | p50 | p95 | max | failed | within 2 s |
|---|---|---|---|---|---|---|
| 05:36 | 400 | 302 ms | 402 ms | 716 ms | 0 | **100.0%** |
| 05:58 | 200 | 305 ms | 409 ms | 1289 ms | 0 | **100.0%** |
| 06:34 | 200 | 358 ms | 467 ms | 802 ms | 0 | **100.0%** |
| 08:07 | 200 | 599 ms | 2083 ms | 70 s | 0 | 94.0% |
| 08:12 | 400 | 585 ms | 2042 ms | 8080 ms | 0 | 94.5% |

**Met in the three morning runs, with a wide margin. Missed by 0.5 to 1 point
in the two runs after 08:00.** Over the morning runs the model answered in about
300 ms, with p95 near 400 ms: well inside 2 s, and lower than the blend's
figures from 3 November below.

The 08:07 and 08:12 runs are reported, not discarded. In the same minutes the
slowdown also showed up where the model plays no part:

- `GET /health`, which does no forecasting, timed out once at 90 s and took up
  to 6.9 s on other calls.
- The static web client, a separate Render service with no Python in it, took
  5 to 6 s on some requests.
- TCP connects to Render took up to 3.7 s. Pings to 1.1.1.1 from the same machine
  varied between 3 and 270 ms.

So the slow period was not caused by the model's work. These measurements
cannot say whether it was the local connection or Render's edge. Either way, a
user on that path would have seen it.

### Cold start

The first POST /forecast after the service had been idle, timed by the same
script. The client shows a waking-up message after 5 s and gives up at 60 s.

| run (UTC) | idle before | first request |
|---|---|---|
| 05:58 | 17 min | **33.3 s** |
| 06:34 | 34 min | **33.3 s** |
| 08:07 | 90 min | **39.8 s** |

All three answered on the first attempt, about 20 s inside the client's 60 s
timeout and below Render's documented wake time of about 50 s. The 08:07
figure falls in the degraded period described above, so part of its extra 6 s
may be network. A `GET /health` at 05:35, after an unmeasured idle period,
took 32.8 s.

The image grew by 158 MB when the model was added. The blend-only image's cold
start was never measured on a stable connection (see below), so these figures
cannot say how much of the wake-up the model adds. They show only that the
total stays inside the client's timeout.

## Before the model: 3 November 2026 (blend)

| run (UTC) | warm requests | p50 | p95 | max | failed | within 2 s |
|---|---|---|---|---|---|---|
| 10:50 | 200 | 336 ms | 1412 ms | 3921 ms | 0 | **96.5%** |
| 10:52 | 400 | 274 ms | 854 ms | 5005 ms | 0 | **98.5%** |
| *10:43, discarded* | *200* | *293 ms* | *1192 ms* | *90 s* | *2* | *96.5%* |

The 10:43 run's first request timed out at 90 seconds, and so did one of its
"warm" requests. Calls to GitHub from the same machine were timing out at the
same time. That run is why the script now keeps retrying the wake-up until the
service actually answers before it starts timing. No cold-start figure was
recorded for the blend.

## What this does not show

- **Location-dependent.** These figures are for one machine on one
  connection. A user elsewhere, or on a mobile connection, will see different
  network time.
- **Sequential, one client.** No concurrent load was applied; the requirement
  does not ask for it, and the free plan is not sized for it.
- **POST /forecast only.** `GET /budget` was not timed.
- **Three cold starts.** Enough to show that the wake-up sits well inside 60 s
  on these days. Not enough to give its tail.
