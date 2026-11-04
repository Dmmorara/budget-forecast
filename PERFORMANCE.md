# Performance — NFR-07

> When the service is warm, at least 95% of forecast requests shall return
> within 2 seconds. *Verified by timed calls against the deployed URL.*

```bash
python3 -m scripts.measure_latency https://budget-forecast-e8ad.onrender.com
python3 -m scripts.measure_latency https://budget-forecast-e8ad.onrender.com --requests 400
```

**Data:** synthetic. Households h001–h060 of the committed slice, October 2026.

## Result: met, without much room to spare

Measured 3 November 2026 from the developer's MacBook Air against the Render
free plan in Frankfurt. Each timing is the full round trip as seen from the
client: the network both ways and the service's work in between.

| run (UTC) | warm requests | p50 | p95 | max | failed | within 2 s |
|---|---|---|---|---|---|---|
| 10:50 | 200 | 336 ms | 1412 ms | 3921 ms | 0 | **96.5%** |
| 10:52 | 400 | 274 ms | 854 ms | 5005 ms | 0 | **98.5%** |
| *10:43, discarded* | *200* | *293 ms* | *1192 ms* | *90 s* | *2* | *96.5%* |

Both clean runs meet the requirement. The typical request takes about 300 ms,
but a few percent take several seconds, so one run came within 1.5 points of
the 95% line. Where those seconds go (the network, or the free plan's shared
CPU) was not measured.

**The 10:43 run is not evidence either way.** Its first request timed out at
90 seconds and so did one of its "warm" requests. Calls to GitHub from the
same machine were timing out at the same time, so the local connection was
failing as well as, or instead of, the service. That run is why the script
now keeps retrying the wake-up until the service actually answers before it
starts timing.

## Cold start

**Not measured reliably.** The one cold request in these runs (10:43) did not
answer within 90 seconds, but the network failures at the time mean that
cannot be attributed to the service. Render documents about 50 seconds to wake
a sleeping free instance. The service needs a dedicated measurement on a
stable connection, after at least 15 minutes idle, before any cold-start
figure appears in the report.

## What this does not show

- **Location-dependent.** These figures are for one machine on one
  connection. A user elsewhere, or on a mobile connection, will see different
  network time.
- **Sequential, one client.** No concurrent load was applied; NFR-07 does not
  ask for it, and the free plan is not sized for it.
- **POST /forecast only.** `GET /budget` was not timed.
