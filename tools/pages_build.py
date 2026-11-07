import json, os, shutil, glob
S='/tmp/claude-0/-workspace/aeb8ab7b-5d77-506d-a638-2f2c04e11cc0/scratchpad'
OUT=S+'/pages'
page=open(S+'/site/patna-places.html').read()
seed={'places':{}, 'roads':{}, 'lmfix':{}}
for f in glob.glob(S+'/export/places/*.json'):
    d=json.load(open(f)); d.pop('__id',None)
    seed['places'][os.path.basename(f)[:-5]]=d
shim=r"""<script>
// Stand-alone mode (outside claude.ai): saves changes in this browser and seeds from seed.json
(function () {
  if (window.claude) return;
  const KEY = "patna-places:";
  const read = (c) => { try { const v = localStorage.getItem(KEY + c); return v ? JSON.parse(v) : null; } catch { return null; } };
  const write = (c, v) => { try { localStorage.setItem(KEY + c, JSON.stringify(v)); } catch {} };
  let SEED = null; const seedP = fetch("seed.json", { cache: "no-cache" }).then((r) => r.json()).then((s) => (SEED = s)).catch(() => (SEED = {}));
  const subs = {};
  const getCol = (c) => read(c) || (SEED && SEED[c] ? JSON.parse(JSON.stringify(SEED[c])) : {});
  const snap = (c) => { const o = getCol(c); return { docs: Object.entries(o).map(([id, d]) => ({ id, exists: true, data: () => d, metadata: {} })), size: Object.keys(o).length, empty: !Object.keys(o).length, docChanges: () => [], metadata: {} }; };
  const emit = (c) => (subs[c] || []).forEach((f) => { try { f(snap(c)); } catch (e) { console.error(e); } });
  const mut = (c, fn) => { const o = getCol(c); fn(o); write(c, o); setTimeout(() => emit(c), 0); };
  const db = {
    collection(c) {
      return {
        path: c,
        onSnapshot(f) { (subs[c] = subs[c] || []).push(f); seedP.then(() => f(snap(c))); return () => { subs[c] = subs[c].filter((x) => x !== f); }; },
        async get() { await seedP; return snap(c); },
        doc(id) {
          id = id || Math.random().toString(36).slice(2, 12);
          return { id, path: c + "/" + id,
            async get() { await seedP; const d = getCol(c)[id]; return { id, exists: !!d, data: () => d }; },
            async set(d) { await seedP; mut(c, (o) => { o[id] = JSON.parse(JSON.stringify(d)); }); },
            async update(d) { await seedP; mut(c, (o) => { o[id] = { ...(o[id] || {}), ...JSON.parse(JSON.stringify(d)) }; }); },
            async delete() { await seedP; mut(c, (o) => { delete o[id]; }); } };
        },
        async add(d) { const ref = this.doc(); await ref.set(d); return ref; },
      };
    },
  };
  const downloads = { async save({ filename, data }) { const url = URL.createObjectURL(data instanceof Blob ? data : new Blob([data])); const a = document.createElement("a"); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); } };
  window.claude = { use: async (n) => (n === "db" ? db : n === "downloads" ? downloads : null) };
})();
</script>
"""
head='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="A personal map of Patna: home, office, landmarks, roads, road distances and sketch maps.">
<meta name="theme-color" content="#0e6670"><link rel="manifest" href="manifest.webmanifest"><link rel="icon" href="icon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="icon-192.png">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}*,*::before,*::after{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
'''
html=head+shim+'</head><body>\n'+page+'\n</body></html>\n'
os.makedirs(OUT,exist_ok=True)
open(OUT+'/index.html','w').write(html)
for f in ['tiles.json','satellite.json','roads.json','roadnet.json']: shutil.copy(S+'/site/'+f, OUT+'/'+f)
json.dump(seed,open(OUT+'/seed.json','w'),ensure_ascii=False,indent=1)
open(OUT+'/CNAME','w').write('rememberplaces.duckdns.org\n')
open(OUT+'/.nojekyll','w').write('')
icon='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0e6670"/><path d="M8 40 Q32 30 56 40" stroke="#9fd6d9" stroke-width="5" fill="none"/><path d="M32 12c-7 0-12 5-12 12 0 9 12 22 12 22s12-13 12-22c0-7-5-12-12-12z" fill="#fff"/><circle cx="32" cy="24" r="5" fill="#0e6670"/></svg>'''
open(OUT+'/icon.svg','w').write(icon)
json.dump({"name":"Patna Places","short_name":"Patna Places","start_url":"./","display":"standalone","background_color":"#f2f4f1","theme_color":"#0e6670","icons":[{"src":"icon-192.png","sizes":"192x192","type":"image/png"},{"src":"icon-512.png","sizes":"512x512","type":"image/png"},{"src":"icon.svg","sizes":"any","type":"image/svg+xml"}]},open(OUT+'/manifest.webmanifest','w'),indent=1)
open(OUT+'/README.md','w').write("# Patna Places\n\nA personal map of Patna: home, office and in-laws' house, landmarks, colour-coded roads, road distances, sketch maps and a memory quiz.\n\nServed with GitHub Pages at https://rememberplaces.duckdns.org\n\nMap data © OpenStreetMap contributors (ODbL). Satellite imagery © Esri, Maxar, Earthstar Geographics.\n")
print('built', os.listdir(OUT))
