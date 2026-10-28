# 麦门大教堂 · MCP 集成说明

本文档说明本项目实际使用的麦当劳 MCP Server、Tool、调用流程和业务价值。

## 1. 使用的 MCP Server

| 项目 | 说明 |
|------|------|
| Server | 麦当劳中国官方 MCP Server（远程托管） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 控制台激活 |
| 协议版本 | MCP 2025-06-18 |

配置示例见 [`mcp-config.example.json`](mcp-config.example.json)，Token 一律通过环境变量 `MCD_MCP_TOKEN` 注入，仓库不含任何真实凭证。

## 2. 使用的 Tool 清单

五大日课共编排 13 个官方 Tool：CLI 确定性实现直接调用 9 个，另 4 个由 `SKILL.md` 编排、AI 客户端按需追加。

#### CLI 确定性实现实际调用（9 个）

| # | Tool | 用途（本项目场景） | 日课 | 调用点 |
|---|------|------------------|------|-------|
| 1 | `now-time-info` | 服务器时间锚点 | 晨祷 | `fetch_matins()` |
| 2 | `campaign-calendar` | 当月营销活动 → 「今日布告」 | 晨祷 | `fetch_matins()` |
| 3 | `available-coupons` | 麦麦省可领券 → 「可领恩惠」 | 晨祷 | `fetch_matins()` |
| 4 | `auto-bind-coupons` | 一键领取全部可领券 | 领恩 | `fetch_grace()` |
| 5 | `query-my-coupons` | 券包全量巡检（含有效期） | 圣物盘点 / 守夜 | `get_expiring_coupons()` |
| 6 | `query-my-account` | 积分账户（可用/累计/已过期） | 圣物盘点 / 守夜 | `fetch_relics()` / `fetch_vigil()` |
| 7 | `mall-points-products` | 积分兑换建议（仅当下月有临期积分） | 守夜 | `fetch_vigil()`（仅当 `nextMouthExpirePoint > 0`） |
| 8 | `order-list` | 历史订单全量 → 奉献录考古 | 奉献录 | `fetch_ledger()` |
| 9 | `list-nutrition-foods` | 160 项营养库 → 热量结算 | 奉献录 | `fetch_ledger()` |

第 5 列写函数名而不是行号：行号会随代码演进漂移，而这张表要逐字对得上源码。

#### `SKILL.md` 编排、由 AI 客户端按需追加（4 个）

`cli/` 不调用这 4 个；grep 源码查不到是预期的。

| # | Tool | 用途（本项目场景） | 触发条件 |
|---|------|------------------|---------|
| 10 | `query-nearby-stores` | 按城市+关键词定位门店 | 用户提供了城市/位置 |
| 11 | `query-meals` | 门店在售菜单 | 需要找可核销餐品 |
| 12 | `query-meal-detail` | 套餐特调轮次与定制项 | 需要精确到去冰/多吉士 |
| 13 | `calculate-price` | 组合权威核价 | 要输出任何金额之前 |

## 3. 调用流程

### 3.1 晨祷（每日日签）

```
now-time-info ──→ campaign-calendar ──→ available-coupons
                                          │
                                          ▼
                              生成日签卡片（今日布告 + 可领恩惠 + 箴言）
```

- `campaign-calendar` 返回当月活动的 Markdown 文本，脚本用正则抓 `**活动标题**：` 行，**取前 5 条**进日签。没有做日期过滤——上游返回的就是进行中的活动，`dateText` 字段本项目不使用；
- `available-coupons` 返回可领券，数量进日签，正文提示用户诵「领恩」触发自动领取；
- 三路各自独立容错：`now-time-info` 失败时时间锚点退回本机时间，另两路任一失败只影响对应的框，两路业务取数全部失败时降级为纯箴言日签（无数据也不空手）。

### 3.2 领恩（自动领券）

```
auto-bind-coupons ──→ 返回实领数量 ──→ 奉献值结算
```

- 幂等：当天已领则返回 0，脚本不重复刷；
- 奉献值不落盘：`领恩` 只把本次实领数拼进落款，`奉献录` 的奉献值每次由 `order-list` 现算。整个 CLI 不写任何文件、不留任何痕迹。

### 3.3 圣物盘点（资产巡检）

```
query-my-coupons ─┐
                  ├──→ 资产总览：券 N 张（X 张临期）+ 积分 M 分
query-my-account ─┘
```

- 券临期判定：从 `query-my-coupons` 返回的 Markdown 里解析 `**有效期**: MM-DD HH:MM - YYYY-MM-DD` 的尾部日期，距今 ≤ 7 天 → 标红。这是文本解析而非结构化字段，上游改排版会失效——`tests/test_parsers.py` 用固定样本锁住了解析行为；
- 积分临期判定：`nextMouthExpirePoint` > 0 → 预警；
- 已过期积分（`expiredPoint`）进入"安息名录"统计——提醒用户守夜要趁早。

### 3.4 守夜日课（临期资产抢救）

```
query-my-coupons ──→ 筛出 7 天内过期券
query-my-account ──→ 筛出下月过期积分
        │
        ▼
query-nearby-stores（可选，用户给城市时定位门店）
query-meals → query-meal-detail（找出能核销该券的餐品与定制组合）
calculate-price（权威核价，绝不猜价格）
        │
        ▼
守夜方案：「券 X 明晚过期 → 到店点 Y 套餐 + 去冰多吉士 → 实付 Z 元，立省 W 元」
```

- 核销路径必须经 `calculate-price` 核价后才输出——这是本项目对"绝不猜价格"的工程承诺。`cli/` 不输出任何金额，所以这条承诺在 CLI 侧是结构性成立的；AI 主持时任何金额必经 `calculate-price`，核不到价就只给方向；
- 积分守夜：调用 `mall-points-products` 找同价位最优兑换品。

### 3.5 奉献录（订单考古）

```
order-list ──→ 逐笔解析（时间/门店/金额/商品）
list-nutrition-foods ──→ 按商品名匹配营养数据
        │
        ▼
奉献值结算：总奉献值、忠诚单品 TOP3、常驻堂区、累计灯油（kcal 热量）
奉献阶位：望教者 → 麦门大祭司（奉献值阈值映射）
```

- 商品名匹配不到营养库时跳过热量统计，不影响其他维度（宁缺毋错）。

## 4. 业务价值

1. **沉默资产激活**：券和积分的过期是纯损失。本项目把"记得用券"从人肉记忆变成每日自动化巡检 + 主动抢救，直接省钱。
2. **非点餐时段的每日心智**：省钱/营养类竞品都在解决"点餐那一刻"的决策，本项目占据的是"每天早上 30 秒"的日课场景——更高频、更轻、更有情感粘性。
3. **梗文化的正外部性**：「麦门」亚文化自带传播势能，但此前的表达只有表情包和语录。本项目给梗一个可交互的载体，同时把流量导向真实的官方交易能力（领券→核销→下单）。
4. **官方叙事协同**：麦当劳 2026 年主推「麦麦 24 节气」会员活动与积分权益闭环，大教堂的奉献值/节气/积分体系与官方叙事同构，是官方会员运营的民间放大器。

## 5. 工程约束与合规

- Token 只从环境变量 `MCD_MCP_TOKEN` 读取，仓库零凭证（符合参赛信息安全要求）；
- 只调用只读查询类 Tool + `auto-bind-coupons`（领券本身幂等且零成本）；**不做下单**——所有需要支付的动作只给路径建议，由用户在官方渠道完成；
- 遵守官方限流（600 次/分钟），脚本内对连续调用做了节流；
- 遵守《麦当劳 MCP 服务规则》与大赛活动规则。
