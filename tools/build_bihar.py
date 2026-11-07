"""Build the Bihar data files from tools/osm_cache/bihar/ (run tools/fetch_bihar.py first).

Run from the repo root:   py tools/build_bihar.py
Writes:
  bihar/layers.json  districts (outline, Hindi name, HQ), state outline, display roads (NH/SH/major),
                     rivers, main railway lines, railway junctions
  bihar/places.json  every city/town/village/suburb: [name, hindi, type, lat*1e4, lng*1e4, district]
  bihar/net.json     routable graph of motorway..tertiary roads (same layout as roadnet.json plus
                     "r": label index per edge and "labels": ["NH-31", "SH-78", "Bailey Road", ...])
"""
import glob, json, math, os, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "osm_cache", "bihar")
OUT = os.path.join(ROOT, "bihar")
HW = ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']

HQ = {  # district -> headquarters town (with spelling variants seen in OSM)
    "Araria": ["Araria"], "Arwal": ["Arwal"], "Aurangabad": ["Aurangabad"], "Banka": ["Banka"],
    "Begusarai": ["Begusarai"], "Bhagalpur": ["Bhagalpur"], "Bhojpur": ["Arrah", "Ara"], "Buxar": ["Buxar"],
    "Darbhanga": ["Darbhanga"], "East Champaran": ["Motihari"], "Gaya": ["Gaya"], "Gopalganj": ["Gopalganj"],
    "Jamui": ["Jamui"], "Jehanabad": ["Jehanabad"], "Kaimur": ["Bhabua", "Bhabhua"], "Katihar": ["Katihar"],
    "Khagaria": ["Khagaria"], "Kishanganj": ["Kishanganj"], "Lakhisarai": ["Lakhisarai"], "Madhepura": ["Madhepura"],
    "Madhubani": ["Madhubani"], "Munger": ["Munger", "Monghyr"], "Muzaffarpur": ["Muzaffarpur"],
    "Nalanda": ["Bihar Sharif", "Biharsharif", "Bihar"], "Nawada": ["Nawada"], "Patna": ["Patna"],
    "Purnia": ["Purnia", "Purnea"], "Rohtas": ["Sasaram", "Sasaram"], "Saharsa": ["Saharsa"],
    "Samastipur": ["Samastipur"], "Saran": ["Chhapra", "Chapra", "Chhapra"], "Sheikhpura": ["Sheikhpura"],
    "Sheohar": ["Sheohar"], "Sitamarhi": ["Sitamarhi"], "Siwan": ["Siwan"], "Supaul": ["Supaul"],
    "Vaishali": ["Hajipur"], "West Champaran": ["Bettiah"],
}
ALIASES = {"purbi champaran": "East Champaran", "purba champaran": "East Champaran", "east champaran": "East Champaran",
           "pashchim champaran": "West Champaran", "pashchimi champaran": "West Champaran", "west champaran": "West Champaran",
           "kaimur (bhabua)": "Kaimur", "kaimur": "Kaimur"}


def load(name):
    return json.load(open(os.path.join(CACHE, name + ".json"), encoding="utf-8"))["elements"]


def m(a, b):
    return math.hypot((b[1] - a[1]) * math.cos(math.radians(a[0])) * 111320, (b[0] - a[0]) * 110570)


def rdp(pts, eps):
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; st = [(0, len(pts) - 1)]
    while st:
        i0, i1 = st.pop(); a, b = pts[i0], pts[i1]
        dx, dy = b[1] - a[1], b[0] - a[0]; L = math.hypot(dx, dy) or 1e-12; dmax, ix = 0, 0
        for i in range(i0 + 1, i1):
            p = pts[i]; dd = abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / L
            if dd > dmax: dmax, ix = dd, i
        if dmax > eps: keep[ix] = True; st += [(i0, ix), (ix, i1)]
    return [p for p, k in zip(pts, keep) if k]


def rdp_ring(r, eps):
    """Simplify a closed ring: split it at its middle so the line ends differ."""
    if len(r) < 8: return r
    mid = len(r) // 2
    return rdp(r[:mid + 1], eps) + rdp(r[mid:], eps)[1:]


def stitch(ways):
    """Join way geometries into closed rings."""
    ways = [w[:] for w in ways if len(w) > 1]; rings = []
    while ways:
        ring = ways.pop()
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, w in enumerate(ways):
                if w[0] == ring[-1]: ring += w[1:]
                elif w[-1] == ring[-1]: ring += w[-2::-1]
                elif w[-1] == ring[0]: ring = w[:-1] + ring
                elif w[0] == ring[0]: ring = w[:0:-1] + ring
                else: continue
                ways.pop(i); changed = True; break
        if len(ring) > 3: rings.append(ring)
    return rings


def inside(pt, rings):
    y, x = pt; c = False
    for r in rings:
        for i in range(len(r) - 1):
            (y1, x1), (y2, x2) = r[i], r[i + 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c


def rings_of(rel):
    outer = [[(round(p["lat"], 5), round(p["lon"], 5)) for p in mb["geometry"]] for mb in rel.get("members", [])
             if mb.get("type") == "way" and mb.get("role") in ("outer", "") and mb.get("geometry")]
    return stitch(outer)


def road_label(t):
    ref = (t.get("ref") or "").split(";")[0].strip()
    if ref:
        mm = re.match(r"^(NH|SH|MDR)\s*-?\s*(\w+)$", ref, re.I)
        return f"{mm.group(1).upper()}-{mm.group(2).upper()}" if mm else ref
    return (t.get("name:en") or t.get("name") or "").strip()


def road_cls(t, hw):
    lab = road_label(t)
    if lab.startswith("NH-") or hw in ("motorway", "trunk"): return "nh"
    if lab.startswith("SH-"): return "sh"
    if lab.startswith("MDR") or hw in ("primary", "secondary"): return "mdr"
    return "other"


def main():
    os.makedirs(OUT, exist_ok=True)
    # ---------- districts ----------
    dists = []
    for rel in load("districts"):
        t = rel.get("tags", {}); nm = (t.get("name:en") or t.get("name") or "").strip()
        nm = ALIASES.get(nm.lower().replace(" district", ""), nm.replace(" district", "").replace(" District", ""))
        rings = rings_of(rel)
        if not rings: continue
        dists.append({"n": nm, "hi": t.get("name:hi", ""), "rings": rings})
    print("districts", len(dists), sorted(d["n"] for d in dists))
    bbox = lambda rings: (min(p[0] for r in rings for p in r), min(p[1] for r in rings for p in r), max(p[0] for r in rings for p in r), max(p[1] for r in rings for p in r))
    for d in dists: d["bb"] = bbox(d["rings"])

    def district_of(lat, lng):
        for i, d in enumerate(dists):
            b = d["bb"]
            if b[0] <= lat <= b[2] and b[1] <= lng <= b[3] and inside((lat, lng), d["rings"]): return i
        return -1

    # ---------- places ----------
    TYP = {"city": 0, "town": 1, "village": 2, "suburb": 3, "hamlet": 4, "neighbourhood": 3, "locality": 4}
    places = []; seen = set()
    for e in load("places"):
        if "lat" not in e:
            if "center" not in e: continue
            e["lat"], e["lon"] = e["center"]["lat"], e["center"]["lon"]
        t = e.get("tags", {}); nm = (t.get("name:en") or t.get("name") or "").strip()
        if not nm or not re.search(r"[A-Za-z]", nm): nm = (t.get("name:en") or "").strip() or nm
        k = (nm.lower(), round(e["lat"], 2), round(e["lon"], 2))
        if k in seen: continue
        seen.add(k)
        hi = t.get("name:hi", "")
        if not hi and re.search(r"[ऀ-ॿ]", t.get("name", "")): hi = t["name"]
        pop = 0
        try: pop = int(re.sub(r"\D", "", t.get("population", "0")) or 0)
        except ValueError: pass
        places.append([nm, hi, TYP[t["place"]], round(e["lat"] * 1e4), round(e["lon"] * 1e4), district_of(e["lat"], e["lon"]), pop])
    places = [p for p in places if p[5] >= 0]
    print("OSM places", len(places), collections.Counter(p[2] for p in places))
    # GeoNames (CC BY 4.0) adds the villages OSM hasn't mapped: tools/osm_cache/geonames/IN.txt, admin1 34 = Bihar
    gn = os.path.join(ROOT, "tools", "osm_cache", "geonames", "IN.txt")
    if os.path.exists(gn):
        grid = collections.defaultdict(list)
        for p in places: grid[(p[3] // 200, p[4] // 200)].append(p)
        big_osm = [p for p in places if p[2] <= 1]
        added = 0
        for line in open(gn, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 15 or f[10] != "34" or f[6] != "P" or f[7] in ("PPLH", "PPLW", "PPLQ"): continue
            nm = f[2].strip() or f[1].strip(); lat, lng = float(f[4]), float(f[5])
            if not nm: continue
            la, lo = round(lat * 1e4), round(lng * 1e4)
            dup = any(q[0].lower() == nm.lower() and abs(q[3] - la) < 200 and abs(q[4] - lo) < 220
                      for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid[(la // 200 + dx, lo // 200 + dy)])
            if dup: continue
            # a city or town OSM already has (its GeoNames point can be several km away)
            if any(q[0].lower() == nm.lower() and abs(q[3] - la) < 1400 and abs(q[4] - lo) < 1500 for q in big_osm): continue
            pop = int(f[14] or 0)
            t = 0 if pop >= 100000 or f[7] in ("PPLA", "PPLC") else 1 if pop >= 20000 or f[7] in ("PPLA2", "PPLA3") else 2
            hi = next((a for a in f[3].split(",") if re.search(r"[ऀ-ॿ]", a)), "")
            d = district_of(lat, lng)
            if d < 0: continue
            p = [nm, hi, t, la, lo, d, pop]; places.append(p); grid[(la // 200, lo // 200)].append(p); added += 1
        print("GeoNames added", added)
    print("places", len(places), collections.Counter(p[2] for p in places))

    # ---------- district HQs ----------
    for i, d in enumerate(dists):
        names = [x.lower() for x in HQ.get(d["n"], [d["n"]])]
        cands = [p for p in places if p[5] == i and p[0].lower() in names]
        cands.sort(key=lambda p: (p[2] not in (0, 1), -p[6]))
        if cands: p = cands[0]; d["hq"] = [p[3] / 1e4, p[4] / 1e4]; d["hqn"] = p[0]; d["hqhi"] = p[1]
        else:
            big = sorted([p for p in places if p[5] == i and p[2] in (0, 1)], key=lambda p: -p[6])
            if big: p = big[0]; d["hq"] = [p[3] / 1e4, p[4] / 1e4]; d["hqn"] = p[0]; d["hqhi"] = p[1]
            print("  HQ not matched for", d["n"], "->", d.get("hqn"))

    # ---------- roads: graph + display ----------
    nodes, ways = {}, {}
    for fn in glob.glob(os.path.join(CACHE, "roads_*.json")):
        for el in json.load(open(fn, encoding="utf-8"))["elements"]:
            if el["type"] == "node": nodes[el["id"]] = (round(el["lat"], 6), round(el["lon"], 6))
            elif el["type"] == "way": ways[el["id"]] = el
    print("road ways", len(ways), "nodes", len(nodes))
    keep = []
    for w in ways.values():
        t = w.get("tags", {}); hw = t.get("highway", "").replace("_link", "")
        if hw not in HW or t.get("area") == "yes" or t.get("access") in ("no", "private"): continue
        ns = [x for x in w["nodes"] if x in nodes]
        if len(ns) >= 2: keep.append((t, hw, ns))
    use = collections.Counter()
    for _, _, ns in keep:
        for x in ns: use[x] += 1
        use[ns[0]] += 1; use[ns[-1]] += 1
    labels, lab_ix = [""], {"": 0}
    idx, nl, edges = {}, [], []
    def nid(x):
        if x not in idx: idx[x] = len(nl); nl.append(nodes[x])
        return idx[x]
    display = collections.defaultdict(list)
    for t, hw, ns in keep:
        lab = road_label(t)
        if lab not in lab_ix: lab_ix[lab] = len(labels); labels.append(lab)
        li = lab_ix[lab]
        lift = 32 if (t.get("bridge", "no") != "no" or t.get("layer", "0") not in ("0", "")) else 0
        ow = t.get("oneway"); flag = 1 if (ow in ("yes", "true", "1") or t.get("junction") == "roundabout" or (hw == "motorway" and ow != "no")) else 0
        if ow == "-1": flag = 2
        cls = road_cls(t, hw)
        if cls != "other" or (hw == "tertiary" and lab):
            display[(cls, lab)].append([nodes[x] for x in ns])
        seg = [ns[0]]
        for x in ns[1:]:
            seg.append(x)
            if use[x] > 1 or x == ns[-1]:
                pts = [nodes[y] for y in seg]; L = sum(m(a, b) for a, b in zip(pts, pts[1:]))
                a, b = nid(seg[0]), nid(seg[-1]); mid = rdp(pts, 0.00025)[1:-1]; f = flag
                if flag == 2: a, b, mid, f = b, a, mid[::-1], 1
                if a != b or L > 0: edges.append((a, b, round(L), f, HW.index(hw) + lift, mid, li))
                seg = [x]
    adj = collections.defaultdict(list)
    for e in edges: adj[e[0]].append(e[1]); adj[e[1]].append(e[0])
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
    E, G, R = [], [], []
    for a, b, L, f, h, mid, li in edges:
        E += [remap[a], remap[b], L, f * 16 + h]; R.append(li)
        g = []; pla, plo = round(nl2[remap[a]][0] * 1e5), round(nl2[remap[a]][1] * 1e5)
        for la, lo in mid:
            x, y = round(la * 1e5), round(lo * 1e5); g += [x - pla, y - plo]; pla, plo = x, y
        G.append(g)
    net = json.dumps({"hw": HW, "n": flatn, "e": E, "g": G, "r": R, "labels": labels}, separators=(",", ":"), ensure_ascii=False)
    open(os.path.join(OUT, "net.json"), "w", encoding="utf-8").write(net)
    print("net: nodes", len(nl2), "edges", len(E) // 4, "components", c, "KB", len(net.encode()) // 1000)

    # display roads: merge each (class, label) into simplified polylines
    droads = []
    for (cls, lab), lines in display.items():
        for ln in lines:
            s = rdp(ln, 0.0012 if cls == "other" else 0.0008)
            if len(s) > 1: droads.append([cls, lab, [[round(p[0], 4), round(p[1], 4)] for p in s]])
    # rivers (long named ones), railways, junctions, state outline
    rivers = collections.defaultdict(list)
    for w in load("rivers"):
        g = [(p["lat"], p["lon"]) for p in w.get("geometry", [])]
        if len(g) > 1: rivers[w["tags"].get("name:en") or w["tags"]["name"]].append(g)
    rv = []
    for nm, lines in rivers.items():
        total = sum(sum(m(a, b) for a, b in zip(g, g[1:])) for g in lines)
        if total < 25000: continue
        for g in lines:
            s = rdp(g, 0.002)
            if len(s) > 1: rv.append([nm, [[round(p[0], 3), round(p[1], 3)] for p in s]])
    rails = []
    for w in load("railways"):
        g = [(p["lat"], p["lon"]) for p in w.get("geometry", [])]
        s = rdp(g, 0.0015)
        if len(s) > 1: rails.append([[round(p[0], 3), round(p[1], 3)] for p in s])
    junc = [[(e["tags"].get("name:en") or e["tags"]["name"]), e["tags"].get("name:hi", ""), round(e["lat"], 4), round(e["lon"], 4)]
            for e in load("junctions") if "lat" in e and "name" in e.get("tags", {})
            and re.search(r"junction|\bjn\b|जंक्शन", (e["tags"].get("name:en", "") + " " + e["tags"]["name"]), re.I)]
    state = []
    for rel in load("state"): state += rings_of(rel)
    layers = {
        "districts": [{"n": d["n"], "hi": d["hi"], "hq": d.get("hq"), "hqn": d.get("hqn", ""), "hqhi": d.get("hqhi", ""),
                       "rings": [[[round(p[0], 3), round(p[1], 3)] for p in rdp_ring(r, 0.003)] for r in d["rings"]]} for d in dists],
        "state": [[[round(p[0], 3), round(p[1], 3)] for p in rdp_ring(r, 0.003)] for r in state],
        "roads": droads, "rivers": rv, "rails": rails, "junctions": junc,
    }
    s = json.dumps(layers, separators=(",", ":"), ensure_ascii=False)
    open(os.path.join(OUT, "layers.json"), "w", encoding="utf-8").write(s)
    print("layers KB", len(s.encode()) // 1000, "roads", len(droads), "rivers", len(rv), "rails", len(rails), "junctions", len(junc))
    s = json.dumps({"districts": [d["n"] for d in dists], "p": [p[:6] for p in places]}, separators=(",", ":"), ensure_ascii=False)
    open(os.path.join(OUT, "places.json"), "w", encoding="utf-8").write(s)
    print("places KB", len(s.encode()) // 1000)


if __name__ == "__main__":
    main()
