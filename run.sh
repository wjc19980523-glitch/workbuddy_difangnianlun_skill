#!/bin/bash
# 《X的年轮》one entry point.  Run it again and again; it does every scripted step and stops only
# when the model has to fill in data, printing exactly what to do next.
#
#   ./run.sh <城市名>            e.g. ./run.sh 南京      (city folder: examples/<slug>/)
#   ./run.sh <城市名> --draft    quick acceptance render: 540x960, 15 fps, no MSAA
#   NL_SCALE / NL_FPS / NL_SAMPLES / NL_WORKERS override quality (see template/render.sh)
#
# Exit codes: 0 = film done · 10 = fill city.json + nodes.json · 11 = pick images · 1 = fix the listed errors
set -o pipefail
S="$(cd "$(dirname "$0")" && pwd)"; T="$S/template"; TL="$T/tools"
NAME="${1:?usage: ./run.sh <城市名> [--draft]}"
[ "$2" = "--draft" ] && export NL_SCALE="${NL_SCALE:-0.5}" NL_FPS="${NL_FPS:-15}" NL_SAMPLES="${NL_SAMPLES:-0}"
PY="python3 -I"
# last line always states the outcome (the exit code is lost when the caller pipes through tail)
trap 'c=$?; case $c in 0) m="DONE 或已完成本步";; 10) m="等待填写 city.json + nodes.json";; 11) m="等待挑图";; *) m="有错误，按上面的 ERROR / FAILED 修改后重跑";; esac; echo "RUN.SH EXIT $c：$m"' EXIT
say() { echo; echo "==================== $*"; }

# ---------------------------------------------------------------- 1. city folder (geocode + research pack)
C=""
if [ -f "$NAME/city.json" ]; then C="$(cd "$NAME" && pwd)"; else
  for d in "$S"/examples/*/; do
    [ -f "$d/city.json" ] && [ "$($PY -c 'import json,sys;print(json.load(open(sys.argv[1])).get("name",""))' "$d/city.json")" = "${NAME%市}" ] && C="${d%/}"
  done
fi
if [ -z "$C" ]; then
  say "步骤 1/8 初始化城市：地理编码 + 下载调研资料"
  C=$($PY "$TL/init_city.py" "$NAME" "$S/examples" | tail -1) || { echo "STEP 1 FAILED: init_city.py"; exit 1; }
fi
echo "城市目录：$C"
R="$C/research"

# ---------------------------------------------------------------- 2. the model fills city.json + nodes.json
if [ ! -f "$C/nodes.json" ] || grep -q TODO "$C/city.json"; then
  say "下一步（模型填写）：city.json + nodes.json"
  cat <<EOF
1. 读 $R/events.md（带年份的史实句子）和 $R/INDEX.md（资料文件 → 网址）。
2. 按 SKILL.md「第 2 步 填表」挑 10–15 个节点（顺序：起源 → 建城/得名 → 鼎盛 → 转折 → 近现代 → 今天）。
3. 每个节点要第二个网站的原文：运行
     python3 -I $TL/wiki.py wp $R <维基条目名>      （维基百科）
     python3 -I $TL/wiki.py bk $R <词条名>          （快懂百科）
     python3 -I $TL/wiki.py ws $R <维基文库篇名>     （正史/条约原文，如 三國志/卷47）
   引文必须从 research/ 里的文件原样复制。
4. 照 $T/nodes.example.json 的格式写 $C/nodes.json；把 $C/city.json 里的 TODO（subtitle、outro.question）改掉。
   不要写经纬度（脚本会查），不要写图片文件名（下一步从候选里挑编号）。
5. 再运行：./run.sh $NAME${2:+ $2}
EOF
  exit 10
fi

# ---------------------------------------------------------------- 3. coordinates
say "步骤 3/8 地理编码（geo → 经纬度）"
$PY "$TL/geocode.py" "$C" || { echo "STEP 3 FAILED: 按上面提示改 nodes.json 里的 geo，再运行 ./run.sh $NAME${2:+ $2}"; exit 1; }

# ---------------------------------------------------------------- 4. image candidates
say "步骤 4/8 Wikimedia Commons 图片候选（只收公有领域 / CC0 / CC BY / CC BY-SA）"
$PY "$TL/find_images.py" "$C" || { echo "STEP 4 FAILED: find_images.py"; exit 1; }
if ! $PY -c 'import json,sys; ns=json.load(open(sys.argv[1]))["nodes"]; sys.exit(0 if all("images" in n for n in ns) else 1)' "$C/nodes.json"; then
  say "下一步（模型挑图）"
  cat <<EOF
打开 $R/images.md，给每个节点写
   "images": [{"pick": "候选编号", "caption": "图注（只依据候选“说明”写，≤30字）"}]
最多 2 张；没有切题的就写 "images": []（自动用文字卡）。觉得候选都不对，可改 "imageQuery" 后重跑。
每个节点都必须有 "images" 这个字段（哪怕是 []）。然后再运行：./run.sh $NAME${2:+ $2}
EOF
  exit 11
fi

# ---------------------------------------------------------------- 5. data check (before any heavy work)
say "步骤 5/8 数据校验"
$PY "$TL/check.py" "$C" || { echo "STEP 5 FAILED: 按 ERROR 逐条修改 nodes.json / city.json，再运行 ./run.sh $NAME${2:+ $2}"; exit 1; }

# ---------------------------------------------------------------- 6. map + images
say "步骤 6/8 3D 地图数据（卫星影像 / 地形 / 水体）与图片下载"
if [ -f "$C/assets/map/grid.json" ] && ! $PY - "$C" <<'EOF'
import json, sys, os
c = sys.argv[1]; g = json.load(open(os.path.join(c, 'assets/map/grid.json')))['core']
ns = json.load(open(os.path.join(c, 'nodes.json')))['nodes']
sys.exit(0 if all(g['lon0'] + .05 < n['lon'] < g['lon1'] - .05 and g['lat0'] + .05 < n['lat'] < g['lat1'] - .05 for n in ns) else 1)
EOF
then echo "有节点在现有地图范围外 → 重新生成地图"; rm -f "$C/assets/map/grid.json" "$C/assets/map/sat_hi.json"; $PY - "$C/city.json" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1])); c.get('map', {}).pop('core', None); c.get('map', {}).pop('wide', None)
json.dump(c, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
EOF
fi
if [ ! -f "$C/assets/map/grid.json" ]; then
  $PY "$TL/fetch_map.py" "$C" $([ -f "$C/assets/map/sat_hi.json" ] || echo --refetch) || { echo "STEP 6 FAILED: fetch_map.py（网络问题可直接重跑，已下载的瓦片会复用）"; exit 1; }
fi
$PY "$TL/fetch_images.py" "$C" || { echo "STEP 6 FAILED: fetch_images.py（网络问题可直接重跑）"; exit 1; }

# ---------------------------------------------------------------- 7. layout check in the real page + docs
say "步骤 7/8 版式校验 + 生成出处清单"
$PY "$TL/check.py" "$C" --layout || { echo "STEP 7 FAILED: 按 ERROR 缩短文字，再运行 ./run.sh $NAME${2:+ $2}"; exit 1; }
$PY "$TL/make_docs.py" "$C" || { echo "STEP 7 FAILED: make_docs.py"; exit 1; }

# ---------------------------------------------------------------- 8. render
say "步骤 8/8 渲染（scale=${NL_SCALE:-1} fps=${NL_FPS:-30} msaa=${NL_SAMPLES:-4}）"
"$T/render.sh" "$C" "${NL_WORKERS:-4}" || { echo "STEP 8 FAILED: render.sh（看 $C/build/logs/；可直接重跑，已渲染的帧会复用）"; exit 1; }
SLUG=$($PY -c 'import json,sys;print(json.load(open(sys.argv[1]))["slug"])' "$C/city.json")
$PY "$TL/check.py" "$C" --video "$C/$SLUG-nianlun.mp4" || { echo "STEP 8 FAILED: 成片校验"; exit 1; }
say "DONE"
echo "成片：$C/$SLUG-nianlun.mp4"
echo "封面：$C/cover.png   缩略图：$C/contact.jpg"
echo "出处：$C/sources.md   图片授权：$C/image-sources.md   待核对：$C/REVIEW.md"
