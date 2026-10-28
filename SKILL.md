---
name: city-nianlun
description: 城市年轮：只给一个城市名（如“南京”“杭州”），产出《X的年轮》2–3 分钟 9:16 电影感 3D 地图历史短片（10–15 个有出处的节点、真实且授权合规的史料图片、出处与授权清单）。模型只填表（city.json + nodes.json），地理编码、地图、图片下载、校验、渲染全部由脚本完成。
---

# 城市年轮 Skill（《X的年轮》）

**一句话**：`./run.sh <城市名>`，按它打印的“下一步”填两张表，反复运行同一条命令，直到打印 `DONE`。

- 模板（3D 地图舞台、运镜、电影调色、字幕版式、节点卡、配乐）**冻结**在 `template/`，**禁止修改** `template/` 里的任何文件。
- 你（执行模型）**只写数据**：`examples/<slug>/city.json` 里的 2 个字段 + `examples/<slug>/nodes.json`。**不写代码，不写经纬度，不写图片网址/文件名。**
- 所有命令都在本 skill 根目录（`run.sh` 所在目录）执行。

---

## 0. 环境（一般已就绪，出错时才看）

需要：`python3`（numpy、Pillow）、`node` ≥ 18、`ffmpeg`/`ffprobe`、`/usr/bin/google-chrome`（或设环境变量 `CHROME=<chrome 路径>`）、中文字体 Noto Serif/Sans CJK、能访问 zh.wikipedia.org / zh.wikisource.org / commons.wikimedia.org / www.baike.com / nominatim.openstreetmap.org / gibs.earthdata.nasa.gov / s3.amazonaws.com / storage.googleapis.com。
`template/node_modules/` 已带好（three、puppeteer-core）；缺失时 `render.sh` 会自动 `npm install`。

---

## 1. 开始：只给城市名

```bash
./run.sh 杭州            # 正式版 1080x1920 30fps
./run.sh 杭州 --draft    # 验收/试看版 540x960 15fps，快 4–6 倍
```

第一次运行会：地理编码城市 → 建目录 `examples/<slug>/`（如 `examples/hangzhou/`）→ 下载调研资料到 `research/`，然后退出（退出码 10）并提示你填表。

`research/` 里会有：
| 文件 | 内容 |
|---|---|
| `events.md` | 维基百科城市条目、《X历史》条目里**所有带年份的句子**，编号列出 —— 从这里挑节点 |
| `wp_city.txt` `wp_history.txt` | zh.wikipedia 城市条目 / 历史条目全文 |
| `bk_*.txt` | 快懂百科（baike.com）词条导语 —— 第二个网站 |
| `INDEX.md` | 每个资料文件 → 来源网址 |

---

## 2. 第一次填表（退出码 10 时）

### 2.1 挑 10–15 个节点

按固定叙事骨架，**按时间顺序**排列（每段 1–3 个节点）：

`起源`（史前遗址/最早人类活动）→ `建城/得名`（筑城、置县/郡、名字由来）→ `鼎盛`（建都、名人、名作、名产）→ `转折`（战争、条约、政权更替）→ `近现代`（民国、建国后重大事件/工程）→ `今天`（世界遗产、国家级非遗、标志性工程）

挑选原则：
1. 只挑 `events.md` 或资料文件里**写明了**的事；资料里没有的事不要上。
2. 优先挑有**具体地点**的事（遗址、城门、寺庙、陵墓、大桥……），地图才能飞过去。
3. 同一地点可以有多个节点（如城区），但全片至少要有 5 个不同地点。
4. 节点数 10–15，推荐 12–14。

### 2.2 为每个节点补第二个网站的原文

规则：**每条上屏的事实，要有 2 个不同网站的原文逐字支持**，才算“已核”；否则自动标“⚠️ 待核对”（仍可上片，但会进 `REVIEW.md` 等人工核对）。
维基百科（zh/en）算同一个网站。可用的第二来源（用脚本下载，**不要凭记忆写网址**）：

```bash
python3 -I template/tools/wiki.py wp examples/<slug>/research 中山陵 南京长江大桥      # 维基百科条目（可多个）
python3 -I template/tools/wiki.py bk examples/<slug>/research 中山陵 南京长江大桥      # 快懂百科词条
python3 -I template/tools/wiki.py ws examples/<slug>/research 三國志/卷47 明史/卷2     # 维基文库原文（正史、条约、公报）
python3 -I template/tools/wiki.py url examples/<slug>/research 名字 https://...        # 政府/新闻网页（你确知网址时）
```
输出 `ok ...` 才算下载成功；`FAILED` 的来源不能用。下载的文件名见输出或 `research/INDEX.md`。
维基文库常用篇名：`三國志/卷47`（吴主传）、`晉書/卷6`、`新唐書/卷196`、`宋史/卷338`、`元史/卷172`、`明史/卷2`（太祖本纪）、`明史/卷304`（郑和传）、`南京條約`。正史卷号不确定就先用 `wp` 下载人物/事件条目，从条目里找“《XX书·XX传》”。

### 2.3 写 `examples/<slug>/nodes.json`

格式照抄 `template/nodes.example.json`。每个节点的字段：

| 字段 | 必填 | 写什么 | 上限 |
|---|---|---|---|
| `id` | ✔ | `n01` `n02` … 按顺序 | |
| `phase` | ✔ | 起源 / 建城/得名 / 鼎盛 / 转折 / 近现代 / 今天 | |
| `place` | ✔ | 地图上的地名标签，如“中华门” | 8 字 |
| `where` | ✔ | 地名下的小字，如“秦淮区 · 城南” | 14 字 |
| `geo` | ✔ | 用来查坐标的名字：**维基百科条目名**最好（如“中华门”“南京长江大桥”），或 OSM 能搜到的地名 | |
| `year` | ✔ | 大字年份：“前472年”“229年”“1912年”“距今约60万年”“庆历年间” | 8 字 |
| `era` | ✔ | 年份下的小字：朝代 · 年号，如“明 · 洪武元年” | 16 字 |
| `title` | ✔ | 节点标题 | 12 字 |
| `body` | ✔ | 解说，**数组**，2–3 行（最多 4 行），每行一句 | 每行 21 字 |
| `src` | ✔ | 画面上的“出处｜…”一行，写书名/网站名，如“《三国志·吴主传》· 维基百科” | 40 字 |
| `facts` | ✔ | 画面上每条事实 + 引文，见下 | |
| `imageQuery` | ✔ | Commons 搜图关键词，中英文都写，用 `|` 分隔，如 `"中华门 | Zhonghua Gate Nanjing"` | |

`facts` 写法：
```json
"facts": [
  {"text": "画面上那条事实（一句话）",
   "quotes": [
     {"file": "wp_中山陵.txt", "quote": "从该文件原样复制的一段原文"},
     {"file": "bk_中山陵.txt", "quote": "另一个网站文件里的原文"}
   ]}
]
```
- `file` 只写文件名（必须在 `research/` 里）；`quote` 从文件里**原样复制**连续 6 字以上（繁体照抄繁体，标点空格可以不同）。脚本逐字比对，对不上就判“待核对”。
- 画面上的数字（年份等）要出现在引文里；对不上的会进待核对清单。
- 不写 `lon` `lat` `dur` `cam` `images`（这些由脚本或下一步处理）。
- **画面上的每一句话（body 每行、era 里的朝代/年号）都要能在 facts 的引文里找到依据**。脚本只能核对引文是否逐字存在，核不了“引文是否支持这句话”，所以：不写引文里没有的评价和推断（如“第一次成为……”“从这里起笔”）；`era` 的年号要和 `year` 对得上（例：1366 年是元至正二十六年，不能写“明 · 洪武”）。

### 2.4 改 `examples/<slug>/city.json` 的两个 TODO

- `subtitle`：片头副标题，≤20 字，用“ · ”分隔三段，如 `"长江之畔 · 两千五百年 · 十四道年轮"`（数字与节点数一致，年数要有节点支撑）。
- `outro.question`：结尾**唯一**的提问，恰好一个问号、以问号结尾，最多 2 行、每行 ≤13 字，用 `\n` 换行，如 `"南京这十四道年轮里，\n你最想走进哪一年？"`。
- 其他字段（slug、center、adminBBox、map、mapCredit、ambient）脚本自动写或保持默认，**不要改**。

然后再运行 `./run.sh <城市名>`。

---

## 3. 挑图（退出码 11 时）

脚本已为每个节点在 Wikimedia Commons 搜好**授权合规**的候选（公有领域 / CC0 / CC BY / CC BY-SA，已排除 AI 生成图），列在 `research/images.md`，每个候选有编号如 `n03-2` 和 Commons 说明。

给**每个**节点加 `images` 字段：
```json
"images": [{"pick": "n03-2", "caption": "中华门瓮城（2019年摄）"}]
```
- 最多 2 张；`pick` 只能用 `images.md` 里的编号。
- `caption` ≤30 字，只依据候选的“说明”和文件名写：是什么、哪里、（说明里有的话）哪年摄/哪个馆藏。**说明里没有的年代、作者、馆藏不要写。**
- 选图要切题：古画/古籍书影/老照片 > 遗址/文物照片 > 现状风景。无关或看不懂的不要选。
- 没有合适的写 `"images": []`，画面自动换成文字卡（大字 = 地名或年份）。
- 候选都不对：改该节点的 `imageQuery`（换关键词，加英文），重跑即可刷新候选。
- 图注下面的署名（作者 · 协议）由脚本自动加，不用写。

然后再运行 `./run.sh <城市名>`。

---

## 4. 修错（退出码 1 时）

脚本会打印 `ERROR 节点 N（id=…）：…`，每条都说了改哪个字段。照做后重跑。常见：

| 报错 | 怎么改 |
|---|---|
| 太长 / 一行放不下 | 缩短该字段；body 拆成两行 |
| 查不到坐标 | 把 `geo` 换成维基百科条目名或附近的著名地标 |
| 坐标不在城市范围 | `geo` 查到了别的城市的同名地点 → 改成“城市名+地名”或条目全名 |
| 图片编号不在候选里 | 只能用 `research/images.md` 里的编号 |
| outro.question 问号 | 全句只能有一个问号，且放在最后 |
| 禁用词 | 删掉：账号名、粉丝群、“下期”“继续测”“关注”“点赞”“据本人称”等 |
| 总时长不在 120–180 秒 | 节点数改到 10–15；不要写 `dur` |
| STEP 6/8 网络失败 | 直接重跑，已下载的会复用 |

`⚠️ 待核对` 不是错误，不会阻止出片；但要尽量补第二来源把它消掉（2.2）。

---

## 5. 完成（打印 DONE 时）

产物都在 `examples/<slug>/`：

| 文件 | 内容 |
|---|---|
| `<slug>-nianlun.mp4` | 成片（9:16，2–3 分钟） |
| `cover.png` | 封面（片头标题帧） |
| `contact.jpg` | 30 格缩略图，检查有无黑屏/错乱 |
| `sources.md` | 每个节点每条事实的引文、网址、核对状态 |
| `image-sources.md` | 每张图的 Commons 链接、作者、授权；文字卡节点；被拒收的图；地图数据来源 |
| `REVIEW.md` | **待人工核对清单**（单一来源、引文对不上、图注需过目） |

最后自查：打开 `contact.jpg` 看地图、卡片是否正常；把 `REVIEW.md` 交给人工。人工审校的备注写在 `examples/<slug>/REVIEW.notes.md`，每次重跑都会附在 REVIEW.md 末尾，不会被覆盖。`run.sh` 输出的最后一行总是 `RUN.SH EXIT <码>：<含义>`。**不要发布、不要上传到任何地方**（除非用户另有指示）。

---

## 5.5 渲染很慢 / 命令有超时（重要）

步骤 6（地图）和步骤 8（渲染）要 20–60 分钟。如果你的命令工具有时长上限（如 600 秒），**不要**用 `timeout` 硬切，改用后台运行再轮询：
```bash
nohup ./run.sh 南京 --draft > examples/nanjing/run.log 2>&1 &
tail -5 examples/nanjing/run.log                  # 隔几分钟看一次
ls examples/nanjing/build/frames | wc -l          # 已渲染帧数（总帧数见 run.log 的 timeline 行）
```
直到 `run.log` 出现 `DONE`（或 `FAILED`）。同一城市同时只会有一个渲染在跑（有锁），重复启动的会排队等待；中断后再运行会接着已渲染的帧继续，不会重来。

## 6. 分辨率与速度参数

| 用法 | 命令 | 输出 |
|---|---|---|
| 正式版（默认） | `./run.sh 杭州` | 1080x1920，30fps，MSAA 4 |
| 验收/试看 | `./run.sh 杭州 --draft` | 540x960，15fps，无 MSAA |
| 自定义 | `NL_SCALE=0.6667 NL_FPS=30 NL_SAMPLES=2 NL_WORKERS=4 ./run.sh 杭州` | 720x1280 |

`NL_SCALE` 缩放 WebGL 与页面（1 = 1080x1920）；`NL_FPS` 帧率（时间线与配乐不变）；`NL_SAMPLES` 抗锯齿；`NL_WORKERS` 并行渲染进程数（CPU 核数的一半左右）。换参数后已渲染的帧会自动作废重渲。

---

## 7. 硬规则（脚本会拦，但你也要遵守）

- 不出现账号名、不提粉丝群、结尾不写“下期继续测/拆”，只留一个给评论区的问题；不加“据本人称”。
- 不编造：资料里没有的事不上；拿不准的删掉或保留为“待核对”。
- 只用脚本从 Commons 下载的授权合规真实图片；**绝不用 AI 生成图**，也不要自己找图片网址。
- 不改 `template/`。确有必要改模板时，记录到 `TEMPLATE-CHANGES.md` 并确认 `examples/huzhou` 仍能渲染。

---

## 8. 目录

```
run.sh                    唯一入口（状态机，可反复运行）
template/                 冻结模板（禁止修改）
  src/                    index.html app.js（3D 地图/运镜/调色/字幕/卡片） scenes.js（默认时长与运镜） render.mjs audio.py
  render.sh               渲染一条龙（帧 → 配乐 → mp4 → 封面 → 缩略图 → ffprobe）
  tools/                  init_city geocode wiki find_images fetch_images fetch_map check make_docs commons
  nodes.example.json      节点表格式示例
examples/huzhou/          湖州（v2 迁移；docs=manual，出处清单为人工撰写；与 v2 逐像素一致）
examples/nanjing/         南京（验收城市）
```

模板自动做的事（不需要你管）：地图范围按节点坐标自动框定并下载卫星影像/地形/水体；每个节点的镜头距离按与最近节点的间距自动算，镜头朝向沿飞行方向；节点间远距离走高空弧线飞越、近距离低空推进；时长按节点数自动分配（总长 120–180 秒）；配乐按时间线自动生成。湖州版的节点里写了 `cam`/`dur` 是为了与 v2 逐像素一致，新城市不要写。
