#!/usr/bin/env python3
"""QR item 2 mechanism check — os.times() user-time granularity on this host.

psh/executor/core.py times pipelines with os.times() deltas; the LEDGER row's
mechanism note says a 10 ms accounting tick divided by a tiny elapsed real
produces the absurd %P. This records the observed quantum of os.times().user:
burn CPU, sample, collect the distinct nonzero increments.
"""
import os

samples = []
prev = os.times().user
x = 0
for _ in range(2_000_000):
    x += 1
    if _ % 1000 == 0:
        cur = os.times().user
        if cur != prev:
            samples.append(round(cur - prev, 6))
            prev = cur
        if len(samples) >= 20:
            break

distinct = sorted(set(samples))
print(f"observed nonzero os.times().user increments (n={len(samples)}): {distinct}")
print(f"minimum quantum: {min(distinct) if distinct else 'NONE OBSERVED'}")
