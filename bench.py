"""rpm-trap: does chasing the highest rate per mile cost truck drivers money?

Simulates a week of reefer loads on USDA's public weekly lane rates and compares three ways to pick the next load:
  greedy  - highest loaded RPM within a deadhead radius, the "find the highest RPM load" approach
  allin   - highest revenue per total mile, counting the empty miles to reach the pickup
  plan    - the best chain of loads for the whole week, found exactly by dynamic programming over the mileage budget
Standard library only.
"""
import argparse, datetime as dt, json, math, pathlib, statistics, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).parent
DATASET = "acar-e3r8"                                   # USDA AgTransport: Refrigerated Truck Rates and Availability
BASE = "https://agtransport.usda.gov"
ROAD = 1.2                                              # straight-line miles to road miles for deadhead legs

DEST = {"atlanta": (33.75, -84.39), "baltimore": (39.29, -76.61), "boston": (42.36, -71.06), "chicago": (41.88, -87.63),
        "dallas": (32.78, -96.80), "los angeles": (34.05, -118.24), "miami": (25.76, -80.19), "new york": (40.71, -74.01),
        "philadelphia": (39.95, -75.17), "seattle": (47.61, -122.33)}
# AMS shipping districts, matched by keyword, most specific first. Unmatched origins are skipped and listed.
ORIGIN = [("nogales", (31.34, -110.94)), ("otay", (32.55, -116.94)), ("mcallen", (26.20, -98.23)), ("pharr", (26.20, -98.18)),
          ("rio grande", (26.20, -98.23)), ("mexico crossings through texas", (26.20, -98.23)), ("south texas", (26.90, -98.50)),
          ("salinas", (36.68, -121.66)), ("watsonville", (36.91, -121.76)), ("oxnard", (34.20, -119.18)), ("santa maria", (34.95, -120.44)),
          ("kern", (35.37, -119.02)), ("san joaquin", (36.74, -119.79)), ("sacramento", (38.58, -121.49)), ("imperial", (32.79, -115.56)),
          ("coachella", (33.72, -116.22)), ("south district california", (33.72, -116.22)), ("yuma", (32.69, -114.62)),
          ("central arizona", (33.45, -112.07)), ("yakima", (46.60, -120.51)), ("wenatchee", (47.42, -120.31)),
          ("columbia basin", (47.13, -119.28)), ("hood river", (45.71, -121.52)), ("malheur", (43.98, -117.0)),
          ("upper valley", (43.49, -112.03)), ("twin falls", (42.56, -114.46)), ("idaho", (43.0, -114.0)),
          ("san luis valley", (37.47, -105.87)), ("red river valley", (47.93, -97.03)), ("central wisconsin", (44.52, -89.57)),
          ("michigan", (42.96, -85.67)), ("maine", (46.70, -68.00)), ("new york", (43.10, -77.60)), ("pennsylvania", (40.30, -76.90)),
          ("new jersey", (39.60, -74.90)), ("delaware", (38.70, -75.50)), ("north carolina", (35.60, -77.40)),
          ("south georgia", (31.45, -83.51)), ("georgia", (32.22, -82.41)), ("southwest florida", (26.42, -81.42)),
          ("southeast florida", (26.60, -80.30)), ("central florida", (28.30, -81.60)), ("florida", (27.50, -81.50))]

def miles(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))

def place(name, table):
    n = name.lower()
    for k, v in (table.items() if isinstance(table, dict) else table):
        if k in n: return v
    return None

def city(name):
    n = name.lower()
    return next((k for k in DEST if k in n), None)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rpm-trap", "Accept": "application/json"})
    for i in range(4):
        try: return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception:
            if i == 3: raise
            import time; time.sleep(3 * (i + 1))

def detect(columns):
    """Map the dataset's columns to the fields we need, by name, so a renamed column fails loudly."""
    def find(*words, kind=None):
        for c in columns:
            n = (c.get("name", "") + " " + c.get("fieldName", "")).lower()
            if all(w in n for w in words) and (kind is None or c.get("dataTypeName") == kind): return c["fieldName"]
        return None
    f = {"date": find("date", kind="calendar_date") or find("date") or find("week", kind="calendar_date"),
         "origin": find("origin"), "dest": find("destination"), "distance": find("distance"),
         "low": find("low"), "high": find("high"), "rpm": find("per mile") or find("rpm")}
    missing = [k for k, v in f.items() if not v]
    if missing: raise SystemExit(f"Could not find columns for {missing} in {[c.get('name') for c in columns]}")
    return f

def fetch(weeks):
    cache = ROOT / "data" / f"rates-{weeks}w.json"
    if cache.exists(): return json.loads(cache.read_text())
    f = detect(get(f"{BASE}/api/views/{DATASET}.json")["columns"])
    since = (dt.date.today() - dt.timedelta(weeks=weeks)).isoformat()
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"$where": f"{f['date']} >= '{since}T00:00:00'", "$order": f["date"], "$limit": 50000, "$offset": off})
        page = get(f"{BASE}/resource/{DATASET}.json?{q}")
        rows += [{k: r.get(v) for k, v in f.items()} for r in page]
        print(f"  fetched {len(rows)} rows", flush=True)
        if len(page) < 50000: break
        off += 50000
    cache.parent.mkdir(exist_ok=True); cache.write_text(json.dumps(rows))
    return rows

def lanes_by_week(rows):
    """One typical load per origin, destination and week: the median midpoint rate across commodities."""
    acc, unmatched, calib = {}, set(), []
    for r in rows:
        try: lo, hi, d = float(r["low"]), float(r["high"]), float(r["distance"])
        except (TypeError, ValueError): continue
        if d <= 0 or hi <= 0: continue
        o, de = place(r["origin"] or "", ORIGIN), place(r["dest"] or "", DEST)
        if o is None: unmatched.add(r["origin"]); continue
        if de is None: continue
        if r.get("rpm"):
            try: calib.append(abs((lo + hi) / 2 / d - float(r["rpm"])) / float(r["rpm"]))
            except (ValueError, ZeroDivisionError): pass
        acc.setdefault((str(r["date"])[:10], r["origin"], city(r["dest"])), []).append(((lo + hi) / 2, d, o))
    weeks = {}
    for (w, o, de), v in acc.items():
        weeks.setdefault(w, []).append({"origin": o, "o": v[0][2], "dest": de, "d": DEST[de],
                                        "rev": statistics.median(x[0] for x in v), "miles": statistics.median(x[1] for x in v)})
    return weeks, sorted(x for x in unmatched if x), (statistics.median(calib) if calib else None)

UNIT = 25                                               # planner resolution in miles; costs round up, so the plan never overspends

def step(pos, L):
    dh = ROAD * miles(pos, L["o"]); return dh, dh + L["miles"]

def run_week(lanes, start, policy, budget, radius):
    if policy == "plan": return plan_week(lanes, start, budget)
    pos, rev, loaded, dead, n = start, 0.0, 0.0, 0.0, 0
    while True:
        best = None
        for L in lanes:
            dh, tot = step(pos, L)
            if loaded + dead + tot > budget: continue
            if policy == "greedy":   # highest loaded RPM nearby; with nothing nearby, the nearest pickup
                score = (1, L["rev"] / L["miles"], -dh) if dh <= radius else (0, -dh, L["rev"] / L["miles"])
            else: score = (L["rev"] / tot,)
            if best is None or score > best[0]: best = (score, dh, L)
        if best is None: break
        _, dh, L = best
        rev += L["rev"]; loaded += L["miles"]; dead += dh; n += 1; pos = L["d"]
    return {"rev": rev, "loaded": loaded, "dead": dead, "loads": n}

def plan_week(lanes, start, budget):
    """Exact best chain of loads for the week. After each load the truck sits in a destination city, so the state is
    (city, miles left). V[b][c] = best revenue with b units left in city c."""
    B = int(budget // UNIT); cities = list(DEST); pos_list = cities + ["_start"]; xy = {**DEST, "_start": start}
    cost = {c: [(math.ceil(step(xy[c], L)[1] / UNIT), L) for L in lanes] for c in pos_list}
    V = [{c: 0.0 for c in pos_list} for _ in range(B + 1)]; pick = [{c: None for c in pos_list} for _ in range(B + 1)]
    for b in range(1, B + 1):
        for c in pos_list:
            best, arg = V[b - 1][c], pick[b - 1][c]
            for u, L in cost[c]:
                if u <= b:
                    v = L["rev"] + V[b - u][L["dest"]]
                    if v > best: best, arg = v, (u, L)
            V[b][c], pick[b][c] = best, arg
    c, b, rev, loaded, dead, n = "_start", B, 0.0, 0.0, 0.0, 0
    while b > 0 and pick[b][c] is not None:
        u, L = pick[b][c]; dh, _ = step(xy[c], L)
        rev += L["rev"]; loaded += L["miles"]; dead += dh; n += 1; b -= u; c = L["dest"]
    return {"rev": rev, "loaded": loaded, "dead": dead, "loads": n}

def main(weeks, budget, radius):
    rows = fetch(weeks)
    wk, unmatched, calib = lanes_by_week(rows)
    if not wk: raise SystemExit("No usable lanes. Paste the 'Could not find columns' or unmatched-origin output to Claude.")
    res = {p: [] for p in ("greedy", "allin", "plan")}
    for w, lanes in sorted(wk.items()):
        for city, xy in DEST.items():
            for p in res: res[p].append(run_week(lanes, xy, p, budget, radius))
    def agg(p):
        R = res[p]; rev = statistics.mean(x["rev"] for x in R); dead = sum(x["dead"] for x in R); tot = dead + sum(x["loaded"] for x in R)
        return rev, sum(x["rev"] for x in R) / tot, 100 * dead / tot, statistics.mean(x["loads"] for x in R)
    g, a, h = agg("greedy"), agg("allin"), agg("plan")
    names = {"greedy": f"Highest loaded RPM within {radius:.0f} empty miles", "allin": "Highest all-in RPM, counting empty miles",
             "plan": "Best chain of loads for the whole week, planned exactly"}
    md = [f"# rpm-trap on USDA reefer lane rates, {dt.date.today()}", "",
          f"{len(wk)} weeks of USDA AgTransport refrigerated truck rates, {sum(len(v) for v in wk.values())} lane-weeks. "
          f"Each week a driver starts at each of the 10 USDA destination cities with {budget:,.0f} miles to drive, loaded plus empty, "
          f"and picks loads by one of three rules. Revenue is the midpoint of USDA's weekly rate range per load.", "",
          "| How the next load is picked | Revenue per week | Revenue per total mile | Empty miles | Loads per week |", "|---|---|---|---|---|"]
    for p, (rv, pm, dh, nl) in (("greedy", g), ("allin", a), ("plan", h)):
        md.append(f"| {names[p]} | ${rv:,.0f} | ${pm:.2f} | {dh:.0f}% | {nl:.1f} |")
    md += ["", f"**Planning the week earned {100 * (h[0] / g[0] - 1):+.0f}% per week against chasing the highest RPM, on the same miles. Counting empty miles alone gave {100 * (a[0] / g[0] - 1):+.0f}%.**", "",
           "## Calibration", "",
           (f"USDA publishes its own rate per mile for each row. Midpoint over distance, as computed here, matched it with a median error of {100 * calib:.2f}%." if calib is not None
            else "USDA's own rate per mile column was not available for calibration."), "",
           "## Honest limits", "",
           "- USDA rates are produce reefer spot rates paid by shippers, including broker fees. A driver nets less, but every rule is paid the same way, so the comparison holds.",
           "- Every lane in a week is treated as available. Real load boards are thinner, and this is a test of the picking rule, not of supply.",
           "- Empty miles are straight-line distance times 1.2. Loading time, hours of service and fuel cost per mile beyond the mileage budget are not modeled.",
           "- Each week starts fresh at each destination city, so a bad Friday never carries into Monday.",
           "- The planner sees the whole week's posted lane rates in advance. Greedy and all-in see the same rates but pick one load at a time, so the planner is the ceiling for planning on this data.",
           f"- Origins matched to coordinates by district name; {len(unmatched)} unmatched districts were skipped" + (f": {', '.join(unmatched[:8])}{'...' if len(unmatched) > 8 else ''}." if unmatched else ".")]
    out = "\n".join(md); (ROOT / "results").mkdir(exist_ok=True); (ROOT / "results" / f"{dt.date.today()}.md").write_text(out, encoding="utf-8"); print(out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=52); ap.add_argument("--budget", type=float, default=2750); ap.add_argument("--radius", type=float, default=250)
    a = ap.parse_args(); main(a.weeks, a.budget, a.radius)
