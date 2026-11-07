import math, os, time, urllib.request, json, base64
def tile(lat, lon, z):
    n = 2**z; x = int((lon+180)/360*n)
    y = int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n); return x, y
plan = [((25.66,85.02),(25.55,85.29),z) for z in (11,12,13,14,15)] + [((25.625,85.095),(25.585,85.14),16)]
todo=[]
for (n_,w),(s,e),z in plan:
    x0,y0=tile(n_,w,z); x1,y1=tile(s,e,z)
    todo += [(z,x,y) for x in range(x0,x1+1) for y in range(y0,y1+1)]
print(len(todo))
out={}
os.makedirs("t",exist_ok=True)
for z,x,y in todo:
    p=f"t/{z}_{x}_{y}.png"
    if not os.path.exists(p):
        req=urllib.request.Request(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",headers={"User-Agent":"PatnaPlacesPersonalMap/1.0 (one-off personal map)"})
        open(p,"wb").write(urllib.request.urlopen(req,timeout=30).read()); time.sleep(0.25)
    out[f"{z}/{x}/{y}"]="data:image/png;base64,"+base64.b64encode(open(p,"rb").read()).decode()
json.dump(out,open("tiles.json","w"))
print(os.path.getsize("tiles.json")/1e6,"MB")
