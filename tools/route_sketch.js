// ---------- road routing (shortest drivable route on the OpenStreetMap network) ----------
const SPEED = { motorway: 45, trunk: 32, primary: 24, secondary: 22, tertiary: 20, unclassified: 18, residential: 15, living_street: 10, service: 10 };
let NET = null, netState = "loading";
const routeCache = new Map();
function netLoad() {
  fetch("roadnet.json").then((r) => r.json()).then((raw) => {
    const n = raw.n.length / 2, E = raw.e, m = E.length / 4;
    const lat = new Float64Array(n), lng = new Float64Array(n);
    for (let i = 0; i < n; i++) { lat[i] = raw.n[2 * i] / 1e5; lng[i] = raw.n[2 * i + 1] / 1e5; }
    const ea = new Int32Array(m), eb = new Int32Array(m), el = new Float64Array(m), ef = new Uint8Array(m), eh = new Uint8Array(m);
    const deg = new Int32Array(n + 1);
    for (let i = 0; i < m; i++) {
      ea[i] = E[4 * i]; eb[i] = E[4 * i + 1]; el[i] = Math.max(1, E[4 * i + 2]); ef[i] = E[4 * i + 3] >> 4; eh[i] = E[4 * i + 3] & 15;
      deg[ea[i] + 1]++; if (!ef[i]) deg[eb[i] + 1]++;
    }
    for (let i = 0; i < n; i++) deg[i + 1] += deg[i];
    const adjTo = new Int32Array(deg[n]), adjE = new Int32Array(deg[n]), fill = deg.slice(0, n);
    for (let i = 0; i < m; i++) {
      adjTo[fill[ea[i]]] = eb[i]; adjE[fill[ea[i]]++] = i;
      if (!ef[i]) { adjTo[fill[eb[i]]] = ea[i]; adjE[fill[eb[i]]++] = i; }
    }
    // edge geometry (absolute lat/lng arrays, including both ends)
    const geom = (i, fwd = true) => {
      const g = raw.g[i], pts = [[lat[ea[i]], lng[ea[i]]]];
      let x = Math.round(lat[ea[i]] * 1e5), y = Math.round(lng[ea[i]] * 1e5);
      for (let k = 0; k < g.length; k += 2) { x += g[k]; y += g[k + 1]; pts.push([x / 1e5, y / 1e5]); }
      pts.push([lat[eb[i]], lng[eb[i]]]);
      return fwd ? pts : pts.reverse();
    };
    // grid index of edges for snapping
    const CELL = 0.004, grid = new Map();
    for (let i = 0; i < m; i++) {
      const pts = geom(i), seen = new Set();
      for (const p of pts) { const k = Math.floor(p[0] / CELL) + ":" + Math.floor(p[1] / CELL); if (!seen.has(k)) { seen.add(k); (grid.get(k) || grid.set(k, []).get(k)).push(i); } }
    }
    NET = { n, m, lat, lng, ea, eb, el, ef, eh, deg, adjTo, adjE, geom, grid, CELL, hw: raw.hw };
    netState = "ready"; routeCache.clear(); render();
  }).catch(() => { netState = "failed"; render(); });
}
function netSnap(pt) {
  const { CELL, grid, geom } = NET, ci = Math.floor(pt.lat / CELL), cj = Math.floor(pt.lng / CELL);
  let best = null;
  for (let r = 0; r <= 4 && !best; r++) {
    for (let di = -r; di <= r; di++) for (let dj = -r; dj <= r; dj++) {
      if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
      for (const e of grid.get((ci + di) + ":" + (cj + dj)) || []) {
        const pts = geom(e); let along = 0;
        const kx = Math.cos(pt.lat * Math.PI / 180);
        for (let j = 0; j < pts.length - 1; j++) {
          const ax = pts[j][1] * kx, ay = pts[j][0], bx = pts[j + 1][1] * kx, by = pts[j + 1][0], px = pt.lng * kx, py = pt.lat;
          const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
          const t = L2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2)) : 0;
          const q = { lat: ay + t * dy, lng: (ax + t * dx) / kx }, d = km(pt, q) * 1000;
          const segm = km({ lat: pts[j][0], lng: pts[j][1] }, { lat: pts[j + 1][0], lng: pts[j + 1][1] }) * 1000;
          if (!best || d < best.d) best = { e, d, q, along: along + t * segm, seg: j };
          along += segm;
        }
      }
    }
  }
  if (best) { const tot = geom(best.e).reduce((s, p, i, a) => i ? s + km({ lat: a[i - 1][0], lng: a[i - 1][1] }, { lat: p[0], lng: p[1] }) * 1000 : 0, 0) || 1; best.f = best.along / tot; }
  return best;
}
function heapPush(h, c, v) { h.push([c, v]); let i = h.length - 1; while (i) { const p = (i - 1) >> 1; if (h[p][0] <= h[i][0]) break; [h[p], h[i]] = [h[i], h[p]]; i = p; } }
function heapPop(h) { const top = h[0], last = h.pop(); if (h.length) { h[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let s = i; if (l < h.length && h[l][0] < h[s][0]) s = l; if (r < h.length && h[r][0] < h[s][0]) s = r; if (s === i) break; [h[s], h[i]] = [h[i], h[s]]; i = s; } } return top; }
// one search per origin, reused for every destination
function netTree(origin) {
  const key = origin.lat.toFixed(5) + "," + origin.lng.toFixed(5);
  if (routeCache.has(key)) return routeCache.get(key);
  const N = NET, s = netSnap(origin); if (!s) return null;
  const dist = new Float64Array(N.n).fill(Infinity), prev = new Int32Array(N.n).fill(-1), h = [];
  const L = N.el[s.e];
  // leave the snapped point toward b (always allowed) and toward a (if two-way)
  const toB = L * (1 - s.f), toA = L * s.f;
  dist[N.eb[s.e]] = toB; heapPush(h, toB, N.eb[s.e]);
  if (!N.ef[s.e] && toA < dist[N.ea[s.e]]) { dist[N.ea[s.e]] = toA; heapPush(h, toA, N.ea[s.e]); }
  while (h.length) {
    const [c, u] = heapPop(h); if (c > dist[u]) continue;
    for (let k = N.deg[u]; k < N.deg[u + 1]; k++) {
      const v = N.adjTo[k], e = N.adjE[k], nc = c + N.el[e];
      if (nc < dist[v]) { dist[v] = nc; prev[v] = e; heapPush(h, nc, v); }
    }
  }
  const tree = { s, dist, prev };
  routeCache.set(key, tree); return tree;
}
// road distance (km), drive time (min) and path from origin to dest
function roadRoute(origin, dest) {
  if (!NET) return null;
  const T = netTree(origin), d = netSnap(dest); if (!T || !d) return null;
  const N = NET, L = N.el[d.e];
  let best = Infinity, via = -1;
  const fromA = T.dist[N.ea[d.e]] + L * d.f; if (fromA < best) { best = fromA; via = N.ea[d.e]; }
  if (!N.ef[d.e]) { const fromB = T.dist[N.eb[d.e]] + L * (1 - d.f); if (fromB < best) { best = fromB; via = N.eb[d.e]; } }
  if (T.s.e === d.e && (d.f >= T.s.f || !N.ef[d.e])) { const same = Math.abs(d.f - T.s.f) * L; if (same < best) { best = same; via = -2; } }
  if (!isFinite(best)) return null;
  // rebuild the path and its drive time
  const legs = []; let mins = 0;
  const addTime = (e, metres) => { mins += metres / 1000 / (SPEED[N.hw[N.eh[e]]] || 15) * 60; };
  if (via === -2) addTime(d.e, best);
  if (via >= 0) {
    addTime(d.e, via === N.ea[d.e] ? L * d.f : L * (1 - d.f));
    let u = via, guard = 0;
    while (T.prev[u] !== -1 && guard++ < 200000) {
      const e = T.prev[u], from = N.eb[e] === u ? N.ea[e] : N.eb[e];
      legs.push(N.geom(e, N.eb[e] === u)); addTime(e, N.el[e]); u = from;
    }
    addTime(T.s.e, u === N.eb[T.s.e] ? N.el[T.s.e] * (1 - T.s.f) : N.el[T.s.e] * T.s.f);
  }
  const path = [[origin.lat, origin.lng], [T.s.q.lat, T.s.q.lng]];
  for (const g of legs.reverse()) path.push(...g);
  path.push([d.q.lat, d.q.lng], [dest.lat, dest.lng]);
  const access = (T.s.d + d.d) * 1.3; // short walk/drive from the door to the mapped road
  const kmTotal = (best + access) / 1000;
  return { km: kmTotal, min: Math.max(1, Math.round(mins + access / 1000 / 12 * 60)), path };
}
function distText(a, b, withTime = true) {
  const r = roadRoute(a, b);
  if (r) return `${fmtKm(r.km)} by road${withTime ? ` · about ${r.min} min` : ""}`;
  return `${fmtKm(km(a, b))} straight line`;
}
function drawRoute(a, b) {
  const r = roadRoute(a, b); if (!r) return;
  L.polyline(r.path, { color: cssVar("--sheet"), weight: 9, opacity: 0.9, interactive: false }).addTo(lineLayer);
  L.polyline(r.path, { color: cssVar("--ganga"), weight: 5, opacity: 0.95, interactive: false }).addTo(lineLayer);
}
netLoad();

// ---------- sketch maps (not to scale) ----------
let sketchSel = [];        // [{kind, key, name, hi?, lat?, lng?, cls?, color}]
let sketchSeed = 1;
function sketchCatalog() {
  const out = [];
  for (const p of places) out.push({ kind: "place", key: "p:" + p.id, name: p.name, lat: p.lat, lng: p.lng, color: cat(p.category).color });
  LANDMARKS.forEach((l, i) => out.push({ kind: "lm", key: "l:" + i, name: l.name, hi: l.hi, lat: l.lat, lng: l.lng, color: KINDS[l.kind].color }));
  if (RD) for (const k of [...new Set(BADGES.map((b) => b[0]))]) if (RD.routes[k]) out.push({ kind: "road", key: "r:" + k, route: k, name: BADGES.find((b) => b[0] === k)[1], cls: RD.routes[k].cls });
  return out;
}
function sketchView() {
  const q = (view.q || "").trim().toLowerCase();
  const cat_ = sketchCatalog(), chosen = new Set(sketchSel.map((s) => s.key));
  const hits = cat_.filter((c) => !chosen.has(c.key) && (!q || c.name.toLowerCase().includes(q) || (c.hi || "").includes(q))).slice(0, q ? 12 : 8);
  const chip = (s) => `<button class="schip" type="button" data-unsk="${esc(s.key)}" title="Remove"><span class="dot${s.kind === "road" ? " bar" : ""}" style="--c:${s.kind === "road" ? `var(--${s.cls})` : s.color}"></span>${esc(s.name)} ✕</button>`;
  const hit = (c) => `<li><button type="button" data-addsk="${esc(c.key)}"><span class="dot${c.kind === "road" ? " bar" : ""}" style="--c:${c.kind === "road" ? `var(--${c.cls})` : c.color}"></span><span class="nm">${esc(c.name)}<span class="sub">${c.kind === "road" ? "Road" : c.kind === "place" ? "Your place" : "Landmark"}</span></span></button></li>`;
  return `<div class="row"><button class="btn" type="button" data-act="back">← All places</button></div>
  <div><p class="eyebrow">Sketch map</p><h2>Pick places and roads</h2></div>
  <p class="sub-note">Choose 2 to 8. The sketch keeps directions, shortens long gaps, spreads out close spots, and writes the road distance on each link.</p>
  <div class="chips">${sketchSel.map(chip).join("") || `<span class="sub-note">Nothing picked yet.</span>`}</div>
  <form class="edit" id="f-sk-title"><label for="sk-title">Sketch title<input id="sk-title" maxlength="80" value="${esc(view.title || "")}" placeholder="e.g. Route to the Collectorate"></label></form>
  <label class="edit" for="sk-q" style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted);font-weight:500">Find a place or road<input id="sk-q" value="${esc(view.q || "")}" placeholder="Type: Gandhi, NH-22, home…" autocomplete="off" style="border:1px solid var(--rule);border-radius:6px;padding:7px 9px;background:var(--paper);color:var(--ink);font-size:15px"></label>
  <ul class="list">${hits.map(hit).join("")}</ul>
  <div class="row"><button class="btn primary" type="button" data-act="sk-draw" ${sketchSel.length < 2 ? "disabled" : ""}>Draw sketch</button>${sketchSel.length ? `<button class="btn" type="button" data-act="sk-clear">Clear</button>` : ""}</div>
  ${netState !== "ready" ? `<p class="sub-note">Road distances load in a moment; until then links show straight-line distance.</p>` : ""}`;
}
function kmXY(ref) { const kx = Math.cos(ref.lat * Math.PI / 180) * 111.32; return (lat, lng) => [(lng - ref.lng) * kx, (lat - ref.lat) * 110.57]; }
function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function drawSketch(canvas) {
  const W2 = 1600, H2 = 1100, DPR = 2;
  canvas.width = W2 * DPR; canvas.height = H2 * DPR;
  const ctx = canvas.getContext("2d"); ctx.scale(DPR, DPR);
  const ink = "#1f2a2a", paper = "#fbfaf5", soft = "#6b7472";
  const RC = { nh: ["#e9b000", "#7a5c00"], sh: ["#1f9d55", "#0c4a28"], city: ["#9c3344", "#4d1520"] };
  const rand = rng(sketchSeed);
  const hand = "'Kalam', 'Comic Sans MS', 'Segoe Print', cursive";
  ctx.fillStyle = paper; ctx.fillRect(0, 0, W2, H2);
  const pts = sketchSel.filter((s) => s.kind !== "road"), roads = sketchSel.filter((s) => s.kind === "road");
  // reference frame
  let allLL = pts.map((p) => [p.lat, p.lng]);
  const roadWays = roads.map((r) => RD.ways.filter((w) => w[1] === r.route).map((w) => w[3]));
  if (!allLL.length) allLL = roadWays.flat(2);
  const ref = { lat: allLL.reduce((s, p) => s + p[0], 0) / allLL.length, lng: allLL.reduce((s, p) => s + p[1], 0) / allLL.length };
  const P = kmXY(ref);
  const tp = pts.map((p) => P(p.lat, p.lng));
  // keep only the part of each road near the chosen places
  let bx0 = Math.min(...tp.map((p) => p[0])), bx1 = Math.max(...tp.map((p) => p[0])), by0 = Math.min(...tp.map((p) => p[1])), by1 = Math.max(...tp.map((p) => p[1]));
  if (!tp.length) { const rp = allLL.map((p) => P(p[0], p[1])); bx0 = Math.min(...rp.map((p) => p[0])); bx1 = Math.max(...rp.map((p) => p[0])); by0 = Math.min(...rp.map((p) => p[1])); by1 = Math.max(...rp.map((p) => p[1])); }
  const pad = Math.max(1.5, 0.25 * Math.max(bx1 - bx0, by1 - by0));
  bx0 -= pad; bx1 += pad; by0 -= pad; by1 += pad;
  const roadParts = roadWays.map((ws) => {
    const parts = [];
    for (const g of ws) { let cur = []; for (const [la, ln] of g) { const q = P(la, ln); if (q[0] >= bx0 && q[0] <= bx1 && q[1] >= by0 && q[1] <= by1) cur.push(q); else { if (cur.length > 1) parts.push(cur); cur = []; } } if (cur.length > 1) parts.push(cur); }
    return parts;
  });
  // layout of the chosen places: a spanning tree of nearest links, each link keeps its true bearing, lengths compressed (log)
  const n = tp.length, D = (i, j) => Math.hypot(tp[i][0] - tp[j][0], tp[i][1] - tp[j][1]);
  const links = [];
  if (n > 1) {
    const inT = new Array(n).fill(false); inT[0] = true;
    for (let c = 1; c < n; c++) { let b = null; for (let i = 0; i < n; i++) if (inT[i]) for (let j = 0; j < n; j++) if (!inT[j] && (!b || D(i, j) < b[2])) b = [i, j, D(i, j)]; inT[b[1]] = true; links.push(b); }
  }
  const dists = links.map((l) => l[2]).sort((a, b) => a - b), s0 = Math.max(0.15, (dists[Math.floor(dists.length / 2)] || 1) / 3);
  const S = tp.map(() => null);
  if (n) S[0] = [0, 0];
  const placed = new Set([0]);
  let guard = 0;
  while (placed.size < n && guard++ < 100) for (const [i, j] of links) {
    const [a, b] = placed.has(i) && !placed.has(j) ? [i, j] : placed.has(j) && !placed.has(i) ? [j, i] : [null, null];
    if (a === null) continue;
    const vx = tp[b][0] - tp[a][0], vy = tp[b][1] - tp[a][1], r = Math.hypot(vx, vy) || 1e-6, Lc = Math.log1p(r / s0) + 0.6;
    S[b] = [S[a][0] + vx / r * Lc, S[a][1] + vy / r * Lc]; placed.add(b);
  }
  // spread out anything still too close
  for (let it = 0; it < 80; it++) for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const dx = S[j][0] - S[i][0], dy = S[j][1] - S[i][1], d = Math.hypot(dx, dy), min = 0.9;
    if (d < min) { const ux = d ? dx / d : (tp[j][0] - tp[i][0]) || 1, uy = d ? dy / d : (tp[j][1] - tp[i][1]); const k = (min - d) / 2 / (Math.hypot(ux, uy) || 1); S[i][0] -= ux * k; S[i][1] -= uy * k; S[j][0] += ux * k; S[j][1] += uy * k; }
  }
  // warp: global similarity + inverse-distance blend so roads follow the moved places
  let warp;
  if (n >= 2) {
    const cx = tp.reduce((s, p) => s + p[0], 0) / n, cy = tp.reduce((s, p) => s + p[1], 0) / n, sx = S.reduce((s, p) => s + p[0], 0) / n, sy = S.reduce((s, p) => s + p[1], 0) / n;
    const k = (S.reduce((s, p) => s + Math.hypot(p[0] - sx, p[1] - sy), 0) / n) / ((tp.reduce((s, p) => s + Math.hypot(p[0] - cx, p[1] - cy), 0) / n) || 1);
    const T0 = (p) => [sx + (p[0] - cx) * k, sy + (p[1] - cy) * k];
    const off = tp.map((p, i) => [S[i][0] - T0(p)[0], S[i][1] - T0(p)[1]]);
    warp = (p) => { const b = T0(p); let wx = 0, wy = 0, ws = 0; for (let i = 0; i < n; i++) { const d2 = (p[0] - tp[i][0]) ** 2 + (p[1] - tp[i][1]) ** 2 + 1e-6, w = 1 / (d2 * d2); wx += w * off[i][0]; wy += w * off[i][1]; ws += w; } return [b[0] + wx / ws, b[1] + wy / ws]; };
  } else { const c = n ? tp[0] : [0, 0], o = n ? S[0] : [0, 0]; warp = (p) => [o[0] + p[0] - c[0], o[1] + p[1] - c[1]]; }
  let rparts = roadParts.map((parts) => parts.map((g) => g.map(warp)));
  // fit everything on the sheet (north up)
  const all = S.filter(Boolean).concat(rparts.flat(2));
  const X0 = Math.min(...all.map((p) => p[0])), X1 = Math.max(...all.map((p) => p[0])), Y0 = Math.min(...all.map((p) => p[1])), Y1 = Math.max(...all.map((p) => p[1]));
  const M = { l: 110, r: 110, t: 150, b: 120 }, sc = Math.min((W2 - M.l - M.r) / ((X1 - X0) || 1), (H2 - M.t - M.b) / ((Y1 - Y0) || 1));
  const ox = M.l + ((W2 - M.l - M.r) - (X1 - X0) * sc) / 2, oy = M.t + ((H2 - M.t - M.b) - (Y1 - Y0) * sc) / 2;
  const px = (p) => [ox + (p[0] - X0) * sc, H2 - (oy + (p[1] - Y0) * sc)];
  const simp = (a, eps) => { if (a.length < 3) return a; let dm = 0, ix = 0; const [x0, y0] = a[0], [x1, y1] = a[a.length - 1], L = Math.hypot(x1 - x0, y1 - y0) || 1e-9; for (let i = 1; i < a.length - 1; i++) { const d = Math.abs((y1 - y0) * a[i][0] - (x1 - x0) * a[i][1] + x1 * y0 - y1 * x0) / L; if (d > dm) { dm = d; ix = i; } } return dm > eps ? simp(a.slice(0, ix + 1), eps).slice(0, -1).concat(simp(a.slice(ix), eps)) : [a[0], a[a.length - 1]]; };
  const rpx = rparts.map((parts) => parts.map((g) => simp(g.map(px), 7)).filter((g) => g.length > 1));
  const sp = S.map((p) => p && px(p));
  // places that sit on a chosen road are pulled onto it
  pts.forEach((p, i) => {
    roads.forEach((r, ri) => {
      const near = roadWays[ri].some((g) => g.some(([la, ln]) => km({ lat: la, lng: ln }, p) < 0.2));
      if (!near) return;
      let best = null;
      for (const g of rpx[ri]) for (let j = 0; j < g.length - 1; j++) { const [ax, ay] = g[j], [bx, by] = g[j + 1], dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy, t = L2 ? Math.max(0, Math.min(1, ((sp[i][0] - ax) * dx + (sp[i][1] - ay) * dy) / L2)) : 0, q = [ax + t * dx, ay + t * dy], d = Math.hypot(q[0] - sp[i][0], q[1] - sp[i][1]); if (!best || d < best[1]) best = [q, d]; }
      if (best && best[1] < 90) sp[i] = best[0];
    });
  });
  const wob = (a) => a + (rand() - 0.5) * 2.2;
  const rough = (g, w, col) => { for (let pass = 0; pass < 2; pass++) { ctx.beginPath(); ctx.strokeStyle = col; ctx.lineWidth = w; ctx.lineCap = "round"; ctx.lineJoin = "round"; g.forEach(([x, y], k) => k ? ctx.lineTo(wob(x), wob(y)) : ctx.moveTo(wob(x), wob(y))); ctx.stroke(); } };
  // paper border
  ctx.strokeStyle = ink; ctx.lineWidth = 2.5; ctx.strokeRect(30, 30, W2 - 60, H2 - 60);
  // roads: dark casing + colour fill, double-line look
  rpx.forEach((parts, ri) => { const [fillc, edge] = RC[roads[ri].cls]; for (const g of parts) rough(g, 15, edge); for (const g of parts) rough(g, 10, fillc); });
  // road labels along their longest stretch
  const boxes = [];
  ctx.textBaseline = "middle";
  rpx.forEach((parts, ri) => {
    let best = null; for (const g of parts) for (let j = 0; j < g.length - 1; j++) { const L = Math.hypot(g[j + 1][0] - g[j][0], g[j + 1][1] - g[j][1]); if (!best || L > best[2]) best = [g[j], g[j + 1], L]; }
    if (!best) return;
    let [a, b] = best; if (b[0] < a[0]) [a, b] = [b, a];
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    ctx.save(); ctx.translate(mx, my); ctx.rotate(ang); ctx.font = `700 22px ${hand}`; const t = roads[ri].name, tw = ctx.measureText(t).width;
    ctx.fillStyle = paper; ctx.fillRect(-tw / 2 - 8, -30, tw + 16, 26); ctx.fillStyle = RC[roads[ri].cls][1]; ctx.textAlign = "center"; ctx.fillText(t, 0, -17); ctx.restore();
    boxes.push([mx - tw / 2, my - 30, tw, 30]);
  });
  // distance links between neighbouring places
  links.forEach(([i, j]) => {
    const a = sp[i], b = sp[j], r = roadRoute(pts[i], pts[j]), label = r ? `${fmtKm(r.km)} by road` : `${fmtKm(km(pts[i], pts[j]))} (straight)`;
    ctx.save(); ctx.setLineDash([10, 9]); ctx.strokeStyle = soft; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.restore();
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2; ctx.font = `700 21px ${hand}`; const tw = ctx.measureText(label).width;
    ctx.fillStyle = paper; ctx.strokeStyle = soft; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.roundRect?.(mx - tw / 2 - 10, my - 16, tw + 20, 32, 14); ctx.fill(); ctx.stroke();
    ctx.fillStyle = ink; ctx.textAlign = "center"; ctx.fillText(label, mx, my + 1);
    boxes.push([mx - tw / 2 - 10, my - 16, tw + 20, 32]);
  });
  // places: pins and labels placed where they overlap least
  const over = (r) => boxes.reduce((s, b) => s + Math.max(0, Math.min(r[0] + r[2], b[0] + b[2]) - Math.max(r[0], b[0])) * Math.max(0, Math.min(r[1] + r[3], b[1] + b[3]) - Math.max(r[1], b[1])), 0) + (r[0] < 40 || r[1] < 40 || r[0] + r[2] > W2 - 40 || r[1] + r[3] > H2 - 40 ? 1e6 : 0);
  sp.forEach(([x, y]) => boxes.push([x - 14, y - 14, 28, 28]));
  pts.forEach((p, i) => {
    const [x, y] = sp[i];
    ctx.beginPath(); ctx.arc(x, y, 13, 0, Math.PI * 2); ctx.fillStyle = p.color.startsWith("var") ? cssVar(p.color.slice(4, -1)) || ink : p.color; ctx.fill(); ctx.lineWidth = 3; ctx.strokeStyle = ink; ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2); ctx.fillStyle = paper; ctx.fill();
    ctx.font = `700 26px ${hand}`; const tw = ctx.measureText(p.name).width; ctx.font = `400 19px ${hand}`; const hw2 = p.hi ? ctx.measureText(p.hi).width : 0;
    const w = Math.max(tw, hw2), h = p.hi ? 52 : 30;
    const cands = [[x + 22, y - h / 2], [x - 22 - w, y - h / 2], [x - w / 2, y - 24 - h], [x - w / 2, y + 22], [x + 18, y - h - 10], [x - 18 - w, y - h - 10], [x + 18, y + 10], [x - 18 - w, y + 10]];
    let best = cands[0], bs = Infinity; for (const c of cands) { const sc2 = over([c[0], c[1], w, h]); if (sc2 < bs) { bs = sc2; best = c; } }
    ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = paper; ctx.globalAlpha = 0.85; ctx.fillRect(best[0] - 4, best[1] - 2, w + 8, h + 2); ctx.globalAlpha = 1;
    ctx.fillStyle = ink; ctx.font = `700 26px ${hand}`; ctx.fillText(p.name, best[0], best[1]);
    if (p.hi) { ctx.fillStyle = soft; ctx.font = `400 19px ${hand}`; ctx.fillText(p.hi, best[0], best[1] + 30); }
    boxes.push([best[0], best[1], w, h]); ctx.textBaseline = "middle";
  });
  // title, north arrow, notes
  ctx.textAlign = "left"; ctx.fillStyle = ink; ctx.font = `700 40px ${hand}`; ctx.fillText(view.title || "Sketch map", 64, 86);
  ctx.font = `400 20px ${hand}`; ctx.fillStyle = soft; ctx.fillText(`Patna · ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}`, 66, 124);
  const nx = W2 - 100, ny = 110; ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(nx, ny - 45); ctx.lineTo(nx - 16, ny + 15); ctx.lineTo(nx, ny + 3); ctx.lineTo(nx + 16, ny + 15); ctx.closePath(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(nx, ny - 45); ctx.lineTo(nx, ny + 3); ctx.lineTo(nx + 16, ny + 15); ctx.closePath(); ctx.fill();
  ctx.font = `700 26px ${hand}`; ctx.textAlign = "center"; ctx.fillText("N", nx, ny - 62);
  ctx.save(); ctx.translate(W2 - 170, H2 - 80); ctx.rotate(-0.06); ctx.strokeStyle = "#a62a2a"; ctx.lineWidth = 3; ctx.strokeRect(-110, -26, 220, 50); ctx.fillStyle = "#a62a2a"; ctx.font = `700 26px ${hand}`; ctx.fillText("NOT TO SCALE", 0, 1); ctx.restore();
  ctx.textAlign = "left"; ctx.fillStyle = soft; ctx.font = `400 18px ${hand}`;
  ctx.fillText(netState === "ready" ? "Distances are by road (shortest drivable route)." : "Distances are straight-line.", 64, H2 - 92);
  const used = [...new Set(roads.map((r) => r.cls))];
  let lx = 64; for (const c of used) { ctx.fillStyle = RC[c][0]; ctx.fillRect(lx, H2 - 66, 34, 10); ctx.fillStyle = soft; const t = { nh: "National Highway", sh: "State Highway / MDR", city: "City road" }[c]; ctx.fillText(t, lx + 42, H2 - 61); lx += 60 + ctx.measureText(t).width; }
}
async function openSketch() {
  const host = $("#sketch"), cv = $("#sketch-canvas");
  host.hidden = false;
  try { await document.fonts.load("700 26px Kalam"); } catch {}
  drawSketch(cv);
}
async function saveSketch() {
  const cv = $("#sketch-canvas"), dl = await window.claude?.use?.("downloads").catch?.(() => null);
  if (!dl) { flash("Saving isn't available in this view. Open the page on claude.ai to save the sketch."); return; }
  cv.toBlob(async (blob) => {
    const name = (view.title || "patna-sketch").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "patna-sketch";
    try { await dl.save({ filename: `${name}.png`, data: blob }); }
    catch (e) { if (e?.code !== "declined") flash("The image could not be saved. Try again."); }
  }, "image/png");
}
