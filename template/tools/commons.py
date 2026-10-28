"""Wikimedia Commons helper.

  python3 -I commons.py search "<query>" [limit]   list files with license / author
  python3 -I commons.py info "File:..."            full metadata as JSON
  python3 -I commons.py get "File:..." <out_dir> [width]   download (thumb if width)
"""
import json, os, re, subprocess, sys, time, urllib.parse

API = 'https://commons.wikimedia.org/w/api.php'
UA = 'CityNianlunBot/1.0 (documentary research)'


def call(params):
    url = API + '?' + urllib.parse.urlencode(dict(params, format='json'))
    for attempt in range(6):
        try:
            out = subprocess.check_output(['curl', '-s', '--noproxy', '*', '-m', '60', '-A', UA, url])
            r = json.loads(out)
            if 'error' not in r:
                return r
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    raise RuntimeError('commons api failed')


def strip(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html or '')).strip()


def info(titles, width=None, page=None):
    p = dict(action='query', titles='|'.join(titles), prop='imageinfo',
             iiprop='url|size|extmetadata|mime')
    if width:
        p['iiurlwidth'] = width
    if page:
        p['iiurlparam'] = f'page{page}-{width or 1600}px'
    pages = call(p)['query']['pages']
    res = []
    for pg in pages.values():
        ii = (pg.get('imageinfo') or [{}])[0]
        em = ii.get('extmetadata', {})
        g = lambda k: strip(em.get(k, {}).get('value', ''))
        res.append(dict(title=pg.get('title'), url=ii.get('url'), thumb=ii.get('thumburl'),
                        page=ii.get('descriptionurl'), w=ii.get('width'), h=ii.get('height'),
                        mime=ii.get('mime'), license=g('LicenseShortName'), license_url=g('LicenseUrl'),
                        artist=g('Artist'), credit=g('Credit')[:200], date=g('DateTimeOriginal')[:80],
                        desc=g('ImageDescription')[:300]))
    return res


def search(q, limit=12):
    r = call(dict(action='query', list='search', srsearch=q, srnamespace=6, srlimit=limit))
    titles = [x['title'] for x in r['query']['search']]
    return info(titles) if titles else []


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'search':
        for x in search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12):
            print(f"{x['title']} | {x['w']}x{x['h']} | {x['license']} | {x['artist'][:50]} | {x['date'][:30]} | {x['desc'][:110]}")
    elif cmd == 'info':
        print(json.dumps(info([sys.argv[2]]), ensure_ascii=False, indent=1))
    elif cmd == 'get':
        width = int(sys.argv[4]) if len(sys.argv) > 4 else None
        page = int(sys.argv[5]) if len(sys.argv) > 5 else None
        x = info([sys.argv[2]], width, page)[0]
        url = x['thumb'] if width and x.get('thumb') else x['url']
        os.makedirs(sys.argv[3], exist_ok=True)
        name = re.sub(r'[^\w.\-]+', '_', x['title'].split(':', 1)[1])
        if page:
            name += f'.p{page}.jpg'
        out = os.path.join(sys.argv[3], name)
        subprocess.check_call(['curl', '-s', '--noproxy', '*', '-m', '120', '-A', UA, '-o', out, url])
        x['local'] = out
        print(json.dumps(x, ensure_ascii=False))
