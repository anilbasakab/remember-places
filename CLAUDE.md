# Remember Places: handover notes for Claude Code

This is Anil Basak's personal map of Patna, served by GitHub Pages at
https://rememberplaces.duckdns.org (DuckDNS A record → 185.199.108.153).
It was built in a claude.ai cloud session; this file tells a new session
what exists and what to do next. The owner is not a programmer. Explain
steps plainly and do the work yourself where you can.

## What the site is

A single static page, `index.html`, plus data files loaded with `fetch()`:

| File | What it holds | Built by |
|---|---|---|
| `index.html` | The whole app (HTML, CSS, JS in one file). Leaflet 1.9.4 from cdnjs. | `tools/pages_build.py` wraps `tools/patna-places.claude-ai.html` |
| `tiles.json` | OpenStreetMap tiles for central Patna, zoom 11–16, as base64 data URIs | `tools/fetch_osm_tiles.py` |
| `satellite.json` | Esri World Imagery tiles, same area and zooms | `tools/sat.py` |
| `roads.json` | Major roads (motorway→tertiary) with class nh / sh / city, route groups, lengths, start/end descriptions | Overpass query → `tools/build_roads.py` → `tools/geo_ends.py` |
| `roadnet.json` | Routable road graph (full drivable network of the Patna bbox) used for road distance and drive time | `py tools/build_roadnet.py` (downloads from Overpass in 21 tiles, caches in `tools/osm_cache/`, which is git-ignored). `tools/graph2.py` is the old cloud-only version. |
| `seed.json` | Home, office and in-laws' house pins (first-load data) | exported from the claude.ai version |
| `CNAME`, `manifest.webmanifest`, `icon*` | Domain and home-screen app settings | `tools/pages_build.py` |

Script paths inside `tools/` still point at the old cloud scratchpad; change them
to local paths before re-running.

## Features (all working)
- Home, office (Visvesvaraya Bhavan, RCD) and in-laws' house pins. Pins are locked; "Adjust position" unlocks one, and it also accepts pasted coordinates or a full Google Maps link.
- 74 landmarks, chowks and localities (`tools/data/landmarks.json`); entries with `"ax": 1` are approximate positions.
- Roads coloured by class: NH yellow, SH/MDR green, city maroon. Tap a road for length, start/end (A/B), lanes, and a "Department records" box.
- Layer chips plus a ☰ menu to show/hide each road class and landmark type (saved in localStorage).
- Road distance and drive time with route drawing, Map/Satellite toggle, Street View and Traffic links to Google, full-screen mode, search, sketch maps (canvas, PNG download), memory quiz, and a "How to remember Patna" card with a spine trace.
- Outside claude.ai, a small shim at the top of `index.html` stands in for `window.claude`: data saves in each browser's localStorage, seeded from `seed.json`.

## Known gaps
1. ~~Road network is incomplete.~~ **Fixed 7 Nov 2026.** `roadnet.json` now holds the full drivable network (32k nodes, 40k segments, 1.4 MB). The long detours were mostly caused by pins snapping onto a single one-way flyover next to the office, not by missing streets. Routing now (a) never snaps a pin onto a bridge, flyover or tunnel (bit 32 in each edge's flag), and (b) connects each pin to every road within 120 m of its nearest road and picks the best overall route. Office → Old Secretariat is now 1.3 km (it was 2.1 km), including about 200 m from each pin to a public road; the office campus lanes are `access=private` in OSM and are left out.
2. **Old Bypass** isn't named in OSM. Ask the owner for two points it passes, then add a label.
3. OSM numbers the southern bypass **NH-22**; the owner knows it as NH-30/NH-31. Confirm the current number with him.

## Next steps the owner asked for
1. ~~Fix gap 1~~ (done).
2. **Google Maps base layer**: built 7 Nov 2026 in `index.html` only (the claude.ai copy in `tools/` does not have it). Still to do: test routes, search and Street View once the owner has a real key.
   - "Google Maps ⚙" button: the owner pastes his key there; it is stored in that browser's localStorage (`patna-places:gkey`), never in the repo. Without a key nothing from Google loads.
   - With a key: Google / Google sat base layers via Leaflet.GoogleMutant 0.15.0 (official Maps JS underneath, our layers on top), live Traffic toggle, Street View inside the panel, "Google Maps · from home" box on place and landmark cards (Route class, `TRAFFIC_AWARE`, 10-minute in-memory cache) with "Show Google's route", and Google results under our own in search (`AutocompleteSuggestion`, Places API (New)).
   - Google places and routes are drawn only while a Google base layer is on (their terms). A rejected key switches back to the OSM map and the settings box says why.
   - Google made the old Directions API and Places API "legacy" on 1 Mar 2025, so the key needs **Maps JavaScript API, Routes API and Places API (New)**.
   Original request:
   - He creates a Google Cloud API key restricted to `rememberplaces.duckdns.org`, with the Maps JavaScript, Directions and Places APIs, and a usage cap so nothing is billed. Never ask him to paste the key in chat; add a settings box in the page that stores it in localStorage, or have him put it in a config file himself.
   - Keep our own layers (NH/SH/city colours, landmarks, chowks, sketch, quiz) drawn on top. Use Google for search, Directions (exact distance and live traffic), embedded Street View and the traffic layer.
   - Google's terms: no caching of Google tiles, and no extracting Google road geometry.
3. **Bihar overview map** with a "Patna | Bihar" switch in the same portal: state and district boundaries, 38 district HQs, all NHs, SHs between districts, main railway lines and junctions, major rivers, and hill shading (Esri World Hillshade). Data from OpenStreetMap. He may supply RCD's official State Highway list (numbers, from-to, lengths) to correct SH labels. His own pins: Madhepura (posting) and Kishanganj (hometown).

## Working rules
- Deploy by committing to branch `claude/remember-places-zyzwu9`; GitHub Pages serves that branch.
- Keep the attribution on screen: "© OpenStreetMap contributors"; with satellite, "Imagery © Esri, Maxar, Earthstar Geographics".
- The site is public and shows his home, office and in-laws' addresses, which he chose knowingly. Don't add more personal data without asking.
- Test on a 400 px wide phone view as well as desktop before pushing.
