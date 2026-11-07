"""Download Patna's full drivable road network from OpenStreetMap and build roadnet.json.

Run from the repo root:   py tools/build_roadnet.py
Raw Overpass responses are cached in tools/osm_cache/ (not committed); delete
that folder to force a fresh download. Output format is what index.html expects:
  {"hw": [...classes], "n": [lat*1e5, lng*1e5, ...], "e": [a, b, metres, bridge*32+oneway*16+class, ...],
   "g": [[dlat, dlng, ...] per edge, delta-encoded inner points]}
"""
import json, math, os, sys, time, collections, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "osm_cache")
OUT = os.path.join(ROOT, "roadnet.json")
S, W, N_, E_ = 25.545, 85.015, 25.665, 85.295   # bbox from CLAUDE.md
STEP = 0.04                                          # tile size in degrees
HW = ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street', 'service']
SKIP_SERVICE = {'parking_aisle', 'driveway', 'drive-through', 'emergency_access'}
SKIP_ACCESS = {'no', 'private'}
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def fetch_tile(s, w, n, e):
    fn = os.path.join(CACHE, f"{s:.3f}_{w:.3f}.json")
    if os.path.exists(fn):
        return json.load(open(fn, encoding="utf-8"))
    hw = "|".join(HW) + "|" + "|".join(h + "_link" for h in HW[:5])
    q = f'[out:json][timeout:180];(way["highway"~"^({hw})$"]({s},{w},{n},{e}););(._;>;);out body;'
    for attempt in range(8):
        url = SERVERS[attempt % len(SERVERS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "RememberPlacesPatnaMap/1.0 (personal map, one-off build)"})
            raw = urllib.request.urlopen(req, timeout=240).read()
            d = json.loads(raw)
            if "remark" in d and "error" in d["remark"].lower():
                raise RuntimeError(d["remark"])
            os.makedirs(CACHE, exist_ok=True)
            open(fn, "wb").write(raw)
            return d
        except Exception as ex:
            print(f"   {url.split('/')[2]} failed ({ex}); retrying", flush=True)
            time.sleep(5 * (attempt + 1))
    sys.exit(f"Could not download tile {s},{w}")


def m(a, b):
    return math.hypot((b[1] - a[1]) * math.cos(math.radians(a[0])) * 111320, (b[0] - a[0]) * 110570)


def rdp(pts, eps):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]; dx, dy = b[1] - a[1], b[0] - a[0]; L = math.hypot(dx, dy) or 1e-12
    dmax, ix = 0, 0
    for i, p in enumerate(pts[1:-1], 1):
        dd = abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / L
        if dd > dmax: dmax, ix = dd, i
    return rdp(pts[:ix + 1], eps)[:-1] + rdp(pts[ix:], eps) if dmax > eps else [a, b]


def main():
    nodes, ways = {}, {}
    tiles = [(round(s, 3), round(w, 3)) for s in frange(S, N_) for w in frange(W, E_)]
    for i, (s, w) in enumerate(tiles, 1):
        n, e = min(s + STEP, N_), min(w + STEP, E_)
        print(f"tile {i}/{len(tiles)}  {s},{w}", flush=True)
        for el in fetch_tile(s, w, n, e)["elements"]:
            if el["type"] == "node": nodes[el["id"]] = (round(el["lat"], 7), round(el["lon"], 7))
            elif el["type"] == "way": ways[el["id"]] = el
    print("downloaded", len(ways), "ways,", len(nodes), "nodes")

    keep = []
    for w in ways.values():
        t = w.get("tags", {}); hw = t.get("highway", "").replace("_link", "")
        if hw not in HW or t.get("area") == "yes": continue
        if hw == "service" and t.get("service") in SKIP_SERVICE: continue
        if t.get("access") in SKIP_ACCESS and t.get("motor_vehicle", t.get("motorcar")) not in ("yes", "designated", "destination"): continue
        if t.get("motor_vehicle") == "no" or t.get("motorcar") == "no": continue
        ns = [x for x in w["nodes"] if x in nodes]
        if len(ns) >= 2: keep.append((t, hw, ns))

    use = collections.Counter()
    for _, _, ns in keep:
        for x in ns: use[x] += 1
        use[ns[0]] += 1; use[ns[-1]] += 1

    idx, nl, edges = {}, [], []
    def nid(x):
        if x not in idx: idx[x] = len(nl); nl.append(nodes[x])
        return idx[x]
    for t, hw, ns in keep:
        # elevated / underground roads: a pin beside them can't join them directly
        lift = 32 if (t.get("bridge", "no") != "no" or t.get("tunnel", "no") != "no"
                      or t.get("layer", "0") not in ("0", "") or t.get("covered") == "yes") else 0
        ow = t.get("oneway"); flag = 0
        if ow in ("yes", "true", "1") or t.get("junction") in ("roundabout", "circular") or (hw == "motorway" and ow != "no"): flag = 1
        if ow == "-1": flag = 2
        seg = [ns[0]]
        for x in ns[1:]:
            seg.append(x)
            if use[x] > 1 or x == ns[-1]:
                pts = [nodes[y] for y in seg]; L = sum(m(a, b) for a, b in zip(pts, pts[1:]))
                a, b = nid(seg[0]), nid(seg[-1]); mid = rdp(pts, 0.00004)[1:-1]
                f = flag
                if flag == 2: a, b, mid, f = b, a, mid[::-1], 1
                if a != b or L > 0: edges.append((a, b, round(L), f, HW.index(hw) + lift, mid))
                seg = [x]

    # keep the largest connected piece (undirected)
    adj = collections.defaultdict(list)
    for a, b, *_ in edges: adj[a].append(b); adj[b].append(a)
    comp = [-1] * len(nl); c = 0
    for s0 in range(len(nl)):
        if comp[s0] != -1: continue
        st = [s0]; comp[s0] = c
        while st:
            u = st.pop()
            for v in adj[u]:
                if comp[v] == -1: comp[v] = c; st.append(v)
        c += 1
    main_c = collections.Counter(comp).most_common(1)[0][0]
    edges = [e for e in edges if comp[e[0]] == main_c]
    used = sorted({e[0] for e in edges} | {e[1] for e in edges}); remap = {o: i for i, o in enumerate(used)}
    nl2 = [nl[o] for o in used]
    flatn = []
    for la, lo in nl2: flatn += [round(la * 1e5), round(lo * 1e5)]
    E, G = [], []
    for a, b, L, f, h, mid in edges:
        E += [remap[a], remap[b], L, f * 16 + h]  # h already carries the +32 bridge bit
        g = []; pla, plo = round(nl2[remap[a]][0] * 1e5), round(nl2[remap[a]][1] * 1e5)
        for la, lo in mid:
            x, y = round(la * 1e5), round(lo * 1e5); g += [x - pla, y - plo]; pla, plo = x, y
        G.append(g)
    s = json.dumps({"hw": HW, "n": flatn, "e": E, "g": G}, separators=(",", ":"))
    open(OUT, "w").write(s)
    print("nodes", len(nl2), "edges", len(E) // 4, "components", c, "size KB", len(s) // 1000)


def frange(a, b):
    x = a
    while x < b - 1e-9:
        yield x; x += STEP


if __name__ == "__main__":
    main()
