# 城市年轮 skill（WorkBuddy）

输入一个城市名，自动调研、填节点表、下载地图和配图，渲染一条约 2–3 分钟的竖屏「城市年轮」视频（3D 地图 + 时间轴节点卡 + 配乐），版式与「湖州 v2」一致。

## 快速开始

```bash
cd template && npm install && cd ..
./run.sh 杭州            # 正式档：1080×1920 / 30fps
./run.sh 杭州 --draft    # 验收档：540×960 / 15fps，更快
```

第一次运行会建好 `examples/<slug>/` 并下载调研资料，然后提示执行模型填写 `nodes.json` 和 `city.json` 的两个字段；填完再跑一次 `./run.sh <城市名>` 即可出片。完整步骤、字段说明、报错对照见 [SKILL.md](SKILL.md)。

## 目录

- `SKILL.md`：给 WorkBuddy（或其他执行模型）的完整用法
- `run.sh`：唯一入口
- `template/`：冻结模板（渲染代码 + 工具脚本），执行模型不改这里
- `examples/huzhou/`：湖州示例（与 v2 逐像素一致）
- `examples/nanjing/`：南京验收示例（WorkBuddy + DeepSeek V4.1 flash 只输入“南京”跑通）
- `ACCEPTANCE-REPORT.md`、`TEMPLATE-CHANGES.md`：验收记录与模板改动

成片视频、渲染中间文件和 `node_modules` 不入库（见 `.gitignore`），本地运行时重新生成。

## 许可

MIT，见 [LICENSE](LICENSE)。示例里的图片来自各自出处，见各城市的 `image-sources.md`。
