"""Fill lon/lat of every node from its "geo" query — the model never types coordinates.

usage: python3 -I template/tools/geocode.py <cityDir>

Order of lookup for each node (first hit inside the city's admin bounding box wins):
  1. zh.wikipedia page coordinates of the title  geo
  2. OpenStreetMap Nominatim search  "<geo>"  then  "<city> <geo>"   (restricted to the city box)
Nodes that already have lon/lat and "geoLocked": true are left alone.
Results go to nodes.json (lon, lat, geoSource) and research/geocode.log.
Exit code 1 + a Chinese message if a node cannot be located: change its "geo" (e.g. a nearby landmark).
"""
import json, os, subprocess, sys, time, urllib.parse

UA = 'CityNianlunBot/1.0 (documentary research)'
CITY = os.path.abspath(sys.argv[1])
city = json.load(open(os.path.join(CITY, 'city.json')))
NP = os.path.join(CITY, 'nodes.json')
data = json.load(open(NP))
bb = city.get('adminBBox') or [city['center']['lon'] - .8, city['center']['lat'] - .8, city['center']['lon'] + .8, city['center']['lat'] + .8]
pad = 0.15
inside = lambda lon, lat: bb[0] - pad <= lon <= bb[2] + pad and bb[1] - pad <= lat <= bb[3] + pad
log = open(os.path.join(CITY, 'research', 'geocode.log'), 'a')


def get(url):
    for a in range(4):
        try:
            return json.loads(subprocess.check_output(['curl', '-s', '-f', '-m', '40', '-A', UA, url]))
        except Exception:
            time.sleep(2 * (a + 1))
    return None


def wiki(q):
    d = get('https://zh.wikipedia.org/w/api.php?action=query&prop=coordinates&redirects=1&format=json&titles=' + urllib.parse.quote(q))
    if not d:
        return None
    pg = next(iter(d['query']['pages'].values()))
    c = (pg.get('coordinates') or [None])[0]
    return (c['lon'], c['lat'], 'zh.wikipedia:' + pg['title']) if c else None


def osm(q):
    vb = f'{bb[0]},{bb[3]},{bb[2]},{bb[1]}'
    d = get('https://nominatim.openstreetmap.org/search?format=json&limit=5&accept-language=zh&bounded=1&viewbox=' + vb
            + '&q=' + urllib.parse.quote(q))
    time.sleep(1.1)   # Nominatim usage policy: max 1 request / s
    for r in d or []:
        return float(r['lon']), float(r['lat']), 'OSM Nominatim:' + r.get('display_name', '')[:60]
    return None


bad = []
for i, n in enumerate(data['nodes']):
    q = (n.get('geo') or n.get('place') or '').strip()
    if n.get('lon') is not None and (n.get('geoLocked') or 'geo' not in n or n.get('geoQuery') == q):
        continue
    hit = None
    for f, qq in ((wiki, q), (osm, q), (osm, f"{city['name']} {q}")):
        if not qq:
            continue
        r = f(qq)
        if r and inside(r[0], r[1]):
            hit = r; break
    if not hit:
        bad.append(f"节点 {i + 1}（{n.get('id')} {n.get('place')}）：用 geo=\"{q}\" 在{city['name']}范围内查不到坐标。请把 geo 改成附近更有名的地标或维基百科条目名，再运行。")
        continue
    n['lon'], n['lat'], n['geoSource'], n['geoQuery'] = round(hit[0], 4), round(hit[1], 4), hit[2], q
    print(f"{n.get('id')} {q} -> {n['lon']}, {n['lat']}  ({hit[2]})")
    log.write(f"{n.get('id')}\t{q}\t{n['lon']}\t{n['lat']}\t{hit[2]}\n")
json.dump(data, open(NP, 'w'), ensure_ascii=False, indent=1)
if bad:
    print('\n'.join(['GEOCODE 失败：'] + bad))
    sys.exit(1)
