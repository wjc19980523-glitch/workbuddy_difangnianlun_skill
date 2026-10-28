"""Write sources.md, image-sources.md and REVIEW.md from nodes.json + build/check.json + assets/img/meta.json.
Human review notes go in <cityDir>/REVIEW.notes.md; they are appended to REVIEW.md on every run.

usage: python3 -I template/tools/make_docs.py <cityDir>
(Skipped for city.json "docs": "manual", e.g. examples/huzhou whose lists were written by hand.)
"""
import datetime, json, os, sys, urllib.parse

CITY = os.path.abspath(sys.argv[1])
city = json.load(open(os.path.join(CITY, 'city.json')))
if city.get('docs') == 'manual':
    print('docs: manual, skipped'); sys.exit(0)
nodes = json.load(open(os.path.join(CITY, 'nodes.json')))['nodes']
chk = json.load(open(os.path.join(CITY, 'build', 'check.json')))
rep = {r['id']: r for r in chk['nodes']}
mp = os.path.join(CITY, 'assets', 'img', 'meta.json')
meta = json.load(open(mp)) if os.path.exists(mp) else {}
rp = os.path.join(CITY, 'assets', 'img', 'rejected.json')
rejected = json.load(open(rp)) if os.path.exists(rp) else []
today = datetime.date.today().isoformat()
name = city['name']
cell = lambda s: str(s).replace('|', '／').replace('\n', ' ')

# ---------------------------------------------------------------- sources.md
L = [f'# 《{city["title"]}》史实出处清单', '',
     f'自动生成于 {today}（template/tools/make_docs.py）。共 {len(nodes)} 个节点。',
     '每条事实下列出引文与来源；“已核”= 引文已在脚本下载的原文里逐字找到。',
     '**状态规则**：只有来自 ≥2 个不同网站、且逐字可查的原文支持的事实才标“✅ 已核”；单一来源、来源打不开、引文对不上的一律标“⚠️ 待核对”，发布前须人工核对或删除。', '',
     '## 片头 / 结尾', '', '| 画面文字 | 说明 |', '|---|---|',
     f'| {cell(city["title"])} / {cell(city.get("subtitle", ""))} | 标题与副标题，副标题中的数量/年代概括须与下列节点一致 |',
     f'| {cell(city["outro"]["question"])} | 结尾唯一的提问，不含事实陈述 |', '']
for i, n in enumerate(nodes, 1):
    r = rep.get(n['id'], {})
    st = '✅ 已核' if r.get('status') == 'ok' else '⚠️ 待核对'
    L += [f'## {i:02d} · {n["year"]} · {n["title"]}（{n["place"]}）— {st}', '',
          f'画面：{" ".join(n["body"])}　｜　出处行：{n["src"]}　｜　坐标 {n.get("lon")}, {n.get("lat")}（{n.get("geoSource", "")}）', '',
          '| 事实 | 状态 | 引文与来源 |', '|---|---|---|']
    for f in r.get('facts', []):
        srcs = '<br>'.join(f"{'✓' if s['ok'] else '✗'} “{cell(s['quote'][:80])}” — <{s['url'] or s['file']}>" + ('' if s['ok'] else f"（{s.get('why', '')}）")
                           for s in f['sources']) or '（无引文）'
        L.append(f"| {cell(f['text'])} | {'✅' if f['status'] == 'ok' else '⚠️ ' + f['why']} | {srcs} |")
    if r.get('missingNumbers'):
        L.append(f"| 画面数字 {'、'.join(r['missingNumbers'])} | ⚠️ 未在已核引文中出现 | 须人工核对年代换算 |")
    L.append('')
L += ['## 地图', '',
      f"- 卫星底图：{city.get('map', {}).get('satellite', '')}（NASA EOSDIS 数据，无使用限制，含修改后的 Copernicus Sentinel-2 数据）",
      f"- 地形：{city.get('map', {}).get('terrain', 'AWS Terrain Tiles')}；高程放大 {city.get('map', {}).get('exaggeration', 2.6)} 倍",
      f"- 水体：{city.get('map', {}).get('water', '')}",
      '- 节点坐标由 template/tools/geocode.py 从 zh.wikipedia 条目坐标或 OpenStreetMap Nominatim 自动查得，见各节点“坐标”。', '']
open(os.path.join(CITY, 'sources.md'), 'w').write('\n'.join(L))

# ---------------------------------------------------------------- image-sources.md
I = [f'# 《{city["title"]}》图像素材来源与授权清单', '',
     f'自动生成于 {today}。所有图片由 template/tools/fetch_images.py 从 Wikimedia Commons 下载，下载前逐张检查授权（只收公有领域 / CC0 / CC BY / CC BY-SA）并排除 Commons 标注为 AI 生成的文件；没有任何 AI 生成图。',
     '授权信息取自 Commons 文件页的结构化元数据。CC BY / BY-SA 作品已在画面图注下署名作者与协议。本地文件统一转为 JPEG、长边 ≤ 1800 px。', '',
     '| 节点 | 本地文件 | 画面图注 | Commons 文件 | 作者 | 授权 | 状态 |', '|---|---|---|---|---|---|---|']
txtcard = []
for i, n in enumerate(nodes, 1):
    ims = n.get('images') or []
    if not ims:
        txtcard.append(f'| {i:02d} {cell(n["place"])}（{cell(n["year"])}） | 没有选到授权合规且切题的图片 |')
    for im in ims:
        x = meta.get(im.get('id'), {})
        url = 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(x.get('title', '').replace(' ', '_'), safe=':') if x.get('title') and not x.get('user_supplied') else x.get('page', '')
        st = '⚠️ 待核对（用户自备，授权未确认）' if x.get('review') else ('⚠️ 待核对（未下载）' if not x else '✅ 授权已查')
        I.append(f"| {i:02d} {cell(n['place'])} | `assets/img/{im.get('id')}.jpg` | {cell(im.get('caption', ''))} | <{url}> | {cell((x.get('artist') or '佚名')[:50])} | {cell(x.get('license', ''))} | {st} |")
I += ['', '**图注须人工过目**：图注由执行模型依据 Commons 文件说明撰写，发布前请对照来源链接确认图注与图片内容一致。', '',
      '## 改用文字卡的节点', '', '| 节点 | 原因 |', '|---|---|'] + (txtcard or ['| — | — |'])
I += ['', '## 被脚本拒收的图片', '', '| 节点 | 文件 | 原因 |', '|---|---|---|'] + \
     ([f"| {r['node']} | {cell(r['file'])} | {cell(r['why'])} |" for r in rejected] or ['| — | — | — |'])
I += ['', '## 地图底图与数据（非历史素材）', '', '| 用途 | 来源 | 授权 / 使用条件 |', '|---|---|---|',
      f"| 卫星影像 | {city.get('map', {}).get('satellite', '')} <https://gibs.earthdata.nasa.gov/> | NASA EOSDIS 数据无使用限制，注明出处；HLS 含修改后的 Copernicus Sentinel-2 数据 |",
      '| 地形高程 | AWS Terrain Tiles（Terrarium z11）<https://registry.opendata.aws/terrain-tiles/> | 开放数据，注明出处 |',
      '| 水体范围 | EC JRC/Google Global Surface Water 2021 <https://global-surface-water.appspot.com/> | 免费使用，注明出处（Source: EC JRC/Google） |', '']
open(os.path.join(CITY, 'image-sources.md'), 'w').write('\n'.join(I))

# ---------------------------------------------------------------- REVIEW.md
V = [f'# {name} · 待人工核对清单', '', f'生成于 {today}。以下条目已上片但未达到“两个不同网站逐字可查”的标准，发布前须核对或删除。', '']
V += [f'- {r}' for r in chk['review']] or ['- 无']
V += ['', '## 图片', ''] + [f"- {r['node']} {r['file']}：{r['why']}（已拒收）" for r in rejected] + \
     ['- 所有图注：请对照 image-sources.md 的 Commons 链接确认图注与图片一致。']
notes = os.path.join(CITY, 'REVIEW.notes.md')      # hand-written review notes survive regeneration
if os.path.exists(notes):
    V += ['', open(notes).read().strip()]
open(os.path.join(CITY, 'REVIEW.md'), 'w').write('\n'.join(V) + '\n')
print('docs ok: sources.md, image-sources.md, REVIEW.md;', len(chk['review']), 'review items')
