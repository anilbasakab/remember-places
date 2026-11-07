import json, math, collections, re
els=json.load(open('op2.json'))['elements']
LM=json.loads(open('refdata.js').read().split("const LANDMARKS = ")[1].split(";\n")[0])
B=(25.545,85.015,25.665,85.295)
def norm_ref(r):
    parts=[p.strip().upper().replace(' ','') for p in re.split('[;,]',r) if p.strip()]
    return [re.sub(r'^(NH|SH)(\w+)$',r'\1-\2',p) for p in parts]
def klass(t):
    refs=norm_ref(t.get('ref',''))
    if re.match(r'^NH ?\d', t.get('name','')): return 'nh'
    if any(p.startswith('NH') for p in refs): return 'nh'
    if any(p.startswith('SH') or p=='MDR' for p in refs): return 'sh'
    return 'city'
def clean(n):
    n=n.strip()
    fix={'Ashok Raj Path':'Ashok Rajpath','Fraser Road (Mazrul Haque Path)':'Fraser Road','Birchand Patel Path (Gardner Road)':'Birchand Patel Path','JP Ganga Path':'JP Ganga Path (Marine Drive)','Marine Drive':'JP Ganga Path (Marine Drive)','East Boring Canal Road':'Boring Canal Road','West Boring Canal Road':'Boring Canal Road','AIIMS- Digha elevated road':'AIIMS–Digha Elevated Road','AIIMS - DIGHA Service road':'AIIMS–Digha Elevated Road'}
    return fix.get(n,n)
def route_key(t):
    k=klass(t); refs=[p for p in norm_ref(t.get('ref','')) if p!='MDR']
    nm=clean(t.get('name') or t.get('name:en') or '')
    if k=='nh':
        if not refs: refs=norm_ref(t.get('name',''))
        return ' / '.join(sorted(set(p for p in refs if p.startswith('NH'))))
    if k=='sh':
        if refs: return refs[0]
        return f"MDR · {nm}" if nm and nm!='MDR' else 'MDR (unnamed)'
    return nm or ''
def seglen(g):
    s=0
    for a,b in zip(g,g[1:]):
        s+=math.hypot((b[1]-a[1])*math.cos(math.radians(a[0]))*111.32,(b[0]-a[0])*111.32)
    return s
ways=[]; R=collections.defaultdict(lambda:{'km':0,'cls':None,'names':collections.Counter(),'hi':collections.Counter(),'lanes':collections.Counter(),'surface':collections.Counter(),'maxspeed':collections.Counter(),'bridges':0,'ends':[],'oneway_km':0,'open':set()})
for e in els:
    t=e['tags']; g=[[round(p['lat'],5),round(p['lon'],5)] for p in e['geometry']]
    k=klass(t); key=route_key(t); l=seglen(g); ow=t.get('oneway')=='yes'
    ways.append({'c':k,'r':key,'h':t['highway'].replace('_link',''),'g':g})
    if not key: continue
    r=R[key]; r['cls']=k; r['km']+=l/(2 if ow else 1)
    if t.get('name'): r['names'][clean(t['name'])]+=l/(2 if ow else 1)
    if t.get('name:hi'): r['hi'][t['name:hi']]+=l
    for f in ('lanes','surface','maxspeed'):
        if t.get(f): r[f][t[f]]+=l
    if t.get('bridge')=='yes': r['bridges']+=1
    if t.get('opening_date'): r['open'].add(t['opening_date'])
    r['ends']+= [tuple(g[0]),tuple(g[-1])]
# endpoint description helpers
endpoint_routes=collections.defaultdict(set)
for w in ways:
    for p in (w['g'][0],w['g'][-1]): endpoint_routes[tuple(p)].add(w['r'])
allpts=collections.defaultdict(set)
for w in ways:
    for p in w['g']: allpts[tuple(p)].add(w['r'])
def km(a,b): return math.hypot((b[1]-a[1])*math.cos(math.radians(a[0]))*111.32,(b[0]-a[0])*111.32)
def near_edge(p): return min(p[0]-B[0],B[2]-p[0])*111<0.6 or min(p[1]-B[1],B[3]-p[1])*100<0.6
out={}
for key,r in R.items():
    if r['km']<0.1: continue
    ends=list(set(r['ends']))
    # farthest pair (sample if many)
    if len(ends)>300: ends=ends[::len(ends)//300+1]
    best=(0,None,None)
    for i in range(len(ends)):
        for j in range(i+1,len(ends)):
            d=km(ends[i],ends[j])
            if d>best[0]: best=(d,ends[i],ends[j])
    if not best[1]: continue
    a,b=best[1],best[2]
    if (a[1],-a[0])>(b[1],-b[0]): a,b=b,a  # west/south first
    def describe(p):
        if near_edge(p): return {'t':'edge','p':p}
        lm=min(LM,key=lambda l:km(p,(l['lat'],l['lng'])))
        if km(p,(lm['lat'],lm['lng']))<0.5: return {'t':'lm','v':lm['name'],'p':p}
        others=[x for x in allpts.get(p,set()) if x and x!=key]
        if others: return {'t':'jn','v':sorted(others,key=lambda x:(x.startswith('MDR'),len(x)))[0],'p':p}
        return {'t':'geo','p':p}
    nm=[n for n,_ in r['names'].most_common()]
    out[key]={'name':key,'cls':r['cls'],'km':round(r['km'],1),'names':nm[:6],'hi':(r['hi'].most_common(1)[0][0] if r['hi'] and r['cls']=='city' else ''),'sub':[[n,round(v,1)] for n,v in r['names'].most_common(6) if v>=0.3 and n!=key],
      'lanes':(r['lanes'].most_common(1)[0][0] if r['lanes'] else ''),'surface':(r['surface'].most_common(1)[0][0] if r['surface'] else ''),
      'maxspeed':(r['maxspeed'].most_common(1)[0][0] if r['maxspeed'] else ''),'bridges':r['bridges'],'open':sorted(r['open']),
      'from':describe(a),'to':describe(b)}
json.dump({'ways':ways,'routes':out},open('roads_full.json','w'),ensure_ascii=False)
print(len(ways),len(out))
for k,v in sorted(out.items(),key=lambda x:-x[1]['km'])[:40]: print(v['km'],v['cls'],k,'|',v['names'][:3],v['hi'],v['lanes'],v['surface'],v['from']['t'],v['from'].get('v'),'->',v['to']['t'],v['to'].get('v'))
geo=[v for v in out.values() for e in (v['from'],v['to']) if e['t']=='geo']
print('need geocode',len(geo))
