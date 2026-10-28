"""Step 1b helper — save citable texts into <cityDir>/research/ (one file per page, URL in the header).

  python3 -I wiki.py wp  <researchDir> <zh.wikipedia title> [...]   plain-text extract + coordinates
  python3 -I wiki.py ws  <researchDir> <zh.wikisource title> [...]  raw wikitext of a primary text (正史/条约/公报)
  python3 -I wiki.py bk  <researchDir> <词条> [...]                  baike.com (快懂百科) entry, tags stripped
  python3 -I wiki.py url <researchDir> <name> <url>                 any web page, tags stripped (government sites, news)
Files that fail to download are reported as FAILED — such sources may not be marked as opened.
"""
import json, os, re, subprocess, sys, time, urllib.parse

UA = 'CityNianlunBot/1.0 (documentary research)'


def curl(url, ua=UA):
    for a in range(5):
        try:
            out = subprocess.check_output(['curl', '-s', '-f', '-L', '-m', '60', '-A', ua, url])
            if out:
                return out
        except subprocess.CalledProcessError:
            pass
        time.sleep(2 * (a + 1))
    return None


def safe(t):
    return re.sub(r'[\\/:*?"<>|\s]+', '_', t)[:80]


mode, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
if mode == 'wp':
    for t in sys.argv[3:]:
        raw = curl('https://zh.wikipedia.org/w/api.php?action=query&prop=extracts|coordinates&explaintext=1&redirects=1'
                   '&format=json&variant=zh-cn&titles=' + urllib.parse.quote(t))
        p = next(iter(json.loads(raw)['query']['pages'].values())) if raw else {}
        if not p.get('extract'):
            print('FAILED wp', t); continue
        url = 'https://zh.wikipedia.org/wiki/' + urllib.parse.quote(p['title'])
        open(os.path.join(out, 'wp_' + safe(t) + '.txt'), 'w').write(f"# zh.wikipedia: {p['title']}\n# {url}\n# coords {p.get('coordinates')}\n\n{p['extract']}")
        print('ok wp', t, '->', p['title'], len(p['extract']), p.get('coordinates')); time.sleep(1)
elif mode == 'ws':
    for t in sys.argv[3:]:
        raw = curl('https://zh.wikisource.org/w/index.php?action=raw&title=' + urllib.parse.quote(t))
        txt = raw.decode('utf8', 'ignore') if raw else ''
        m = re.match(r'#REDIRECT\s*\[\[([^\]]+)\]\]', txt, re.I)
        if m:
            t2 = m.group(1); raw = curl('https://zh.wikisource.org/w/index.php?action=raw&title=' + urllib.parse.quote(t2))
            txt = raw.decode('utf8', 'ignore') if raw else ''; t = t2
        if not txt:
            print('FAILED ws', t); continue
        url = 'https://zh.wikisource.org/wiki/' + urllib.parse.quote(t)
        open(os.path.join(out, 'ws_' + safe(t) + '.txt'), 'w').write(f'# zh.wikisource: {t}\n# {url}\n\n{txt}')
        print('ok ws', t, len(txt)); time.sleep(1)
else:
    if mode == 'bk':
        jobs = [('bk_' + safe(t), 'https://www.baike.com/wiki/' + urllib.parse.quote(t)) for t in sys.argv[3:]]
    elif mode == 'url':
        jobs = [('web_' + safe(sys.argv[3]), sys.argv[4])]
    else:
        sys.exit(__doc__)
    for name, url in jobs:
        raw = curl(url, 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36')
        s = raw.decode('utf8', 'ignore') if raw else ''
        s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', '', s)
        s = re.sub(r'\s*\n\s*', '\n', re.sub(r'<[^>]+>', '\n', s)).strip()
        if len(s) < 150:
            print('FAILED', mode, url, '(page missing or empty)'); continue
        s = re.sub(r'\n(?=[^\n]{0,12}\n)', '', s)   # re-join words split by inline tags
        open(os.path.join(out, name + '.txt'), 'w').write(f'# {url}\n\n{s}')
        print('ok', mode, name, len(s)); time.sleep(1)

# keep research/INDEX.md in sync (file → source URL)
with open(os.path.join(out, 'INDEX.md'), 'w') as f:
    f.write('# research/ 文件索引（文件第二行是来源网址）\n\n')
    for fn in sorted(os.listdir(out)):
        if fn.endswith('.txt'):
            head = open(os.path.join(out, fn), errors='ignore').read(400).splitlines()
            url = next((h[2:] for h in head if h.startswith('# http')), '')
            f.write(f'- {fn}  {url}\n')
