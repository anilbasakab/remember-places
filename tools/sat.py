import math, os, time, urllib.request, json, base64, concurrent.futures as cf
def tile(lat, lon, z):
    n = 2**z; return int((lon+180)/360*n), int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
plan = [((25.66,85.02),(25.55,85.29),z) for z in (11,12,13,14,15)] + [((25.625,85.095),(25.585,85.14),16)]
todo=[]
for (n_,w),(s,e),z in plan:
    x0,y0=tile(n_,w,z); x1,y1=tile(s,e,z); todo += [(z,x,y) for x in range(x0,x1+1) for y in range(y0,y1+1)]
os.makedirs("t",exist_ok=True)
def get(t):
    z,x,y=t; p=f"t/{z}_{x}_{y}.jpg"
    if os.path.exists(p): return
    for k in range(4):
        try:
            req=urllib.request.Request(f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",headers={"User-Agent":"PatnaPlacesPersonalMap/1.0"})
            open(p,"wb").write(urllib.request.urlopen(req,timeout=30).read()); return
        except Exception: time.sleep(3*(k+1))
with cf.ThreadPoolExecutor(4) as ex: list(ex.map(get,todo))
out={f"{z}/{x}/{y}":"data:image/jpeg;base64,"+base64.b64encode(open(f"t/{z}_{x}_{y}.jpg","rb").read()).decode() for z,x,y in todo if os.path.exists(f"t/{z}_{x}_{y}.jpg")}
json.dump(out,open("sat.json","w")); print(len(todo),len(out),os.path.getsize("sat.json")/1e6,"MB")
