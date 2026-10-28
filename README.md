# 麦门大教堂 · MCD Cathedral

<p align="center">
<img src="assets/hero.webp" width="100%" alt="麦门大教堂门面横幅：石质立面立于阶座之上，两道高尖拱勾出 M 形轮廓，拱上方居中一面圆形玫瑰窗带放射石棱，屋脊立细尖塔，两侧各一盏点燃的壁烛，米白天空与绛红地带">
</p>

> **把「麦门」做成一座赛博大教堂：每天 30 秒，替你抢救正在过期的券和积分。**

![零依赖](https://img.shields.io/badge/零依赖-Python_标准库-FFC72C?style=for-the-badge&labelColor=27251F)
![官方 MCP：9 个 CLI 直调 · 4 个 AI 编排](https://img.shields.io/badge/官方_MCP-9_直调_·_4_编排-DA291C?style=for-the-badge&labelColor=27251F)
![五大日课：晨祷 领恩 盘点 守夜 奉献录](https://img.shields.io/badge/五大日课-晨祷_领恩_盘点_守夜_奉献录-FFC72C?style=for-the-badge&labelColor=27251F)

```bash
python cli/cathedral.py --demo relics  # 无需 Token，30 秒看完整效果
```

## 🌅 先看一眼晨祷

```text
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                  演示模式 · DEMO                   ┃
┃ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ┃
┃  数据为 2026-10-10 09:26 真实实测快照，非实时查询  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                 麦门大教堂 · 晨祷                  ┃
┃                 2026-10-10 星期六                  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
┌────────────────────────────────────────────────────┐
│ 今日箴言                                           │
│ ────────────────────────────────────────────────── │
│ 麦门信众，天下一家。                               │
└────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────┐
│ 今日布告                                           │
│ ────────────────────────────────────────────────── │
│ · 超值9.9元早餐两件套陪你开工啦                    │
│ · 麦当劳 X PEACEMINUSONE                           │
│ · 麦咖啡一早现磨元气早餐震撼来袭！                 │
│ · 麦当劳联动G-DRAGON                               │
│ · 韩式风味蘸酱上新就「酱」心有所「薯」             │
└────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────┐
│ 可领恩惠                                           │
│ ────────────────────────────────────────────────── │
│ 信徒的恩惠已领尽，今日无可领之券。                 │
└────────────────────────────────────────────────────┘
──────────────────────────────────────────────────────
                   阿门，麦门永存。                   
```

> 以上为 2026-10-10 实测快照，`--demo` 可原样复现。

## ⛪ 五大日课

<table>
<tr>
<td width="33%" valign="top" align="center">
<img src="assets/ritual-matins.webp" width="120" alt="晨祷徽记：圆形玫瑰窗后升起日轮，窗上方三道细光束，窗下悬一口小钟"><br>
🌅 <b>晨祷</b><br>
<code>python cli/cathedral.py matins</code><br>
今日日签：今日布告 + 可领恩惠 + 一句麦门箴言。<br>
<code>now-time-info</code> <code>campaign-calendar</code> <code>available-coupons</code>
</td>
<td width="33%" valign="top" align="center">
<img src="assets/ritual-grace.webp" width="120" alt="领恩徽记：石座上一只浅口奉献盘，盘上方三枚圆形钱币呈弧形悬浮"><br>
🧧 <b>领恩</b><br>
<code>python cli/cathedral.py grace</code><br>
一键领尽麦麦省所有可领之券，幂等、绝不漏领。<br>
<code>auto-bind-coupons</code>
</td>
<td width="33%" valign="top" align="center">
<img src="assets/ritual-relics.webp" width="120" alt="圣物盘点徽记：多层石龛里并置三只小圣物匣，旁边一摞圆形钱币，下方一排短烛"><br>
📦 <b>圣物盘点</b><br>
<code>python cli/cathedral.py relics</code><br>
券包与积分全资产巡检，临期券按剩余天数排倒计时条。<br>
<code>query-my-coupons</code> <code>query-my-account</code>
</td>
</tr>
<tr>
<td width="33%" valign="top" align="center">
<img src="assets/ritual-vigil.webp" width="120" alt="守夜徽记：尖拱下一支点燃的高烛与一只沙漏并立，沙漏中沙粒下落，烛底积着融蜡"><br>
⚰️ <b>守夜日课</b><br>
<code>python cli/cathedral.py vigil</code><br>
对七日内过期的券与积分逐项给核销路径；报价必先核价。<br>
CLI 实际调用：<code>query-my-coupons</code> <code>query-my-account</code> <code>mall-points-products</code>（仅当下月有临期积分）<br>
AI 主持时按需追加：<code>query-nearby-stores</code> <code>query-meals</code> <code>query-meal-detail</code> <code>calculate-price</code>
</td>
<td width="33%" valign="top" align="center">
<img src="assets/ritual-ledger.webp" width="120" alt="奉献录徽记：石质读经台上摊开一本小金册，页面刻着几行记数痕，一支细金羽笔斜搭其上，旁有一小枚蜡封"><br>
📜 <b>奉献录</b><br>
<code>python cli/cathedral.py ledger</code><br>
订单考古：消费足迹、常驻堂区、忠诚圣物、奉献值结算与阶位。<br>
<code>order-list</code> <code>list-nutrition-foods</code>
</td>
<td width="33%" valign="middle" align="center">
⚡ <b>30 秒直测</b><br>
<code>python cli/cathedral.py --demo relics</code><br>
<code>--demo</code> 读 2026-10-10 实测快照，不发网络请求、不需要 Token，输出顶部带 DEMO 横幅。<br>
<b>评委可直接跑</b>
</td>
</tr>
</table>

## 📊 实测战绩（2026-10-10 真实账号）

| 实测值 | 是什么 | 这说明什么 |
|-------:|--------|-----------|
| **27 张** | 在持优惠券 | 一个普通会员的券包，厚度远超自己的记忆 |
| **12 张** | 七日内临期券 | 接近一半的券将在一周内归零，不盘点等于白送 |
| **1572.8 分** | 已熄灭积分 | 不是假设的损失，是本账号已经发生的损失 |
| **1483 分** | 当前可用积分 | 还救得回来的那部分，就是「守夜」的对象 |
| **9 个** | CLI 直接调用的官方 MCP Tool | 五个日课每一步都落在官方能力上，不是空壳叙事 |
| **13 个** | 五大日课编排的官方 Tool 总数 | 9 个 CLI 直调 + 4 个由 AI 客户端按需追加 |
| **87 个** | 单份早餐套餐的定制项 | 核销路径能精确到「去冰、多吉士」这一级 |

完整原始输出与逐条出处见 [`docs/demo.md`](docs/demo.md)。

## 🏅 奉献阶位

奉献值 = Σ订单金额 × 10 + 订单数 × 50（只用 `order-list` 的真实金额与笔数，不估不猜）。

| 徽章 | 等级 | 奉献值 | 这一级的信徒 |
|:----:|------|--------|-------------|
| <img src="assets/badge-1-catechumen.webp" width="44" alt="望教者徽章：盾形徽记，素面尖拱下立一支细长点燃的蜡烛"> | 望教者 | < 200 | 刚推开堂门，连券都还没领全 |
| <img src="assets/badge-2-acolyte.webp" width="44" alt="麦门侍者徽章：盾形徽记，一只小奉献盘，身后立一支高烛，上方一道素面尖拱"> | 麦门侍者 | 200 ~ 999 | 晨祷开始不辍，券包渐厚 |
| <img src="assets/badge-3-knight.webp" width="44" alt="薯条骑士徽章：盾形徽记，两支交叉的细金杖，上方一道小尖拱，下方一排三点"> | 薯条骑士 | 1000 ~ 4999 | 有常驻堂区、有忠诚圣物（本仓库作者：奉献值 2709） |
| <img src="assets/badge-4-bishop.webp" width="44" alt="巨无霸主教徽章：盾形徽记，三层圆盘叠成塔状，顶部一道高冠形尖拱，两侧各一座细尖塔"> | 巨无霸主教 | 5000 ~ 19999 | 积分与券从不过期，守夜无从下手 |
| <img src="assets/badge-5-highpriest.webp" width="44" alt="麦门大祭司徽章：盾形徽记，放射光芒的日轮居于圆形玫瑰窗之上，两侧双尖拱相夹，繁复哥特石棱花边，全套最华丽"> | 麦门大祭司 | ≥ 20000 | 麦门永存的具身证明 |

## 🎯 目标用户

- **麦门信徒**：梗玩了三年，终于有个地方能正经地玩——每天一次有日课感的打开。
- **券与积分常年过期的会员**：不想记有效期，只想被人按时叫醒。大教堂每天替你巡检、临期标红、给核销路径。
- **想看 MCP Skill 工程范式的开发者**：一套 `SKILL.md` 提示词编排 + 一套零依赖确定性实现 + golden 基线测试，可以直接抄走当模板。
- **大赛评委**：`--demo` 一条命令，无需 Token、无需装包，30 秒看完五个日课的真实版面。

## 🕯️ 为什么是大教堂

- **别人做计算器，我们做教堂。** 优惠计算是工具，用完即走；大教堂是场景，每天都要来一次。
- **表面是玄学，内核是资产管理。** 积分和券每天都在静默贬值（本仓库作者实测已有 1572.8 积分已经熄灭），大教堂的工作是每天替你抢救。
- **梗是皮，数据是骨。** 所有「神谕」都来自真实 MCP 返回，每条结论可溯源到具体 Tool；营养库匹配不到就直说「此物灯油未载入典籍」，宁缺毋错。

## 🚀 安装与快速开始

### 方式一：WorkBuddy / 任意 MCP 客户端（推荐）

1. **申请 MCP Token**：访问 [麦当劳 MCP 开放平台](https://open.mcd.cn/mcp)，手机号登录 → 控制台 → 激活，获得你的 Token。
2. **配置 MCP 连接器**：把下方 JSON 填进客户端的 MCP 配置，Token 用环境变量注入，不要写死在文件里。

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

3. **把本仓库装成你的 Skill**：WorkBuddy 放入 `~/.workbuddy/skills/` 后重启；其他客户端把 `SKILL.md` 的内容粘进 Agent 系统提示词。
4. **对你的 AI 说**：「阿门麦门永存」—— 晨祷开始。

### 方式二：零依赖命令行（评委直测用）

```bash
export MCD_MCP_TOKEN="你的 Token"        # Windows PowerShell: $env:MCD_MCP_TOKEN="你的 Token"
python cli/cathedral.py matins     # 晨祷：今日日签
python cli/cathedral.py grace      # 领恩：一键领券
python cli/cathedral.py relics     # 圣物盘点：资产巡检
python cli/cathedral.py vigil      # 守夜：临期资产抢救
python cli/cathedral.py ledger     # 奉献录：订单考古
```

选项：

| 选项 | 说明 |
|------|------|
| `--demo` | 离线演示：读 `cli/fixtures.py` 里的 2026-10-10 实测快照，不发任何网络请求、不需要 Token，输出顶部有 DEMO 诚信横幅 |
| `--no-color` | 关闭颜色。重定向到文件、管道，或设了 `NO_COLOR` 环境变量时会自动关闭 |
| `-h` / `--help` | 显示日课与选项清单 |

仅用 Python 标准库（`urllib`），无第三方依赖，无需 `requirements.txt`，Python 3.8+ 即可运行。终端编码与 Windows 颜色支持由 `cli/ui.py` 自举，不需要你导出任何编码环境变量。

**依赖口径**：运行时零依赖覆盖的是 `cli/` —— 纯 Python 标准库，Python 3.8+，跑任何日课都不需要装任何东西。README 里的插图是预先生成好的资产，已提交在 `assets/` 下；生成它们的 [`tools/gen_assets.py`](tools/gen_assets.py) 是**构建期工具**，额外需要 Pillow 和一个图像生成网关的凭证（凭证只从环境变量读取，仓库零凭证），`cli/` 与 `tests/` 永不 import 它，使用者和评委都不需要运行它。

## 💬 使用示例

在 MCP 客户端里：

```
信徒：阿门，麦门永存
司钟人：（晨祷 → 5 条今日布告、可领恩惠 0 张、箴言一句「麦门信众，天下一家。」）

信徒：盘点圣物
司钟人：（27 张在持、12 张七日内临期并排出倒计时，1572.8 已熄灭积分另立安息名录碑）

信徒：守夜
司钟人：（逐张给核销路径；任何金额必先经 calculate-price 核价，核不到就只给方向）

信徒：翻奉献录
司钟人：（10 次朝圣、累计奉献 220.9 元、常驻南京徐庄路快捷小站，落款【薯条骑士 · 奉献值 2709】）
```

无 Token 直测：

```bash
python cli/cathedral.py --demo matins
python cli/cathedral.py --demo relics
python cli/cathedral.py --demo vigil
```

## 🏗️ 架构

```
mcd-monastery/              # 仓库名沿用报名时登记的地址，展示名为「麦门大教堂」
├── SKILL.md                # Skill 定义：五大日课的编排逻辑（AI 读这个）
├── README.md               # 你正在看的文件
├── CONTEST_DECLARATION.md  # 参赛声明（官方要求，内容不可改）
├── MCP_INTEGRATION.md      # MCP 集成说明：Server、13 个 Tool（9 直调 + 4 编排）、调用流程
├── mcp-config.example.json # 脱敏配置示例（Token 只走环境变量占位符）
├── assets/                 # 视觉资产（已生成并提交，使用者无需生成）
│   ├── hero.webp           # 首屏门面通栏横幅：满宽自适应，README 里不写固定宽度
│   │                       # （AI 生成，图内零文字）
│   ├── ritual-*.webp       # 五日课圆徽 360×360，细金环框、环外透明（AI 生成，图内零文字）
│   ├── badge-*.webp        # 五级阶位盾徽 200×200，盾外透明（AI 生成，图内零文字）
│   ├── og-card.png         # Social preview 卡 1280×640：AI 背景 + 本机 CJK 字体渲染的
│   │                       # 标题文字（矢量字形，边缘清晰），唯一带字的资产；
│   │                       # 在仓库设置里上传，不嵌 README
│   └── og-bg.webp          # og-card 的无字背景版（备用）
├── cli/
│   ├── cathedral.py        # 零依赖 CLI：MCP 取数 + 五日课编排（取数与渲染分层）
│   ├── ui.py               # 版面地基：中文显示宽度、框线组件、配色降级、条形图
│   └── fixtures.py         # --demo 离线快照：2026-10-10 实测原始数据与冻结时钟
├── tools/
│   └── gen_assets.py       # 构建期资产生成器：需 Pillow + 图像生成网关凭证；
│                           # cli/ 与 tests/ 永不 import 它，使用者无需运行
├── docs/
│   └── demo.md             # 端到端实测记录（本 README 的数据出处）
└── tests/
    ├── test_align.py       # golden 回归：版式对齐 + 数值与 docs/demo.md 逐条一致
    ├── test_ui.py          # 宽度地基、净化层与框线组件单测（超宽截断绝不破框）
    ├── test_color.py       # 颜色降级：--no-color / NO_COLOR / 非 TTY 均无转义码残留
    ├── test_compat.py      # Python 3.8 兼容扫描（ast 扫 3.9+ 构造）
    ├── test_parsers.py     # 锁住 MCP 返回解析行为
    ├── test_throttle.py    # 限流节流与失败路径
    ├── test_errors.py      # 三条错误路径：缺凭证 / 凭证无效 / 网络不可达 → 面板 + exit 1
    ├── test_render_branches.py
    │                       # 快照取零值的那些分支（kcal>0 / 积分兑换 / 下月熄灭）的覆盖
    ├── test_assets.py      # 资产引用机械校验：路径真实存在 / 每个 img 有 alt /
    │                       # 无孤儿资产 / 十枚徽记带 alpha 透明底
    └── golden/             # 五日课 --demo 输出基线，README 与 demo.md 的输出块来源
```

跑测试（无需任何依赖，标准库 unittest）：

```bash
python -m unittest discover -s tests -t tests
```

`-t tests` 不能省：`tests/` 不是 Python 包（没有 `__init__.py`），写成 `-t .` 会直接 ImportError。当前 193 个用例全绿。

**设计哲学**：Skill 即提示词编排。`SKILL.md` 是「大教堂会规」，教任何 MCP 客户端里的 AI 如何主持日课；`cli/cathedral.py` 是同一套日课的确定性实现，没有 AI 也能跑，保证可评审、可回归。版面只有一个出口（`cli/ui.py`），所以 README、`docs/demo.md` 和 `tests/golden/` 里看到的框线是同一套代码画出来的——文档里的输出块一律从 golden 复制，不手写。

## 📎 实测数据

2026-10-10 用真实 Token 跑完五个日课的完整原始输出、三个关键数据发现、13 行工具调用全景表与结论，全部记在 [`docs/demo.md`](docs/demo.md)。README 里出现的每个数字都能在那里找到出处。

## 🙏 合规声明

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，**非麦当劳官方产品**。梗文化仅是叙事外壳，所有数据与交易能力均来自[麦当劳中国官方 MCP 服务](https://open.mcd.cn/mcp)；项目不调用任何支付类工具，不下单、不代付。

- 参赛声明（原创性、合规、信息安全、使用提示）：[`CONTEST_DECLARATION.md`](CONTEST_DECLARATION.md)
- MCP 集成细节与工程约束（Token 只走环境变量、限流节流、只读为主）：[`MCP_INTEGRATION.md`](MCP_INTEGRATION.md)
- 视觉资产（门面横幅、五日课圆徽、五级阶位盾徽）由 AI 图像模型生成，统一金／绛红／米白三色与石质肌理；这 11 张内嵌 README 的图**图内零文字、零字母、零商标**。唯一的例外是不嵌 README、只用于仓库 Social preview 的 `og-card.png`：它的标题文字（「麦门大教堂 / MCD CATHEDRAL / 每天 30 秒，替你抢救正在过期的券和积分」）不是模型画的，而是构建脚本用本机 CJK 字体（TrueType）渲染合成的，所以边缘是矢量字形级的清晰。全部资产均不含任何麦当劳商标或官方视觉元素，生成脚本见 [`tools/gen_assets.py`](tools/gen_assets.py)。badge 与插图沿用公开品牌配色，仅为视觉呼应；本项目非麦当劳官方产品，与麦当劳不存在隶属、赞助或背书关系，资产内不含任何商标、标识或官方视觉元素。

> I'm loving it. 🍟
