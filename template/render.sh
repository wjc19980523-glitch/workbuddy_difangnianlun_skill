#!/bin/bash
# Step 2 — one-command render.   template/render.sh <cityDir> [workers]
# Reads only <cityDir>/city.json, nodes.json, assets/. Writes into <cityDir>:
#   <slug>-nianlun.mp4, cover.png, contact.jpg   (+ build/ with frames, score, logs)
# Quality (environment variables, defaults = final 1080x1920 quality):
#   NL_SCALE=1     output scale: 1 → 1080x1920, 0.6667 → 720x1280, 0.5 → 540x960
#   NL_FPS=30      frame rate (15 for quick drafts; timeline and music are unchanged)
#   NL_SAMPLES=4   MSAA samples (0 for drafts)
set -e
T="$(cd "$(dirname "$0")" && pwd)"
C="$(cd "${1:?usage: render.sh <cityDir> [workers]}" && pwd)"
W="${2:-3}"
export NL_SCALE="${NL_SCALE:-1}" NL_FPS="${NL_FPS:-30}" NL_SAMPLES="${NL_SAMPLES:-4}"
cd "$T"
[ -d node_modules/three ] || npm install --no-audit --no-fund
SLUG=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['slug'])" "$C/city.json")
OUT="$C/$SLUG-nianlun.mp4"
B="$C/build"; mkdir -p "$B/frames" "$B/logs"
exec 9> "$B/render.lock"; flock -n 9 || { echo "另一个渲染正在进行（$B/render.lock），等待它结束…"; flock 9; }
node src/render.mjs "$C" info 2>/dev/null | grep '^{' > "$B/segments.json"
TOTAL=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['total'])" "$B/segments.json")
NF=$(python3 -I -c "import sys;print(round(float(sys.argv[1])*int(sys.argv[2])))" "$TOTAL" "$NL_FPS")
echo "timeline: $TOTAL s, $NF frames @ ${NL_FPS}fps, scale $NL_SCALE, msaa $NL_SAMPLES, $W workers"
[ -s "$B/score.wav" ] && [ "$B/score.wav" -nt "$B/segments.json" ] && cmp -s "$B/segments.json" "$B/score.key" || {
  python3 -I src/audio.py "$B/segments.json" "$B/score.wav"; cp "$B/segments.json" "$B/score.key"; }
# frames from another timeline / quality setting are removed so resume never mixes versions
KEY=$( (cat "$C/city.json" "$C/nodes.json" "$B/segments.json"; echo "$NL_SCALE $NL_FPS $NL_SAMPLES"; cd "$C/assets" && find img map -type f ! -name '*.json' -print0 | sort -z | xargs -0 md5sum) | md5sum)
if [ ! -f "$B/frames.key" ] || [ "$(cat "$B/frames.key")" != "$KEY" ]; then rm -f "$B/frames/"*.jpg; fi
echo "$KEY" > "$B/frames.key"
PIDS=()
for k in $(seq 0 $((W-1))); do
  s=$((NF*k/W)); e=$((NF*(k+1)/W))
  ( for try in 1 2 3 4 5; do node src/render.mjs "$C" frames "$B/frames" $s $e >> "$B/logs/w$k.log" 2>&1 && break; sleep 5; done ) &
  PIDS+=($!)
done
for p in "${PIDS[@]}"; do wait $p; done
N=$(ls "$B/frames" | grep -c '\.jpg$' || true)
[ "$N" -ge "$NF" ] || { echo "RENDER FAILED: only $N/$NF frames rendered, see $B/logs"; exit 1; }
ffmpeg -loglevel error -y -framerate "$NL_FPS" -i "$B/frames/f%05d.jpg" -i "$B/score.wav" \
  -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11" -c:v libx264 -preset slow -crf 23 -maxrate 12M -bufsize 24M -pix_fmt yuv420p \
  -profile:v high -movflags +faststart -c:a aac -b:a 192k -ar 48000 -shortest "$OUT"
node src/render.mjs "$C" shot 5.0 "$C/cover.png" > /dev/null 2>&1
STEP=$(python3 -I -c "import sys;print(float(sys.argv[1])/30)" "$TOTAL")
ffmpeg -loglevel error -y -i "$OUT" -vf "fps=1/$STEP,scale=216:384,tile=6x5:padding=4:margin=4:color=black" -frames:v 1 -q:v 3 "$C/contact.jpg"
echo "== ffprobe"; ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,display_aspect_ratio -show_entries format=duration -of compact "$OUT" | tee "$B/ffprobe.txt"
ffmpeg -hide_banner -i "$OUT" -vf "blackdetect=d=0.5:pix_th=0.06" -an -f null - 2>&1 | grep -E "blackdetect" || echo "blackdetect: none"
echo "RENDER OK: $OUT"
