"""Pre-render gate: validates city.json + nodes.json and writes build/check.json.

usage: python3 -I template/tools/check.py <cityDir> [--layout] [--video <mp4>]

ERROR  = must be fixed before rendering (exit code 1); every message says which field to change.
待核对 = allowed on screen but listed for human review in sources.md / REVIEW.md:
         a fact counts as checked only with verbatim quotes from ≥ 2 different sites
         (zh/en.wikipedia = one site, zh.wikisource, baike.com, each government / news domain).
--layout  measures the typography in the real page (needs assets/map); wrapped lines are errors.
--video   ffprobe the result: 9:16, 120–180 s.
"""
import json, os, re, subprocess, sys, urllib.parse

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITY = os.path.abspath(sys.argv[1])
ARGS = sys.argv[2:]
city = json.load(open(os.path.join(CITY, 'city.json')))
data = json.load(open(os.path.join(CITY, 'nodes.json')))
nodes = data.get('nodes', [])
manual = city.get('docs') == 'manual'          # hand-written sources.md (examples/huzhou)
E, R, W = [], [], []                           # errors, review items, warnings

BANNED = ['下期', '继续测', '继续拆', '粉丝', '据本人称', '关注我', '点赞', '三连', '@', '抖音号', '视频号', '小红书号', '公众号', '私信', '进群']
LIM = dict(place=8, where=14, year=8, era=16, title=12, body=21, src=40, caption=30, big=4, line=12)


def width(s):   # CJK = 1, ASCII = 0.55
    return sum(0.55 if ord(c) < 128 else 1 for c in s)


def need(obj, k, where, typ=str):
    v = obj.get(k)
    if v is None or (typ is str and (not isinstance(v, str) or not v.strip())):
        E.append(f'{where}：缺少字段 "{k}"'); return None
    if isinstance(v, str) and 'TODO' in v:
        E.append(f'{where}："{k}" 还是 TODO 占位，请填写'); return None
    return v


def norm(s):
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'-\{|\}-', '', s)
    return re.sub(r'[^\w]|_', '', s)


def site(url):
    h = urllib.parse.urlparse(url).hostname or ''
    h = re.sub(r'^(www|m|zh|en)\.', '', h)
    if h.endswith('wikipedia.org'):
        return 'wikipedia'
    return '.'.join(h.split('.')[-3:]) if h.endswith(('.gov.cn', '.com.cn', '.org.cn', '.edu.cn')) else '.'.join(h.split('.')[-2:])


# ---------------------------------------------------------------- city.json
for k in ('slug', 'name', 'title', 'subtitle'):
    need(city, k, 'city.json')
c = city.get('center') or {}
if not isinstance(c.get('lon'), (int, float)) or not isinstance(c.get('lat'), (int, float)):
    E.append('city.json：center 缺少 lon/lat（由 init_city.py 自动写入，不要手改）')
q = (city.get('outro') or {}).get('question', '')
if not q or 'TODO' in q:
    E.append('city.json：outro.question 必须填写结尾唯一的提问')
else:
    if len(re.findall(r'[？?]', q)) != 1 or not q.rstrip().endswith(('？', '?')):
        E.append('city.json：outro.question 必须恰好包含一个问号，并以问号结尾')
    if any(width(l) > 13 for l in q.split('\n')):
        E.append('city.json：outro.question 每行不超过 13 个字（用 \\n 换行，最多 2 行）')
    if q.count('\n') > 1:
        E.append('city.json：outro.question 最多 2 行')
if width(city.get('title', '')) > 7:
    E.append('city.json：title 不超过 7 个字（如“南京的年轮”）')
if width(city.get('subtitle', '')) > 20:
    E.append('city.json：subtitle 不超过 20 个字')

# ---------------------------------------------------------------- nodes
if not 10 <= len(nodes) <= 15:
    E.append(f'nodes.json：节点数必须是 10–15 个，现在是 {len(nodes)} 个')
ids = [n.get('id') for n in nodes]
if len(set(ids)) != len(ids):
    E.append('nodes.json：id 有重复')
bb = city.get('adminBBox')
grid = None
gp = os.path.join(CITY, 'assets', 'map', 'grid.json')
if os.path.exists(gp):
    grid = json.load(open(gp))['core']
cand = {}
cp = os.path.join(CITY, 'research', 'image_candidates.json')
if os.path.exists(cp):
    cand = {x['code']: x for v in json.load(open(cp)).values() for x in v['items']}

texts = [city.get('title', ''), city.get('subtitle', ''), q]
report = []
for i, n in enumerate(nodes):
    at = f"节点 {i + 1}（id={n.get('id')}）"
    for k in ('id', 'place', 'where', 'year', 'era', 'title', 'src'):
        v = need(n, k, at)
        if v and k in LIM and width(v) > LIM[k]:
            E.append(f'{at}："{k}" 太长（{v}），最多 {LIM[k]} 个字')
    body = n.get('body')
    if not isinstance(body, list) or not 1 <= len(body) <= 4:
        E.append(f'{at}："body" 必须是 1–4 行的数组')
        body = []
    for l in body:
        if width(l) > LIM['body']:
            E.append(f'{at}：body 这一行太长（{l}），每行最多 {LIM["body"]} 个字，请拆成两行')
    if n.get('year') and not re.search(r'\d|年|世纪|距今', n['year']):
        E.append(f'{at}："year" 必须含年份数字，如 "前472年" "1912年" "距今约60万年"')
    lon, lat = n.get('lon'), n.get('lat')
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        E.append(f'{at}：没有坐标——填 "geo"（地名/维基条目名）后运行 geocode.py，不要自己写经纬度')
    else:
        if bb and not (bb[0] - .2 <= lon <= bb[2] + .2 and bb[1] - .2 <= lat <= bb[3] + .2):
            E.append(f'{at}：坐标 {lon},{lat} 不在{city.get("name")}范围内，请改 "geo" 后重新 geocode')
        if grid and not (grid['lon0'] < lon < grid['lon1'] and grid['lat0'] < lat < grid['lat1']):
            E.append(f'{at}：坐标在地图范围外——请删除 assets/map 后重新运行（地图会按节点重新生成）')
    if 'cam' in n and not isinstance(n['cam'], dict):
        E.append(f'{at}："cam" 必须是对象或删除（默认自动运镜）')
    imgs = n.get('images') or []
    if len(imgs) > 2:
        E.append(f'{at}：最多 2 张图')
    for im in imgs:
        if im.get('pick') and cand and im['pick'] not in cand:
            E.append(f'{at}：图片编号 {im["pick"]} 不在 research/images.md 的候选里（只能从候选中挑）')
        if not im.get('pick') and not im.get('commons') and not im.get('local') and not manual:
            E.append(f'{at}：图片必须写 "pick"（候选编号）')
        if not need(im, 'caption', at + ' 的图片'):
            continue
        if width(im['caption']) > LIM['caption']:
            E.append(f'{at}：图注太长（{im["caption"]}），最多 {LIM["caption"]} 个字')
        texts.append(im['caption'])
        if '--layout' in ARGS or '--video' in ARGS:
            iid = im.get('id')
            if not iid or not os.path.exists(os.path.join(CITY, 'assets', 'img', iid + '.jpg')):
                E.append(f'{at}：图片文件不存在（先运行 fetch_images.py）')
    if n.get('card'):
        if width(n['card'].get('big', '')) > LIM['big']:
            E.append(f'{at}：card.big 最多 {LIM["big"]} 个字')
        for l in n['card'].get('lines', []):
            if width(l) > LIM['line']:
                E.append(f'{at}：card.lines 每行最多 {LIM["line"]} 个字')
            texts.append(l)
    texts += [str(n.get(k, '')) for k in ('place', 'where', 'year', 'era', 'title', 'src')] + list(body)

    # ------------------------------------------------------------ facts / quotes
    if manual:
        continue
    facts = n.get('facts')
    if not isinstance(facts, list) or not facts:
        E.append(f'{at}：缺少 "facts"——画面上每条事实都要写进 facts，并附原文引文'); continue
    node_rep = dict(id=n.get('id'), place=n.get('place'), year=n.get('year'), facts=[])
    verified_text = ''
    for j, f in enumerate(facts):
        fr = dict(text=f.get('text', ''), sources=[], status='待核对', why='')
        sites = set()
        for qd in f.get('quotes', []):
            fn = os.path.join(CITY, 'research', os.path.basename(qd.get('file', '')))
            src = dict(file=os.path.basename(qd.get('file', '')), quote=qd.get('quote', ''), url='', ok=False)
            if not os.path.exists(fn):
                src['why'] = '文件不存在（必须是 research/ 里脚本下载的文件）'
            else:
                txt = open(fn, encoding='utf8', errors='ignore').read()
                m = re.search(r'^# (?:zh\.\w+: [^\n]*\n# )?(https?://\S+)', txt, re.M)
                src['url'] = m.group(1) if m else ''
                nq = norm(src['quote'])
                if len(nq) < 6:
                    src['why'] = '引文太短（至少 6 个字）'
                elif nq not in norm(txt):
                    src['why'] = '引文在文件里找不到（必须原样复制原文，繁体就照抄繁体）'
                else:
                    src['ok'] = True; sites.add(site(src['url'])); verified_text += txt[:0] + src['quote']
            fr['sources'].append(src)
        if len(sites) >= 2:
            fr['status'] = 'ok'
        else:
            fr['why'] = '只有一个网站的原文可核' if len(sites) == 1 else '没有可核的原文引文'
        node_rep['facts'].append(fr)
    # numbers shown on screen must appear in the node's verified quotes
    shown = ' '.join([n.get('year', ''), n.get('era', '')] + list(body))
    vt = norm(verified_text)
    missing = [d for d in re.findall(r'\d{2,}', shown) if d not in vt]
    node_rep['missingNumbers'] = missing
    node_rep['status'] = 'ok' if all(f['status'] == 'ok' for f in node_rep['facts']) and not missing else '待核对'
    if node_rep['status'] != 'ok':
        why = [f"「{f['text'][:24]}」{f['why']}" for f in node_rep['facts'] if f['status'] != 'ok']
        if missing:
            why.append('画面数字 ' + '、'.join(missing) + ' 未在已核引文中出现')
        R.append(f"{at} {n.get('place')} {n.get('year')}：" + '；'.join(why))
    report.append(node_rep)

for t in texts:
    for b in BANNED:
        if b in t:
            E.append(f'画面文字含禁用词“{b}”：{t}')
for n in nodes:
    for k in ('title', 'era', 'where'):
        if re.search(r'[？?]', str(n.get(k, ''))) or any(re.search(r'[？?]', l) for l in n.get('body', [])):
            E.append(f'节点 {n.get("id")}：节点文字里不能有问号（全片只在结尾提一个问题）'); break

# ---------------------------------------------------------------- layout in the real page
if '--layout' in ARGS and not E:
    env = dict(os.environ, NL_SCALE='0.5', NL_SAMPLES='0')
    out = subprocess.run(['node', os.path.join(T, 'src', 'render.mjs'), CITY, 'layout'], capture_output=True, text=True, env=env)
    lines = [l for l in out.stdout.splitlines() if l.startswith('[')]
    if not lines:
        E.append('页面加载失败：' + (out.stderr.strip().splitlines() or ['?'])[-1][:300])
    else:
        for x in json.loads(lines[-1]):
            at = f"节点 {x['i'] + 1}（id={nodes[x['i']].get('id')}）"
            if x['year'] > 1: E.append(f'{at}：year 一行放不下，请缩短')
            if x['title'] > 1: E.append(f'{at}：title 一行放不下，请缩短')
            for k, b in enumerate(x['body']):
                if b > 1: E.append(f'{at}：body 第 {k + 1} 行放不下，请拆短')
            if x['src'] > 2: E.append(f'{at}：src 超过两行，请缩短')
            if x['footTop'] < 1290: E.append(f'{at}：文字区太高会压住图片，请减少 body 行数')
            if x.get('cardBig', 1) > 1: E.append(f'{at}：文字卡 big 一行放不下')
            if x.get('cap', 1) > 1: E.append(f'{at}：图注一行放不下，请缩短')
    info = subprocess.run(['node', os.path.join(T, 'src', 'render.mjs'), CITY, 'info'], capture_output=True, text=True, env=env)
    tl = [l for l in info.stdout.splitlines() if l.startswith('{')]
    if tl:
        tot = json.loads(tl[-1])['total']
        if not 120 <= tot <= 180:
            E.append(f'总时长 {tot:.1f} 秒不在 120–180 秒内（节点 dur 请删除，让模板自动分配）')

if '--video' in ARGS:
    v = ARGS[ARGS.index('--video') + 1]
    p = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height,codec_type',
                                            '-show_entries', 'format=duration', '-of', 'json', v]))
    vs = [s for s in p['streams'] if s['codec_type'] == 'video'][0]
    d = float(p['format']['duration'])
    print(f'VIDEO {vs["width"]}x{vs["height"]} {d:.1f}s audio={"yes" if any(s["codec_type"] == "audio" for s in p["streams"]) else "no"}')
    if abs(vs['width'] / vs['height'] - 9 / 16) > 0.01: E.append('成片不是 9:16')
    if not 120 <= d <= 180: E.append(f'成片时长 {d:.1f}s 不在 120–180 秒')

os.makedirs(os.path.join(CITY, 'build'), exist_ok=True)
json.dump(dict(errors=E, review=R, nodes=report), open(os.path.join(CITY, 'build', 'check.json'), 'w'), ensure_ascii=False, indent=1)
for r in R:
    print('待核对', r)
for e in E:
    print('ERROR', e)
print(f'CHECK {"FAILED" if E else "OK"}: {len(E)} 个错误，{len(R)} 个待核对节点')
sys.exit(1 if E else 0)
