# TEMPLATE-CHANGES

## A. v2 工程 → 冻结模板（建模板时的改动，南京验收开始前完成）

对照 `/workspace/opc-videos/huzhou-nianlun/v2/src/`。所有改动只把湖州专属内容换成从 `city.json` / `nodes.json` 读取，渲染数学（地形、着色、雾、景深、调色、运镜插值、字幕动画、配乐）一行未改。

| 文件 | 改动 |
|---|---|
| `src/scenes.js` | 原来是写死的湖州节点表 → 改为加载 `/city/city.json` + `/city/nodes.json`。节点没写 `dur`/`cam` 时按坐标自动计算：时长 = clamp((150−片头−片尾)/节点数, 9.5, 12) 秒（双图 +0.5）；镜头距离 = clamp(0.9 × 与最近节点间距, 6.5, 16) km，朝向 = 沿飞行方向 ±25°（同地点则转 110°），俯仰按序轮换，环绕方向交替；`scope: "region"` 节点用高空大全景。片头/片尾镜头按节点分布自动框定。没有图片又没写 `card` 的节点自动生成文字卡（大字 = 地名或年份）。`?fps=` 参数（默认 30）。 |
| `src/app.js` | `LON0/LAT0` ← `city.center`；高程放大 ← `city.map.exaggeration`（默认 2.6）；`COUNTIES`（湖州三县）→ 节点字段 `highlights`；苕溪河道 → `city.river`（可选）；“太湖”环境地名 → `city.ambient`；地图/图片路径加城市目录前缀；右下角地图署名 ← `city.mapCredit`。新增画质参数 `?scale=`（WebGL 分辨率缩放）和 `?samples=`（MSAA）；默认值 1 / 4 与 v2 完全相同。 |
| `src/index.html` | 去掉写死的标题和地图署名；import map 路径改为模板根目录；加 boot 错误捕获（数据文件缺失时渲染器立即报错而不是卡住）。 |
| `src/render.mjs` | 第一个参数是城市目录（模板挂在 `/`，城市目录挂在 `/city/`）；新增 `layout` 模式（在真实页面里测量每个节点的字幕是否换行/压图，供 `check.py` 使用）；`NL_SCALE`/`NL_SAMPLES`/`NL_FPS` 环境变量。 |
| `src/audio.py` | 只改了文件头注释。 |
| `render.sh` | 原 `finalize.sh` 的扩展：帧并行渲染 → 配乐 → mp4（编码参数与 v2 相同）→ 封面（片头 5.0 秒帧，与 v2 相同）→ 30 格缩略图 → ffprobe / 黑帧检测。 |
| `tools/` | v2 的 `fetch_tiles.py` / `fetch_gibs.py` / `prep_map.py` 合并成通用的 `fetch_map.py`（按节点自动框范围、自动挑选少云日期并多日期补洞、水体改用 JRC Global Surface Water，替代 v2 针对太湖颜色的阈值）；`commons.py` 沿用；新增 `init_city.py`、`geocode.py`、`wiki.py`、`find_images.py`、`fetch_images.py`（授权白名单 + AI 图排除）、`check.py`、`make_docs.py`。 |

**湖州一致性验证**：用模板 + `examples/huzhou/` 数据，与 v2 代码在 0.5、6、14、55.5、60、118、120、120.5、160 秒以及 25 秒（文字卡）逐帧截图比较，**最大像素差 = 0**（逐像素一致）。`examples/huzhou/` 的节点表在 `cam`/`dur` 里保留了 v2 的手调值，地图资产直接迁移自 v2（v2 的太湖颜色阈值水体掩膜），出处清单为 v2 人工撰写（`city.json` 中 `"docs": "manual"`）。

## B. 南京验收开始之后对模板的改动

（WorkBuddy 南京验收开始时间：2026-10-28 16:01。以下为此后对 `template/` 的修改。）

| 时间 | 文件 | 改动 | 原因 |
|---|---|---|---|
| 16:50 | `template/render.sh` | 帧缓存的版本键从 `ls -l assets/…`（含修改时间）改为对 `assets/img`、`assets/map` 文件内容取 md5；新增 `flock` 渲染锁，同一城市同时只允许一个渲染，后来者等待。 | WorkBuddy 的 Bash 工具单条命令最长 600 秒，模型用 `timeout 570 ./run.sh 南京 --draft` 反复续跑。每次重跑 `fetch_images.py` 都会重写图片文件，修改时间变了，版本键随之变化，已渲染的帧被整批删除（实测 1712 帧 → 30 帧），渲染永远完不成。被 timeout 杀掉的父进程留下的渲染子进程还会和新一轮抢同一批帧。改后重写图片内容不变（已验证 md5 一致），帧保留；子进程持有锁，新一轮等它们结束后续跑。 |
| 17:50 | `template/tools/make_docs.py` | 若城市目录有 `REVIEW.notes.md`（人工审校备注），每次生成 REVIEW.md 时附在末尾。 | 审校后重跑 `run.sh` 会重新生成 REVIEW.md，手写备注被覆盖（实测）。 |

两处改动都只涉及缓存、并发控制和清单生成，不涉及画面。湖州复验见 REPORT.md（湖州是 `docs: manual`，不经过 make_docs）。
