"""Download Bihar data from OpenStreetMap (Overpass) into tools/osm_cache/bihar/.

Run from the repo root:   py tools/fetch_bihar.py
Cached files are reused; delete a file to fetch it again. Then run tools/build_bihar.py.
"""
import json, os, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "osm_cache", "bihar")
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = "RememberPlacesBiharMap/1.0 (personal map, one-off build)"
AREA = 'area["ISO3166-2"="IN-BR"]->.br;'
S, W, N, E = 24.25, 83.30, 27.55, 88.30
STEP = 0.5


def fetch(name, query, timeout=300):
    fn = os.path.join(CACHE, name + ".json")
    if os.path.exists(fn):
        return
    q = f"[out:json][timeout:{timeout}];" + query
    for attempt in range(8):
        url = SERVERS[attempt % len(SERVERS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=timeout + 60).read()
            d = json.loads(raw)
            if "remark" in d and ("error" in d["remark"].lower() or "timed out" in d["remark"].lower()):
                raise RuntimeError(d["remark"][:200])
            if not d.get("elements"):
                raise RuntimeError("empty answer (some mirrors return nothing for area queries)")
            os.makedirs(CACHE, exist_ok=True)
            open(fn, "wb").write(raw)
            print(f"  {name}: {len(d['elements'])} elements, {len(raw)//1024} KB", flush=True)
            return
        except Exception as ex:
            print(f"  {name}: {url.split('/')[2]} failed ({str(ex)[:120]}); retrying", flush=True)
            time.sleep(6 * (attempt + 1))
    sys.exit(f"Could not download {name}")


def main():
    print("districts", flush=True)
    fetch("districts", AREA + 'rel["boundary"="administrative"]["admin_level"="5"](area.br);out geom;')
    print("state outline", flush=True)
    fetch("state", 'rel["ISO3166-2"="IN-BR"];out geom;')
    print("places", flush=True)
    fetch("places", AREA + 'nwr["place"~"^(city|town|village|suburb|hamlet|neighbourhood|locality)$"]["name"](area.br);out center;')
    print("rivers", flush=True)
    fetch("rivers", AREA + 'way["waterway"="river"]["name"](area.br);out geom;')
    print("junctions", flush=True)
    fetch("junctions", AREA + 'node["railway"="station"](area.br);out;')
    print("railways", flush=True)
    fetch("railways", AREA + 'way["railway"="rail"]["usage"="main"](area.br);out geom;')
    # roads in tiles (motorway..tertiary and links), with node ids so tiles join up
    hw = "motorway|trunk|primary|secondary|tertiary"
    tiles = []
    s = S
    while s < N - 1e-9:
        w = W
        while w < E - 1e-9:
            tiles.append((round(s, 2), round(w, 2))); w += STEP
        s += STEP
    for i, (s, w) in enumerate(tiles, 1):
        print(f"roads tile {i}/{len(tiles)}", flush=True)
        fetch(f"roads_{s:.2f}_{w:.2f}", f'(way["highway"~"^({hw})(_link)?$"]({s},{w},{min(s+STEP,N)},{min(w+STEP,E)}););(._;>;);out body qt;', timeout=240)
    # GeoNames gazetteer for villages OSM lacks (CC BY 4.0): https://download.geonames.org/export/dump/IN.zip
    gdir = os.path.join(ROOT, "tools", "osm_cache", "geonames")
    if not os.path.exists(os.path.join(gdir, "IN.txt")):
        import zipfile, io
        print("geonames", flush=True)
        raw = urllib.request.urlopen(urllib.request.Request("https://download.geonames.org/export/dump/IN.zip", headers={"User-Agent": UA}), timeout=300).read()
        os.makedirs(gdir, exist_ok=True); zipfile.ZipFile(io.BytesIO(raw)).extract("IN.txt", gdir)
    print("done")


if __name__ == "__main__":
    main()
