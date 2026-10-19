import bench
# 1. Distance sanity: Atlanta to Chicago is about 590 straight-line miles.
assert 560 < bench.miles(bench.DEST["atlanta"], bench.DEST["chicago"]) < 620
# 2. Column detection works on names like USDA's and fails loudly when one is missing.
cols = [{"name": "Date", "fieldName": "date", "dataTypeName": "calendar_date"}, {"name": "Origin", "fieldName": "origin"},
        {"name": "Destination", "fieldName": "destination"}, {"name": "Distance", "fieldName": "distance"},
        {"name": "Week Low", "fieldName": "low"}, {"name": "Week High", "fieldName": "high"}, {"name": "Rate Per Mile", "fieldName": "rpm"}]
assert bench.detect(cols)["rpm"] == "rpm" and bench.detect(cols)["low"] == "low"
try: bench.detect(cols[:3]); raise AssertionError("should have failed")
except SystemExit: pass
# 3. The RPM trap: a short high-RPM load from Salinas into Seattle, far from other produce, vs a longer load to Los Angeles.
sal, imp = bench.place("Salinas-Watsonville California", bench.ORIGIN), bench.place("Imperial Valley California", bench.ORIGIN)
lanes = [{"origin": "Salinas", "o": sal, "dest": "seattle", "d": bench.DEST["seattle"], "rev": 2700.0, "miles": 820.0},       # $3.29/mi, dead end
         {"origin": "Salinas", "o": sal, "dest": "los angeles", "d": bench.DEST["los angeles"], "rev": 1000.0, "miles": 330.0},  # $3.03/mi
         {"origin": "Imperial", "o": imp, "dest": "los angeles", "d": bench.DEST["los angeles"], "rev": 900.0, "miles": 220.0}]  # $4.09/mi
start = bench.DEST["los angeles"]
g = bench.run_week(lanes, start, "greedy", 2750, 250); h = bench.run_week(lanes, start, "plan", 2750, 250)
assert h["rev"] >= g["rev"], (g, h)
# 4. Lane aggregation computes the median midpoint and calibrates against USDA's own rate per mile.
rows = [{"date": "2026-05-05T00:00:00", "origin": "Salinas-Watsonville California", "dest": "Chicago", "distance": "2100", "low": "6000", "high": "6600", "rpm": "3.0"},
        {"date": "2026-05-05T00:00:00", "origin": "Somewhere Unknown", "dest": "Chicago", "distance": "900", "low": "1", "high": "2", "rpm": "1"}]
wk, unmatched, calib = bench.lanes_by_week(rows)
assert len(wk["2026-05-05"]) == 1 and wk["2026-05-05"][0]["rev"] == 6300 and unmatched == ["Somewhere Unknown"] and calib < 0.01
print("all tests passed")
# 5. The planner is exact: brute force every chain of loads on a tiny week and compare.
import itertools, math
tiny = [dict(L) for L in lanes]
best = 0.0
for k in range(0, 7):
    for chain in itertools.product(range(len(tiny)), repeat=k):
        pos, used, rev, ok = start, 0, 0.0, True
        for i in chain:
            u = math.ceil(bench.step(pos, tiny[i])[1] / bench.UNIT)
            if used + u > int(2750 // bench.UNIT): ok = False; break
            used += u; rev += tiny[i]["rev"]; pos = tiny[i]["d"]
        if ok: best = max(best, rev)
assert abs(bench.plan_week(tiny, start, 2750)["rev"] - best) < 1e-6, (bench.plan_week(tiny, start, 2750), best)
# 6. The planner never earns less than either one-at-a-time rule on the same week.
for pol in ("greedy", "allin"):
    assert bench.plan_week(tiny, start, 2750)["rev"] >= bench.run_week(tiny, start, pol, 2750, 250)["rev"] - 1e-6
print("planner tests passed")
