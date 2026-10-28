# REPORT · 城市年轮 skill（湖州 v2 冻结模板 + 南京验收）

日期：2026-10-28。本轮没有发布、上传或发送任何内容（没有推送 GitHub，也没有发飞书）。

## 1. 结论

| 验收项 | 结果 |
|---|---|
| (a) WorkBuddy（codebuddy CLI 2.172.1）+ **DeepSeek V4.1 flash**，只输入城市名“南京”，端到端出片 | **跑通**。一次会话完成（16:01:28 → 16:56:53，55 分钟，187 轮，退出码 0，最后一次 `run.sh` 打印 DONE）。中途没有人工介入对话。我（Claude）在它渲染期间修了一处模板渲染脚本的缓存 bug（见 §5）。 |
| (b) 画面与湖州 v2 约 1:1 | 模板与 v2 **逐像素一致**：湖州数据在 10 个时间点的截图与 v2 代码最大像素差 0；封面与 v2 `cover.png` 最大像素差 0。南京沿用同一套 3D 地图、运镜、调色、字幕版式、节点卡和配乐规则，对比两城的 contact.jpg 可见版式一致。 |
| 南京成片 ffprobe | 见 §3：**540×960（9:16），15 fps，169.0 秒，有音轨，无黑帧**。这是按要求的低分辨率验收版；正式版用 `./run.sh 南京` 出 1080×1920 / 30 fps。 |
| 模板代码 | WorkBuddy 没有改 `template/` 下任何文件（已核对它的全部写操作：只写了 `examples/nanjing/nodes.json`，并用 python 改了 `city.json` 的两个字段）。南京验收开始后，模板改过两处，都由我修改：`render.sh` 的帧缓存和渲染锁，`tools/make_docs.py` 保留人工审校备注。见 `TEMPLATE-CHANGES.md` §B。两处都不涉及画面，改后湖州仍能渲染。 |

## 2. 路径

```
/workspace/opc-videos/city-nianlun-skill/
  SKILL.md                    WorkBuddy 用法（够它独立做杭州：步骤、字段表、来源、挑图、报错对照、超时处理、分辨率参数）
  run.sh                      唯一入口（状态机）：./run.sh <城市名> [--draft]
  template/                   冻结模板
    src/                      index.html app.js scenes.js render.mjs audio.py
    render.sh                 渲染一条龙；NL_SCALE / NL_FPS / NL_SAMPLES 调分辨率、帧率、抗锯齿
    tools/                    init_city geocode wiki find_images fetch_images fetch_map check make_docs commons
    nodes.example.json        节点表格式示例
  TEMPLATE-CHANGES.md         v2 → 模板的改动；南京验收后对模板的改动
  REPORT.md                   本文件
  examples/huzhou/            湖州（v2 数据迁移）
    city.json nodes.json assets/  sources.md image-sources.md（v2 人工版原样迁移）
    cover.png                 1080×1920，与 v2 cover.png 逐像素一致
    huzhou-nianlun-draft540.mp4 / contact-draft540.jpg   模板渲染的 540×960 验证片（165.0 秒）
    （1080×1920 正片与 v2 逐像素一致，未重复渲染：/workspace/opc-videos/huzhou-nianlun/v2/huzhou-nianlun-v2.mp4）
  examples/nanjing/           南京（验收城市）
    nanjing-nianlun.mp4       验收成片（WorkBuddy 产出数据 + Claude 审校 6 处后重渲，见 §4）
    cover.png contact.jpg sources.md image-sources.md REVIEW.md
    city.json nodes.json research/（80 个原文文件）assets/（地图 + 30 张图）
    workbuddy-raw/            WorkBuddy 原样产出（审校前）：mp4、cover、contact、sources、image-sources、REVIEW、nodes.json、city.json
  workbuddy-test/             验收记录：prompt.txt、run_workbuddy.sh、workbuddy.jsonl（完整会话流）、workbuddy.log、summarize.py、review_fixes.py
```

## 3. 南京成片验证（ffprobe）

成片 `examples/nanjing/nanjing-nianlun.mp4`：

```
$ ffprobe -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,display_aspect_ratio -show_entries format=duration,size
stream|codec_name=h264|codec_type=video|width=540|height=960|display_aspect_ratio=9:16|r_frame_rate=15/1
stream|codec_name=aac|codec_type=audio
format|duration=169.000000|size=35207174
blackdetect: none            check.py --video: VIDEO 540x960 169.0s audio=yes · CHECK OK
```

- 制作方式：数据（city.json、nodes.json、调研原文、选图）由 **WorkBuddy + DeepSeek V4.1 flash** 用本 skill 产出；地理编码、地图、图片下载、校验、出处清单、渲染全部由 skill 脚本完成。我（Claude）审校后改了 nodes.json 的 6 处数据（§4），用同一条命令 `./run.sh 南京 --draft` 重渲。
- WorkBuddy 原样成片在 `examples/nanjing/workbuddy-raw/nanjing-nianlun.mp4`：540×960，15 fps，169.0 秒，有音轨，blackdetect 无黑帧。
- 分辨率是按本轮要求的验收档（`--draft` = 540×960 / 15 fps / 无 MSAA）。正式档 1080×1920 / 30 fps 用 `./run.sh 南京`，参数见 SKILL.md §6。

## 4. 南京节点（15 个，按时间顺序）

| # | id | 段落 | 年份 | 纪年 | 标题 | 地点 | 坐标（脚本地理编码） | 图 |
|---|---|---|---|---|---|---|---|---|
| 01 | n01 | 起源 | 距今数十万年 | 旧石器时代 · 葫芦洞 | 南京猿人 | 汤山（江宁区 · 汤山东麓） | 119.0627, 32.05 | 2 |
| 02 | n02 | 建城/得名 | 前472年 | 周元王四年 · 越 | 越城 | 长干里（秦淮区 · 中华门外） | 118.7721, 32.0152 | 2 |
| 03 | n03 | 建城/得名 | 前333年 | 战国 · 楚威王七年 | 金陵邑 | 清凉山（鼓楼区 · 石头山） | 118.7558, 32.0525 | 2 |
| 04 | n04 | 鼎盛 | 229年 | 东吴 · 黄龙元年 | 建业建都 | 石头城（鼓楼区 · 清凉山麓） | 118.7497, 32.0524 | 2 |
| 05 | n05 | 转折 | 589年 | 隋 · 开皇九年 | 建康湮灭 | 台城（玄武区 · 鸡鸣寺旁） | 118.79, 32.0631 | 2 |
| 06 | n06 | 鼎盛 | 937年 | 南唐 · 升元元年 | 江宁府 | 祖堂山（江宁区 · 南唐二陵） | 118.7336, 31.8906 | 2 |
| 07 | n08 | 鼎盛 | 1366年 | 元末 · 朱元璋始筑 | 城垣与瓮城 | 中华门（秦淮区 · 城南） | 118.7764, 32.0142 | 2 |
| 08 | n07 | 鼎盛 | 1368年 | 明 · 洪武元年 | 洪武定都 | 明故宫（秦淮区 · 中山东路） | 118.8124, 32.0396 | 2 |
| 09 | n09 | 鼎盛 | 1412年 | 明 · 永乐十年 | 大报恩寺 | 大报恩寺（秦淮区 · 雨花路） | 118.778, 32.011 | 2 |
| 10 | n10 | 转折 | 1842年 | 清 · 道光二十二年 | 南京条约 | 静海寺（鼓楼区 · 下关） | 118.7411, 32.0942 | 2 |
| 11 | n11 | 转折 | 1853年 | 太平天国 · 癸好三年 | 天京 | 天王府（玄武区 · 长江路） | 118.7922, 32.0461 | 2 |
| 12 | n12 | 近现代 | 1912年 | 民国元年 · 一月 | 临时大总统 | 总统府（玄武区 · 长江路） | 118.7922, 32.0461 | 2 |
| 13 | n13 | 近现代 | 1937年 | 民国二十六年 · 冬 | 南京大屠杀 | 江东门（建邺区 · 水西门大街） | 118.7435, 32.0355 | 2 |
| 14 | n14 | 近现代 | 1968年 | 12月29日 · 全线通车 | 长江大桥 | 长江大桥（下关 · 浦口） | 118.7397, 32.1153 | 2 |
| 15 | n15 | 今天 | 2003年 | 世界文化遗产 | 明孝陵 | 明孝陵（玄武区 · 紫金山南麓） | 118.8346, 32.0603 | 2 |

片头“南京的年轮 / 长江之畔 · 两千五百年 · 十五道年轮”；结尾唯一的提问“南京这十五道年轮里，你最想走进哪一年？”。
出处：每条事实都有两个不同网站的逐字引文（zh.wikipedia + 快懂百科），`check.py` 判定 0 条“待核对”。全部 30 张图来自 Wikimedia Commons，授权为公有领域、CC0、CC BY 或 CC BY-SA，被拒收 0 张，没有 AI 图，详见 `image-sources.md`。地图底图用 NASA GIBS HLS 少云日期拼接，地形用 AWS Terrain Tiles，水体用 JRC Global Surface Water。

### 审校改动（WorkBuddy 出片后，由 Claude 按 research/ 原文逐条审校；脚本 `workbuddy-test/review_fixes.py`）

`check.py` 只能核“引文是否逐字存在”，核不了“引文是否支持这句话”。WorkBuddy 版本里有以下问题，已在数据层修正后重渲：

1. **n08 纪年错**：1366 年写成“明 · 洪武年间”（洪武始于 1368 年）→ “元末 · 朱元璋始筑”；同时把它排到 n07（1368）之前，恢复时间顺序。
2. **n07 无据断语**：“南京第一次成为大一统王朝的京城”在引文里没有依据 → 换成有引文的“国号大明，建元洪武。”
3. **n01 年代**：大字“距今约60万年”只是来源说法中的一个 → 改为“距今数十万年”，正文写快懂百科原文“60万至35万年”；删去无据的“南京的人类史，从这里起笔”。
4. **n09** “历时十九年”补上维基原文引文“历时19年”。
5. **n10 图注**“· 国立故宫博物院”在 Commons 说明中没有依据，已删。
6. **n14 纪年栏**“中国 · 自力更生”不是史实 → “12月29日 · 全线通车”（维基原文“12月29日，公路桥正式通车，南京长江大桥全线贯通”）。

## 5. 待核对条目

脚本判定的“待核对”（单一来源、引文对不上）：**0 条**（`examples/nanjing/REVIEW.md`）。
人工审校后仍建议发布前确认的（已写进 `REVIEW.md`「人工审校备注」）：

- **n01** 南京猿人年代，各来源不一（58–62 万年 / 60–100 万年 / 60–35 万年）。
- **n04** “229年，孙权称帝，定都建业”合并了两件事：四月在武昌称帝，九月迁都建业。
- **n13** 画面写“三十万人遇难”，全国人大常委会 2014 年决定原文是“三十多万人”。建议改成一致的说法。
- **n11** 纪年栏“癸好三年”是纪年换算，引文里没有这个写法。
- **图注**：30 条图注由模型撰写，我对照 Commons 说明全部看过，改了 1 处（n10a）。
- **来源层级**：南京全部引文来自 zh.wikipedia + 快懂百科两家百科。规则上满足“两个不同网站”，但没有用到政府《历史沿革》页或正史原文（WorkBuddy 没有用 `wiki.py ws`）。发布前最好由人对照南京市政府网《历史沿革》或正史抽查。

湖州的待核对条目沿用 v2：中国非遗网、湖州市政府网在 v2 环境中打不开，相关条目是用搜索摘要核对的，见 `examples/huzhou/sources.md`。

## 6. WorkBuddy 实测记录（南京）

- 命令：`codebuddy -p "城市：南京。使用 city-nianlun skill（本目录的 SKILL.md）为南京出片，验收用 --draft。" --model deepseek-v4.1-flash -y`，工作目录是 skill 根目录。skill 以软链装在 `~/.codebuddy/skills/city-nianlun`（仅本机）。包装脚本最多允许 6 轮“继续”，实际 1 轮就完成，没有用到。
- 过程（完整流在 `workbuddy-test/workbuddy.jsonl`）：读 SKILL.md → `./run.sh 南京 --draft`（初始化，退出提示填表）→ 读 `events.md` 和维基原文 → 用 `wiki.py wp` / `wiki.py bk` 下载维基与快懂百科条目（research/ 里共 75 个 wp_/bk_ 文件，含初始化下载的 4 个）（5 个快懂百科词条不存在，FAILED，它换了词条名）→ 写 nodes.json（15 节点）和 city.json 两个字段 → `run.sh`（地理编码 15/15 成功 → 图片候选 → 退出提示挑图）→ 挑 30 张图并写图注 → `run.sh`（校验通过 → 生成地图 → 下载图片 → 版式校验 → 出处清单 → 渲染）。
- **卡住的地方 1（已修复）**：codebuddy 的 Bash 单条命令最长 600 秒，渲染约 35 分钟。模型改用 `timeout 570 ./run.sh 南京 --draft` 反复续跑，但 `render.sh` 的帧缓存键里含图片文件的修改时间，每次重跑都把已渲染的帧整批删掉（实测 1712 帧 → 30 帧），会无限循环。我在它运行中修了 `template/render.sh`：缓存键改为按文件内容，并加渲染锁。之后它自己核对了缓存键稳定，续跑完成。SKILL.md 新增 §5.5，教它遇到超时就后台运行再轮询。
- **卡住的地方 2（未阻断）**：模型用 `| tail` 截取输出，把 `run.sh` 的退出码吃掉了（它看到的总是 `EXIT=0`），但 run.sh 打印的“下一步”文字足够它判断下一步。之后我给 `run.sh` 加了最后一行 `RUN.SH EXIT <码>：<含义>`，截取输出也能看到结果。
- 模型为了理解流程读过 `scenes.js`、`check.py`、`geocode.py`、`render.sh`，并写过几段一次性的 python 小脚本：查引文、试地理编码、改 json。这些不是模板代码，没有写入 skill。
- **它做不到的**：语义核对（§4 的 6 处）。脚本能拦住编造的引文、编造的图片、超长文字、禁用词、坐标越界，拦不住“引文没写，但模型顺手加的断语”和“年号对错”。SKILL.md §2.3 已补这两条规则，但仍建议每个城市出片后做一次人工语义审校（REVIEW.md）。

## 7. 模板改动

见 `TEMPLATE-CHANGES.md`：
- **§A** v2 → 冻结模板：所有湖州专属内容改为从 city.json / nodes.json 读取；新增自动运镜、自动时长、默认文字卡、画质参数。渲染数学未改，湖州逐像素一致。
- **§B** 南京验收开始后：改了 `template/render.sh`（帧缓存键按文件内容计算 + 渲染锁）和 `template/tools/make_docs.py`（REVIEW.md 附上 `REVIEW.notes.md` 里的人工审校备注），都不涉及画面。改后复验：湖州用新 render.sh 出 540×960 / 165.0 秒 / 有音轨 / 无黑帧；`check.py examples/huzhou --layout` 通过；南京用新 render.sh 出片。

## 8. 交给 WorkBuddy 做杭州时

只需：`城市：杭州。使用 city-nianlun skill 出片（试看用 --draft）。` SKILL.md 已覆盖全部步骤、字段、来源用法、挑图规则、报错对照、超时处理和分辨率参数。开发时已用杭州试跑 init、地理编码、图片候选、校验、下载图片和出处清单，均正常；没有渲染杭州成片。
