"""Step 1c — build the 3D map for any city from open data (no hand tuning).

usage: python3 -I template/tools/fetch_map.py <cityDir> [--days 900]

Reads <cityDir>/city.json (center) and nodes.json (node coordinates). Writes <cityDir>/assets/map/:
  core_h.bin / wide_h.bin    float32 heights (m) on lon/mercator-lat grids (768² core, 256² wide)
  sat_hi_4k.jpg / sat_lo_2k.jpg   true-colour satellite mosaics
  water.png                  water mask aligned with sat_hi (specular + flattening)
  grid.json                  grid sizes + extents
and records map.core / map.wide / map.satellite / mapCredit in city.json.

Data (all open, credited on screen + in image-sources.md):
  satellite  NASA GIBS WMS, HLS S30/L30 (Harmonized Landsat Sentinel-2, 30 m). The least cloudy
             cool-season date is picked automatically; gaps are filled from the next-best dates.
  terrain    AWS Terrain Tiles (Terrarium, z11)
  water      EC JRC / Google Global Surface Water 2021, occurrence layer (z11)
"""
import concurrent.futures as cf
import datetime, json, math, os, subprocess, sys, time
import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
CITY = os.path.abspath(sys.argv[1])
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 900
M = os.path.join(CITY, 'assets', 'map')
TMP = os.path.join(CITY, 'build', 'mapdl')
os.makedirs(M, exist_ok=True); os.makedirs(TMP, exist_ok=True)
UA = 'CityNianlunBot/1.0 (documentary map; open data)'
R = 6378137.0
G = 768

city = json.load(open(os.path.join(CITY, 'city.json')))
_np = os.path.join(CITY, 'nodes.json')
nodes = json.load(open(_np))['nodes'] if os.path.exists(_np) else []   # before the node table exists: centre only


# ---------------------------------------------------------------- extents
def extents():
    """core: node cloud + city centre, padded, at least ~0.97° x 0.79° (≈ 92 x 88 km);
    wide: core + 0.45° each side (the far ring that fades into fog)."""
    mp = city.get('map', {})
    if mp.get('core') and mp.get('wide'):
        return mp['core'], mp['wide']
    lons = [n['lon'] for n in nodes] + [city['center']['lon']]
    lats = [n['lat'] for n in nodes] + [city['center']['lat']]
    lon0, lon1, lat0, lat1 = min(lons) - .15, max(lons) + .15, min(lats) - .15, max(lats) + .15
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    hw, hh = max((lon1 - lon0) / 2, .485), max((lat1 - lat0) / 2, .395)
    core = [round(cx - hw, 3), round(cy - hh, 3), round(cx + hw, 3), round(cy + hh, 3)]
    wide = [round(core[0] - .45, 3), round(core[1] - .35, 3), round(core[2] + .45, 3), round(core[3] + .38, 3)]
    return core, wide


def curl(url, path, tries=6, proxy=True):
    if os.path.exists(path) and os.path.getsize(path) > 100:
        try:
            Image.open(path).load(); return True
        except Exception:
            pass
    for a in range(tries):
        cmd = ['curl', '-s', '-f', '-m', '120', '-A', UA, '-o', path, url]
        if (a % 2 == 1) == proxy:
            cmd[1:1] = ['--noproxy', '*']
        if subprocess.call(cmd) == 0 and os.path.exists(path) and os.path.getsize(path) > 100:
            try:
                Image.open(path).load(); return True
            except Exception:
                pass
        time.sleep(1.5 * (a + 1))
    return False


def merc(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def inv(x, y):
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def lon2x(lon, z): return (lon + 180) / 360 * 2 ** z
def lat2y(lat, z):
    r = math.radians(lat); return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z
def x2lon(x, z): return x / 2 ** z * 360 - 180
def y2lat(y, z): return math.degrees(math.atan(math.sinh(math.pi - 2 * math.pi * y / 2 ** z)))
def lat2my(lat): return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


# ---------------------------------------------------------------- satellite date
LAYERS = {'S30': 'HLS_S30_Nadir_BRDF_Adjusted_Reflectance', 'L30': 'HLS_L30_Nadir_BRDF_Adjusted_Reflectance'}


def probe_dates(core):
    out = os.path.join(TMP, 'probe'); os.makedirs(out, exist_ok=True)
    today = datetime.date.today()
    d0 = today - datetime.timedelta(days=DAYS + 60)
    dates = [d0 + datetime.timedelta(days=i) for i in range(DAYS)]
    dates = [d for d in dates if d.month in (10, 11, 12, 1, 2, 3, 4)]   # cool season: less haze and cloud

    def one(job):
        L, d = job
        f = os.path.join(out, f'{L}_{d}.png')
        if not os.path.exists(f):
            u = ('https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0'
                 f'&LAYERS={LAYERS[L]}&CRS=EPSG:4326&BBOX={core[1]},{core[0]},{core[3]},{core[2]}&WIDTH=200&HEIGHT=180'
                 f'&FORMAT=image/png&TRANSPARENT=TRUE&TIME={d}')
            subprocess.call(['curl', '-s', '-m', '40', '-A', UA, '-o', f, u])
        try:
            a = np.asarray(Image.open(f).convert('RGBA'), np.float32)
        except Exception:
            return None
        cov = (a[..., 3] > 0).mean()
        rgb = a[..., :3][a[..., 3] > 0]
        bright = (rgb.mean(1) > 170).mean() if len(rgb) else 1.0
        return dict(layer=L, date=str(d), cov=round(float(cov), 3), cloud=round(float(bright), 3))

    jobs = [(L, d) for L in LAYERS for d in dates]
    res = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(one, jobs):
            if r and r['cov'] > 0.3:
                res.append(r)
    res.sort(key=lambda r: -(r['cov'] - 3 * r['cloud']))
    json.dump(res[:40], open(os.path.join(TMP, 'probe_rank.json'), 'w'), indent=1)
    return res


def gibs_tile(layer, date, bbox, w, h, path):
    x0, y0, x1, y1 = bbox
    u = ('https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0'
         f'&LAYERS={layer}&CRS=EPSG:3857&BBOX={x0},{y0},{x1},{y1}&WIDTH={w}&HEIGHT={h}&FORMAT=image/png&TIME={date}')
    if not curl(u, path):
        raise RuntimeError(u)


def pushpull(img, mask):
    """fill pixels where mask is False with smoothly extended colour from the known pixels
    (normalised convolution at 1/16 scale, widened until every hole is reached, then bilinear upsampling)"""
    H, W = mask.shape
    m = Image.fromarray((mask * 255).astype(np.uint8)).resize((max(W // 16, 8), max(H // 16, 8)), Image.BOX)
    c = Image.fromarray((img * mask[..., None]).astype(np.uint8)).resize(m.size, Image.BOX)
    mw = np.asarray(m, np.float32) / 255
    cw = np.asarray(c, np.float32)
    col = cw / np.maximum(mw, 1e-6)[..., None]
    filled = mw > 0.5
    r = 2
    while not filled.all() and r < 4096:
        bw = np.asarray(Image.fromarray((mw * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r)), np.float32) / 255
        bc = np.stack([np.asarray(Image.fromarray(np.clip(cw[..., k], 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r)), np.float32) for k in range(3)], -1)
        ok = (bw > 0.02) & ~filled
        col[ok] = bc[ok] / bw[ok][..., None]
        filled |= ok
        r *= 2
    big = np.asarray(Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR))
    soft = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)), np.float32)[..., None] / 255
    out = img * soft * mask[..., None] + big * (1 - soft * mask[..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


def sat_mosaic(name, lonlat, mpp, picks, tile=2048):
    """mosaic in web mercator; pixels without data or with cloud in pick k are filled from pick k+1"""
    x0, y0 = merc(lonlat[0], lonlat[1]); x1, y1 = merc(lonlat[2], lonlat[3])
    W, H = int((x1 - x0) / mpp), int((y1 - y0) / mpp)
    nx, ny = math.ceil(W / tile), math.ceil(H / tile)
    W, H = nx * tile, ny * tile
    x1, y1 = x0 + W * mpp, y0 + H * mpp
    acc = np.zeros((H, W, 3), np.uint8); have = np.zeros((H, W), bool)
    used = []
    for p in picks:
        img = np.zeros((H, W, 4), np.uint8)
        for j in range(ny):
            for i in range(nx):
                bx0, bx1 = x0 + i * tile * mpp, x0 + (i + 1) * tile * mpp
                by1, by0 = y1 - j * tile * mpp, y1 - (j + 1) * tile * mpp
                f = os.path.join(TMP, f"{name}_{p['layer']}_{p['date']}_{i}_{j}.png")
                gibs_tile(LAYERS[p['layer']], p['date'], (bx0, by0, bx1, by1), tile, tile, f)
                img[j * tile:(j + 1) * tile, i * tile:(i + 1) * tile] = np.asarray(Image.open(f).convert('RGBA'))
        ok = img[..., 3] > 0
        if used:   # filler dates: skip bright (cloud) pixels
            ok &= img[..., :3].mean(-1) < 170
        fill = ok & ~have
        if fill.mean() > 0.0005 or not used:
            acc[fill] = img[..., :3][fill]; have |= fill
            used.append(f"{p['layer']} {p['date']}")
        print(name, p['layer'], p['date'], 'coverage now', round(float(have.mean()), 4), flush=True)
        if have.mean() > 0.999:
            break
    if not have.all():   # remaining holes (outside every swath): push-pull fill from the surrounding colours
        acc = pushpull(acc, have)
    lon0, lat0 = inv(x0, y0); lon1, lat1 = inv(x1, y1)
    meta = dict(w=W, h=H, lon0=lon0, lon1=lon1, lat0=lat0, lat1=lat1, dates=used)
    json.dump(meta, open(os.path.join(M, name + '.json'), 'w'), indent=1)
    return Image.fromarray(acc), meta


# ---------------------------------------------------------------- xyz mosaics (terrain, water)
def xyz_mosaic(url, z, lonlat, kind):
    lon0, lat0, lon1, lat1 = lonlat
    x0, x1 = int(lon2x(lon0, z)), int(lon2x(lon1, z))
    y0, y1 = int(lat2y(lat1, z)), int(lat2y(lat0, z))
    d = os.path.join(TMP, f'{kind}{z}'); os.makedirs(d, exist_ok=True)
    jobs = [(tx, ty) for ty in range(y0, y1 + 1) for tx in range(x0, x1 + 1)]

    def get(j):
        tx, ty = j
        p = os.path.join(d, f'{tx}_{ty}.png')
        return p if curl(url.format(z=z, x=tx, y=ty), p, tries=4) else None
    with cf.ThreadPoolExecutor(6) as ex:
        paths = list(ex.map(get, jobs))
    W, H = (x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256
    meta = dict(z=z, x0=x0, y0=y0, w=W, h=H)
    if kind == 'dem':
        arr = np.zeros((H, W), np.float32)
        for (tx, ty), p in zip(jobs, paths):
            if p is None:
                raise RuntimeError(f'terrain tile {z}/{tx}/{ty} failed')
            a = np.asarray(Image.open(p).convert('RGB'), np.float32)
            arr[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        return np.clip(arr, -50, 6000), meta
    arr = np.zeros((H, W), np.float32)
    for (tx, ty), p in zip(jobs, paths):
        if p is None:       # JRC has no tile where there is no water at all
            continue
        a = np.asarray(Image.open(p).convert('RGBA'), np.float32)
        # occurrence ramp runs red (rarely water) → blue (always water); keep "water most of the time"
        w = (a[..., 3] > 0) & (a[..., 2] > a[..., 0])
        arr[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = w
    return arr, meta


def sample_xyz(arr, meta, lon, lat):
    z = meta['z']
    x = ((lon + 180) / 360 * 2 ** z - meta['x0']) * 256
    r = np.radians(lat)
    y = ((1 - np.log(np.tan(r) + 1 / np.cos(r)) / math.pi) / 2 * 2 ** z - meta['y0']) * 256
    x0 = np.clip(np.floor(x).astype(int), 0, arr.shape[1] - 2); y0 = np.clip(np.floor(y).astype(int), 0, arr.shape[0] - 2)
    fx, fy = np.clip(x - x0, 0, 1), np.clip(y - y0, 0, 1)
    a = arr[y0, x0] * (1 - fx) + arr[y0, x0 + 1] * fx
    b = arr[y0 + 1, x0] * (1 - fx) + arr[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def grid(meta, n):
    lons = np.linspace(meta['lon0'], meta['lon1'], n)
    my = np.linspace(lat2my(meta['lat1']), lat2my(meta['lat0']), n)
    lats = np.degrees(2 * np.arctan(np.exp(my)) - math.pi / 2)
    return np.meshgrid(lons, lats)


def main():
    core, wide = extents()
    print('core', core, 'wide', wide, flush=True)
    if os.path.exists(os.path.join(M, 'sat_hi.json')) and '--refetch' not in sys.argv:
        hi = json.load(open(os.path.join(M, 'sat_hi.json'))); lo = json.load(open(os.path.join(M, 'sat_lo.json')))
        sat_hi = Image.open(os.path.join(M, 'sat_hi.jpg')); sat_lo = Image.open(os.path.join(M, 'sat_lo.jpg'))
    else:
        rank = probe_dates(core)
        good = [r for r in rank if r['cov'] > 0.9][:6] or rank[:6]
        rest = [r for r in rank if r not in good][:6]
        print('best dates', good[:3], flush=True)
        sat_hi, hi = sat_mosaic('sat_hi', core, 24, good + rest)
        sat_lo, lo = sat_mosaic('sat_lo', wide, 96, good + rest, tile=1024)
        sat_hi.save(os.path.join(M, 'sat_hi.jpg'), quality=92); sat_lo.save(os.path.join(M, 'sat_lo.jpg'), quality=92)

    dem, dmeta = xyz_mosaic('https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png', 11,
                            [lo['lon0'], lo['lat0'], lo['lon1'], lo['lat1']], 'dem')
    wat, wmeta = xyz_mosaic('https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png', 11,
                            [hi['lon0'], hi['lat0'], hi['lon1'], hi['lat1']], 'water')
    # water mask on the sat_hi pixel grid (1536², mercator-linear like the texture)
    LON, LAT = grid(hi, 1536)
    w = sample_xyz(wat, wmeta, LON, LAT)
    w_img = Image.fromarray((np.clip(w, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(2))
    w_img.save(os.path.join(M, 'water.png'))
    water_s = np.asarray(w_img, np.float32) / 255

    for name, meta, n in (('core', hi, G), ('wide', lo, 256)):
        LON, LAT = grid(meta, n)
        h = sample_xyz(dem, dmeta, LON, LAT)
        if name == 'core':
            idx = np.clip(((np.arange(n) / (n - 1)) * 1535).astype(int), 0, 1535)
            wm = water_s[np.ix_(idx, idx)]
            h = h * (1 - wm)          # flat water surfaces
        h = np.maximum(h, 0)
        pad = np.pad(h, 2, mode='edge')
        med = np.median(np.stack([pad[2 + dy:2 + dy + n, 2 + dx:2 + dx + n] for dy in range(-2, 3) for dx in range(-2, 3)]), 0)
        spikes = ((h - med) > 150) & (name == 'core')
        h = np.where(spikes, med, h)
        h.astype(np.float32).tofile(os.path.join(M, f'{name}_h.bin'))
        print(name, n, 'height', float(h.min()), float(h.max()), 'spikes', int(spikes.sum()), flush=True)

    sat_hi.convert('RGB').resize((4096, 4096), Image.LANCZOS).save(os.path.join(M, 'sat_hi_4k.jpg'), quality=90)
    sat_lo.convert('RGB').resize((2048, 2048), Image.LANCZOS).save(os.path.join(M, 'sat_lo_2k.jpg'), quality=90)
    json.dump(dict(core=dict(n=G, **{k: hi[k] for k in ('lon0', 'lon1', 'lat0', 'lat1')}),
                   wide=dict(n=256, **{k: lo[k] for k in ('lon0', 'lon1', 'lat0', 'lat1')})),
              open(os.path.join(M, 'grid.json'), 'w'), indent=1)

    c = json.load(open(os.path.join(CITY, 'city.json')))
    c.setdefault('map', {})
    c['map'].update(core=core, wide=wide, satellite='NASA GIBS HLS ' + ' / '.join(dict.fromkeys(hi['dates'] + lo.get('dates', []))),
                    terrain='AWS Terrain Tiles (Terrarium z11)', water='EC JRC/Google Global Surface Water 2021 (occurrence)')
    c['map'].setdefault('exaggeration', 2.6)
    if not c.get('mapCredit'):
        c['mapCredit'] = '底图：NASA GIBS / HLS（含修改后的 Copernicus Sentinel-2 数据）· 地形：AWS Terrain Tiles · 水体：EC JRC/Google'
        if c.get('river'):
            c['mapCredit'] += ' · 河道：© OpenStreetMap'
    json.dump(c, open(os.path.join(CITY, 'city.json'), 'w'), ensure_ascii=False, indent=1)
    print('map ok', hi['dates'])


if __name__ == '__main__':
    main()
