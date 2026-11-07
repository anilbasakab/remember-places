import json, time, urllib.request, urllib.parse, os
d=json.load(open('roads_full.json')); cache=json.load(open('endcache.json')) if os.path.exists('endcache.json') else {}
UA={"User-Agent":"PatnaPlacesPersonalMap/1.0 (personal one-off map)"}
for k,v in d['routes'].items():
    for e in (v['from'],v['to']):
        if e['t']!='geo': continue
        key=f"{e['p'][0]},{e['p'][1]}"
        if key not in cache:
            u="https://nominatim.openstreetmap.org/reverse?"+urllib.parse.urlencode(dict(lat=e['p'][0],lon=e['p'][1],format='jsonv2',zoom=16))
            for t in range(4):
                try: cache[key]=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30)).get('address',{}); break
                except Exception: time.sleep(10*(t+1))
            json.dump(cache,open('endcache.json','w')); time.sleep(2.2)
        a=cache.get(key,{})
        e['v']=a.get('neighbourhood') or a.get('suburb') or a.get('quarter') or a.get('road') or a.get('village') or a.get('town') or ''
        if not e['v']: e['t']='pt'
json.dump(d,open('roads_full.json','w'),ensure_ascii=False)
for k,v in d['routes'].items(): print(k,'|',v['from'].get('v',v['from']['t']),'->',v['to'].get('v',v['to']['t']),v['sub'][:3])
