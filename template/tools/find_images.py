"""List licence-checked Wikimedia Commons candidates for every node — the model only picks a number.

usage: python3 -I template/tools/find_images.py <cityDir>

For every node with "imageQuery": "词1 | word 2 | ..." (Chinese and English keywords, separated by |):
  * searches Commons (file namespace), keeps only bitmap images (jpg/png/tif) ≥ 700 px,
    licence = public domain / CC0 / CC BY / CC BY-SA, not categorised/described as AI-generated
  * writes research/images.md (human/model readable) and research/image_candidates.json
Each candidate has a code like  n03-2 . To use it, the node gets
    "images": [{"pick": "n03-2", "caption": "图注（据候选说明写，不要编）"}]
fetch_images.py resolves the code to the Commons file. Codes not in the list are rejected by check.py,
so the model cannot invent files. A node with no suitable candidate keeps "images": [] → text card.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import commons  # noqa: E402
from fetch_images import licence_ok, AI  # noqa: E402

CITY = os.path.abspath(sys.argv[1])
data = json.load(open(os.path.join(CITY, 'nodes.json')))
cp = os.path.join(CITY, 'research', 'image_candidates.json')
cand = json.load(open(cp)) if os.path.exists(cp) else {}
OKMIME = ('image/jpeg', 'image/png', 'image/tiff')

md = ['# 图片候选（Wikimedia Commons，已按授权过滤）', '',
      '用法：在 nodes.json 对应节点写 "images": [{"pick": "编号", "caption": "图注"}]，最多 2 张。',
      '只能用下面列出的编号；图注只能根据“说明”一栏写，看不懂就写文件名里的地名/物名，不要编年代和作者。',
      '没有合适的图就写 "images": []（画面自动改用文字卡）。', '']
for n in data['nodes']:
    q = n.get('imageQuery', '').strip()
    nid = n['id']
    if not q:
        md += [f"## {nid} {n.get('place', '')}  （没有 imageQuery，跳过）", '']
        continue
    if nid not in cand or cand[nid].get('query') != q:
        per, seen = [], set()
        for part in [p.strip() for p in q.split('|') if p.strip()]:
            try:
                res = commons.search(part, 25)
            except Exception:
                res = []
            got = []
            for x in res:
                if x['title'] in seen:
                    continue
                seen.add(x['title'])
                if x.get('mime') not in OKMIME or (x.get('w') or 0) < 700 or not licence_ok(x.get('license', '')):
                    continue
                if AI.search((x.get('desc') or '') + ' ' + x['title']):
                    continue
                got.append(x)
            per.append(got)
        # round-robin over the keywords; at most 2 files of one photo series (same name without numbers)
        rows, series = [], {}
        for k in range(25):
            for got in per:
                if k < len(got):
                    stem = re.sub(r'[\d\s_\-,.()（）]+', '', got[k]['title'].rsplit('.', 1)[0])
                    if series.get(stem, 0) < 2:
                        series[stem] = series.get(stem, 0) + 1; rows.append(got[k])
        cand[nid] = {'query': q, 'items': []}
        for k, x in enumerate(rows[:12], 1):
            cand[nid]['items'].append(dict(code=f'{nid}-{k}', title=x['title'], w=x['w'], h=x['h'], license=x['license'],
                                           artist=(x.get('artist') or '')[:60], date=(x.get('date') or '')[:30],
                                           desc=re.sub(r'\s+', ' ', x.get('desc') or '')[:220], page=x.get('page')))
    items = cand[nid]['items']
    md += [f"## {nid} {n.get('place', '')} · {n.get('year', '')}  （搜索：{q}）", '']
    if not items:
        md += ['（没有授权合规的候选 → 换 imageQuery 关键词再运行，或留空用文字卡）', '']
    for x in items:
        md.append(f"- **{x['code']}**  {x['title']}  | {x['w']}x{x['h']} | {x['license']} | 作者 {x['artist'] or '—'} | {x['date'] or '—'}\n  说明：{x['desc'] or '—'}")
    md.append('')
json.dump(cand, open(cp, 'w'), ensure_ascii=False, indent=1)
open(os.path.join(CITY, 'research', 'images.md'), 'w').write('\n'.join(md))
print('candidates:', {k: len(v['items']) for k, v in cand.items()})
