import json, math, collections
SRC=[]  # (tags, [(lat,lon),...])
for e in json.load(open('../ref/op2.json'))['elements']:
    SRC.append((e['tags'],[(round(p['lat'],7),round(p['lon'],7)) for p in e['geometry']]))
for fn in ['part_0_0.json','fine_0_2.json']:
    dd=json.load(open(fn))['elements']; NN={e['id']:(round(e['lat'],7),round(e['lon'],7)) for e in dd if e['type']=='node'}
    for e in dd:
        if e['type']=='way' and 'tags' in e: SRC.append((e['tags'],[NN[n] for n in e['nodes'] if n in NN]))
# dedupe identical ways (major roads appear in both sources)
seen=set(); S2=[]
for t,g in SRC:
    k=(g[0],g[-1],len(g))
    if k in seen: continue
    seen.add(k); S2.append((t,g))
SRC=S2
N={p:p for t,g in SRC for p in g}
W=[{'tags':t,'nodes':g} for t,g in SRC]
HW=['motorway','trunk','primary','secondary','tertiary','unclassified','residential','living_street','service']
use=collections.Counter()
for w in W:
    for n in w['nodes']: use[n]+=1
for w in W: use[w['nodes'][0]]+=1; use[w['nodes'][-1]]+=1
def m(a,b):
    return math.hypot((b[1]-a[1])*math.cos(math.radians(a[0]))*111320,(b[0]-a[0])*110570)
idx={}; nodes=[]
def nid(n):
    if n not in idx: idx[n]=len(nodes); nodes.append(N[n])
    return idx[n]
def rdp(pts,eps):
    if len(pts)<3: return pts
    a,b=pts[0],pts[-1]; dx,dy=b[1]-a[1],b[0]-a[0]; L=math.hypot(dx,dy) or 1e-12
    dmax,ix=0,0
    for i,p in enumerate(pts[1:-1],1):
        dd=abs(dy*(p[1]-a[1])-dx*(p[0]-a[0]))/L
        if dd>dmax: dmax,ix=dd,i
    return rdp(pts[:ix+1],eps)[:-1]+rdp(pts[ix:],eps) if dmax>eps else [a,b]
edges=[]
for w in W:
    t=w['tags']; hw=t['highway'].replace('_link','')
    if hw not in HW: continue
    ow=t.get('oneway')
    flag=0
    if ow in('yes','true','1') or t.get('junction')=='roundabout' or (hw=='motorway' and ow!='no'): flag=1
    if ow=='-1': flag=2
    ns=[n for n in w['nodes'] if n in N]
    if len(ns)<2: continue
    seg=[ns[0]]
    for n in ns[1:]:
        seg.append(n)
        if use[n]>1 or n==ns[-1]:
            pts=[N[x] for x in seg]; L=sum(m(a,b) for a,b in zip(pts,pts[1:]))
            a,b=nid(seg[0]),nid(seg[-1])
            mid=rdp(pts,0.00004)[1:-1]
            if flag==2: a,b=b,a; mid=mid[::-1]; f=1
            else: f=flag
            if a!=b or L>0: edges.append((a,b,round(L),f,HW.index(hw),mid))
            seg=[n]
# drop tiny disconnected components: keep largest connected (undirected)
adj=collections.defaultdict(list)
for i,(a,b,*_) in enumerate(edges): adj[a].append(b); adj[b].append(a)
comp=[-1]*len(nodes); best=None; sizes=collections.Counter()
c=0
for s in range(len(nodes)):
    if comp[s]!=-1: continue
    st=[s]; comp[s]=c
    while st:
        u=st.pop()
        for v in adj[u]:
            if comp[v]==-1: comp[v]=c; st.append(v)
    c+=1
for x in comp: sizes[x]+=1
main=sizes.most_common(1)[0][0]
edges=[e for e in edges if comp[e[0]]==main]
used=sorted(set([e[0] for e in edges]+[e[1] for e in edges])); remap={o:i for i,o in enumerate(used)}
nl=[nodes[o] for o in used]
flatn=[]
for la,lo in nl: flatn+= [round(la*1e5), round(lo*1e5)]
E=[]; G=[]
for a,b,L,f,h,mid in edges:
    E+= [remap[a],remap[b],L,f*16+h]
    g=[]; pla,plo=round(nl[remap[a]][0]*1e5),round(nl[remap[a]][1]*1e5)
    for la,lo in mid:
        x,y=round(la*1e5),round(lo*1e5); g+=[x-pla,y-plo]; pla,plo=x,y
    G.append(g)
out={'hw':HW,'n':flatn,'e':E,'g':G}
s=json.dumps(out,separators=(',',':'))
open('roadnet.json','w').write(s)
print('nodes',len(nl),'edges',len(E)//4,'components',c,'size KB',len(s)//1000)
