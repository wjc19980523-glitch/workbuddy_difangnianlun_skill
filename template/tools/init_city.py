"""Step 1a — start a city from its name only.

usage: python3 -I template/tools/init_city.py <城市名> <examplesDir>

  * geocodes the city (OpenStreetMap Nominatim) → centre, admin bounding box, English name → slug
  * writes <examplesDir>/<slug>/city.json (skeleton; title/subtitle/question are filled in step 1b)
  * downloads research material into <slug>/research/:
      wp_city.txt      zh.wikipedia plain-text extract of the city article
      wp_history.txt   zh.wikipedia "<城市名>历史" article if it exists
      bk_*.txt         baike.com (快懂百科) intro paragraphs — a second site for the same facts
      events.md        every dated sentence of the two Wikipedia texts, numbered (node candidates)
      INDEX.md         file → source URL
  * prints the slug directory
"""
import json, os, re, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

UA = 'CityNianlunBot/1.0 (documentary research)'
name = sys.argv[1].strip()
root = os.path.abspath(sys.argv[2])
short = re.sub(r'(市|县|区)$', '', name)


def get(url):
    for _ in range(4):
        try:
            return json.loads(subprocess.check_output(['curl', '-s', '-m', '60', '-A', UA, url]))
        except Exception:
            pass
    raise RuntimeError(url)


# ---------------------------------------------------------------- geocode
q = urllib.parse.quote(short + '市')
res = get(f'https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=5&namedetails=1&accept-language=zh')
res = [r for r in res if r.get('class') in ('boundary', 'place')] or res
if not res:
    res = get(f'https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(short)}&format=json&limit=5&namedetails=1&accept-language=zh')
g = res[0]
en = (g.get('namedetails') or {}).get('name:en') or (g.get('namedetails') or {}).get('name:zh-Latn-pinyin') or short
slug = re.sub(r'[^a-z]', '', re.sub(r'\b(city|prefecture|municipality)\b', '', en.lower()))
bb = [float(x) for x in g['boundingbox']]          # lat0, lat1, lon0, lon1
out = os.path.join(root, slug)
os.makedirs(os.path.join(out, 'research'), exist_ok=True)
os.makedirs(os.path.join(out, 'assets', 'img'), exist_ok=True)

# Wikidata coordinate of the city (usually the historic core) is a better camera centre than the admin centroid
center = {'lon': round(float(g['lon']), 4), 'lat': round(float(g['lat']), 4)}
try:
    wd = get('https://zh.wikipedia.org/w/api.php?action=query&prop=pageprops|coordinates&redirects=1&format=json&titles=' + urllib.parse.quote(short + '市'))
    pg = next(iter(wd['query']['pages'].values()))
    if pg.get('coordinates'):
        center = {'lon': round(pg['coordinates'][0]['lon'], 4), 'lat': round(pg['coordinates'][0]['lat'], 4)}
except Exception:
    pass

cp = os.path.join(out, 'city.json')
city = json.load(open(cp)) if os.path.exists(cp) else {}
city.update({k: v for k, v in dict(
    slug=slug, name=short, title=f'{short}的年轮',
    subtitle=city.get('subtitle') or 'TODO 副标题（如：长江之畔 · 两千五百年 · 十四道年轮）',
    center=center, adminBBox=[bb[2], bb[0], bb[3], bb[1]],
    outro=city.get('outro') or {'question': f'TODO 结尾唯一的问题（如：{short}这十四道年轮里，\n你最想走进哪一年？）'},
    ambient=city.get('ambient', []),
).items()})
json.dump(city, open(cp, 'w'), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- research material
R = os.path.join(out, 'research')


def extract(title):
    d = get('https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&redirects=1&format=json&variant=zh-cn&titles='
            + urllib.parse.quote(title))
    pg = next(iter(d['query']['pages'].values()))
    return pg.get('title'), pg.get('extract') or ''


for fn, title in (('wp_city.txt', short + '市'), ('wp_history.txt', short + '历史')):
    t, txt = extract(title)
    if txt:
        open(os.path.join(R, fn), 'w').write(f'# zh.wikipedia: {t}\n# https://zh.wikipedia.org/wiki/{urllib.parse.quote(t)}\n\n{txt}')
# second site for the same facts (baike.com intro paragraphs)
subprocess.call([sys.executable, '-I', os.path.join(HERE, 'wiki.py'), 'bk', R, short, short + '市', short + '历史'])

# events.md: every sentence with a year, numbered, so the model can choose 10–15 nodes from real text
ev, seen = [], set()
YEAR = re.compile(r'(公元前|前)?\d{2,4}年|距今|万年前|世纪')
for fn in ('wp_history.txt', 'wp_city.txt'):
    p = os.path.join(R, fn)
    if not os.path.exists(p):
        continue
    body = open(p).read().split('\n', 3)[-1]
    sec = ''
    for line in body.splitlines():
        if line.startswith('=='):
            sec = line.strip('= ').strip(); continue
        if sec in ('参考资料', '参考文献', '外部链接', '参见', '注释', '友好城市', '交通', '体育', '经济', '人口', '气候'):
            continue
        for sent in re.split(r'(?<=[。！；])', line):
            sent = sent.strip()
            if 12 <= len(sent) <= 160 and YEAR.search(sent) and sent not in seen:
                seen.add(sent); ev.append((fn, sec, sent))
with open(os.path.join(R, 'events.md'), 'w') as f:
    f.write(f'# {short} · 带年份的史实句子（摘自 research/ 下的维基百科文件，供挑选节点）\n\n')
    f.write('挑节点后，引文要从对应文件原样复制；再用 wiki.py 下载该事件自己的维基条目/快懂百科/维基文库原文，凑齐第二个网站。\n\n')
    for k, (fn, sec, sent) in enumerate(ev[:400], 1):
        f.write(f'{k}. [{fn} · {sec}] {sent}\n')

with open(os.path.join(R, 'INDEX.md'), 'w') as f:
    f.write('# research/ 文件索引（文件第二行是来源网址）\n\n')
    for fn in sorted(os.listdir(R)):
        if fn.endswith('.txt'):
            head = open(os.path.join(R, fn)).read(400).splitlines()
            url = next((h[2:] for h in head if h.startswith('# http')), '')
            f.write(f'- {fn}  {url}\n')

print(out)
