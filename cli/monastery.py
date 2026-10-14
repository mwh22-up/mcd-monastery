#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门修道院 · 零依赖 CLI
五大仪式的确定性实现。仅用 Python 标准库，3.8+ 可跑。

用法：
  export MCD_MCP_TOKEN="你的token"
  python monastery.py morning     # 晨课：今日日签
  python monastery.py blessing    # 领福：一键领券
  python monastery.py inventory   # 圣物盘点：资产巡检
  python monastery.py transcend   # 超度：临期资产抢救
  python monastery.py merit       # 功德簿：订单考古

选项：
  --demo      离线演示模式：读 cli/fixtures.py 的 2026-10-10 实测快照，
              不发任何网络请求、不需要 Token，输出顶部有 DEMO 诚信横幅
  --no-color  关闭颜色（重定向与 NO_COLOR 环境变量下会自动关闭）
  -h/--help   显示用法

版面一律由 cli/ui.py 渲染：本文件不许出现 print，输出只走 ui.out()。
取数与渲染分层：fetch_*() 负责 MCP 调用与解析，render_*() 只负责版面，
--demo 只替换 fetch 层，渲染路径与真实模式完全同一条。
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta

import fixtures
import ui

URL = "https://mcp.mcd.cn"
VERSES = [
    "薯条所至，皆为圣土。",
    "巨无霸三层，人生三重境界。",
    "早课不辍，功德自增。",
    "可乐去冰，心静自然凉。",
    "麦门信众，天下一家。",
]
LEVELS = [
    (200, "见习麦门徒"),
    (1000, "麦门侍僧"),
    (5000, "薯条骑士"),
    (20000, "巨无霸主教"),
    (float("inf"), "麦门大祭司"),
]
WEEKDAYS = "一二三四五六日"      # D10：%A 随 locale 变（实测本机输出 Saturday），自维护中文表
EXPIRE_SCALE = 7                 # 倒计时条的刻度：七日内魂飞魄散
NAME_W = 24                      # 倒计时条里券名占的列数
BAR_W = 10                       # 条形图长度
THROTTLE_S = 0.2                 # MCP_INTEGRATION.md §5：连续调用间隔 ≥200ms

_FROZEN = None       # --demo 的冻结时钟；None 表示用真实时间
_DEMO = False        # --demo 开关
_last_call_at = 0.0  # 上一次 MCP 调用的时间戳，用于节流


def now():
    """当前时间。--demo 下返回快照的冻结时钟，使「剩 N 天」可复现。"""
    return _FROZEN or datetime.now()


def is_demo():
    return _DEMO


# ─────────────────────────── MCP 层（调用与解析，内容不动） ───────────────────────────

def call(tool, args=None):
    global _last_call_at
    gap = THROTTLE_S - (time.time() - _last_call_at)
    if gap > 0:
        time.sleep(gap)      # 相邻两次 HTTP 之间补足 200ms，只补间隔不改请求
    token = os.environ.get("MCD_MCP_TOKEN", "")
    if not token:
        ui.out(ui.panel("缺少凭证", ["先设环境变量 MCD_MCP_TOKEN（open.mcd.cn/mcp 申请）"], ui.C.RED))
        sys.exit(1)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args or {}},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
    finally:
        # 失败也记账：fetch_* 会吞掉异常继续调下一个 tool，时间戳不更新会让它零间隔发出
        _last_call_at = time.time()
    if raw.startswith("data:"):
        for line in raw.split("\n"):
            if line.startswith("data:"):
                raw = line[5:].strip()
                break
    resp = json.loads(raw)
    content = resp.get("result", {}).get("content", [])
    text = content[0]["text"] if content else ""
    return extract_json(text), text


def extract_json(text):
    """从工具返回的文本中尽力抽取第一个 JSON 对象。"""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                if isinstance(obj, dict) and ("success" in obj or "data" in obj or "code" in obj):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def parse_date(s):
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s.strip()[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def parse_coupons_md(text):
    """从 query-my-coupons 的 Markdown 返回中解析券列表。"""
    coupons = []
    total = 0
    m = re.search(r"共\s*(\d+)\s*张可用优惠券", text)
    if m:
        total = int(m.group(1))
    # 每张券：## {标题} + **有效期**: ...
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        title = block.split("\n")[0].strip()
        m2 = re.search(r"\*\*有效期\*\*:\s*(\S+)\s*(\d{2}:\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", block)
        end = None
        if m2:
            end = parse_date(m2.group(3))
        elif m2 is None:
            m3 = re.search(r"\*\*有效期\*\*:\s*([0-9\-]+)", block)
            if m3:
                end = parse_date(m3.group(1))
        coupons.append({"title": title, "end": end})
    return total, coupons


def get_expiring_coupons():
    """拉券包并筛出 7 天内临期的券。"""
    obj, text = call("query-my-coupons")
    at = now()
    total, coupons = parse_coupons_md(text)
    expiring = []
    for c in coupons:
        if c["end"] and (c["end"] - at) <= timedelta(days=7):
            expiring.append((c["title"], c["end"]))
    return total, expiring


# ─────────────────────────── 版面小件 ───────────────────────────

def _weekday(at):
    return "星期" + WEEKDAYS[at.weekday()]


def _date_label(at):
    return "%s %s" % (at.strftime("%Y-%m-%d"), _weekday(at))


def _closing(text):
    """框外收尾句：细线分隔 + 居中金色法号。"""
    return ui.divider() + [ui.pad(ui.C.paint(text, ui.C.GOLD), ui.CARD_W, "center")]


def _days_left(end):
    return max((end - now()).days, 0)


def _days_color(days):
    """0-1 天红、2-3 天金、其余暗灰。"""
    if days <= 1:
        return ui.C.RED
    if days <= 3:
        return ui.C.GOLD
    return ui.C.DIM


def _by_days(expiring):
    """按剩余天数升序（剩得少的在最上），同一天保持上游顺序。"""
    at = now()
    return sorted(expiring, key=lambda it: (it[1] - at).days)


def _countdown_rows(expiring):
    """临期倒计时条：券名 + 七日刻度条 + 剩余天数。inventory 与 transcend 共用。"""
    rows = []
    for title, end in _by_days(expiring):
        days = _days_left(end)
        rows.append(ui.pad(ui.trunc(ui.safe_text(title), NAME_W), NAME_W)
                    + " " + ui.bar(days, EXPIRE_SCALE, BAR_W, _days_color(days))
                    + " " + ui.pad("剩 %d 天" % days, 8, "right"))
    return rows


def _demo_coupons():
    """demo 旁路：快照里的到期日字符串转成 datetime，结构与真实分支完全一致。"""
    snap = fixtures.SNAPSHOT
    expiring = [(title, datetime.strptime(day, "%Y-%m-%d"))
                for title, day in snap["coupons"]["expiring"]]
    return {"total": snap["coupons"]["total"],
            "expiring": expiring,
            "account": dict(snap["account"])}


# ─────────────────────────── 仪式一：晨课 ───────────────────────────

def fetch_morning():
    if is_demo():
        snap = fixtures.SNAPSHOT["morning"]
        return {"campaigns": list(snap["campaigns"]), "campaigns_err": None,
                "available": snap["available"], "available_err": None}
    obj, _ = call("now-time-info")
    campaigns = []
    campaigns_err = None
    try:
        obj, text = call("campaign-calendar")
        shown = 0
        # campaign-calendar 返回 Markdown 文本，从标题行提取
        for m in re.finditer(r"\*\*活动标题\*\*：(.+)", text):
            title = m.group(1).strip()
            if title:
                campaigns.append(title)
                shown += 1
                if shown >= 5:
                    break
    except Exception as e:
        campaigns_err = "%s" % e
    available = 0
    available_err = None
    try:
        obj, text = call("available-coupons")
        n = 0
        if obj and obj.get("data"):
            items = obj["data"] if isinstance(obj["data"], list) else obj["data"].get("list", [])
            n = len(items)
        if n == 0:
            # 返回可能是 Markdown 文本，数券标题行
            n = len(re.findall(r"\*\*券名\*\*|\*\*优惠券\*\*|- \*\*", text))
        available = n
    except Exception as e:
        available_err = "%s" % e
    return {"campaigns": campaigns, "campaigns_err": campaigns_err,
            "available": available, "available_err": available_err}


def render_morning(data):
    at = now()
    lines = ui.plaque("麦门修道院 · 晨课", _date_label(at))
    lines += ui.panel("今日箴言", [VERSES[at.toordinal() % len(VERSES)]])
    if data["campaigns_err"]:
        chance = ["（活动日历读取失败：%s）" % data["campaigns_err"]]
    elif data["campaigns"]:
        chance = ui.bullet([ui.safe_text(t) for t in data["campaigns"]])
    else:
        chance = ["（经卷暂无记载，施主可自行参悟）"]
    lines += ui.panel("今日机缘", chance)
    if data["available_err"]:
        fortune = ["（福报读取失败：%s）" % data["available_err"]]
    elif data["available"]:
        fortune = ["麦麦省现有 %d 张福报可领，诵「领福」即刻领取。" % data["available"]]
    else:
        fortune = ["施主福缘已满，今日无可领之福。"]
    lines += ui.panel("可领福报", fortune)
    return lines + _closing("阿弥陀佛，麦门永存。")


def morning():
    ui.out(render_morning(fetch_morning()))


# ─────────────────────────── 仪式二：领福 ───────────────────────────

def fetch_blessing():
    if is_demo():
        return {"text": fixtures.SNAPSHOT["blessing"]["text"]}
    obj, text = call("auto-bind-coupons")
    return {"text": text}


def render_blessing(data):
    text = data["text"]
    rows = ["僧众正在替施主领取福报……"]
    # auto-bind-coupons 返回 Markdown 文本
    if "领券成功" in text or "成功" in text:
        m = re.search(r"(\d+)\s*张", text)
        n = m.group(1) if m else "?"
        rows.append("阿弥陀佛，今日领得 %s 张福报，功德 +%s。" % (n, n))
        mark = "【今日功德 +%s】" % n
    else:
        rows.append("施主福缘已满，今日无可领之福。明日再来。")
        mark = "【福缘已满】"
    lines = ui.plaque("麦门修道院 · 领福", _date_label(now()))
    lines += ui.panel("领福结果", rows)
    return lines + _closing("麦门永存。") + ui.seal(mark)


def blessing():
    ui.out(render_blessing(fetch_blessing()))


# ─────────────────────────── 仪式三：圣物盘点 ───────────────────────────

def fetch_inventory():
    if is_demo():
        return _demo_coupons()
    total, expiring = get_expiring_coupons()
    obj, _ = call("query-my-account")
    account = obj["data"] if (obj and obj.get("data")) else None
    return {"total": total, "expiring": expiring, "account": account}


def render_inventory(data):
    at = now()
    total = data["total"]
    expiring = data["expiring"]
    account = data["account"]
    lines = ui.plaque("圣物盘点", _date_label(at))
    if total:
        held = "在持 %d 张" % total
        if expiring:
            held += "，其中 %d 张七日内魂飞魄散" % len(expiring)
        lines += ui.panel("优惠券", [held + "。"])
    else:
        lines += ui.panel("优惠券", ["施主暂无在持之券。"])
    if expiring:
        lines += ui.panel("临期倒计时 · 七日内魂飞魄散", _countdown_rows(expiring))
    else:
        lines += ui.panel("临期倒计时", ["券包安好，无需超度。"])
    grave = []
    if account:
        rows = [("可用", "%s 分" % account.get("availablePoint")),
                ("累计", "%s 分" % account.get("accumulativePoint"))]
        nx = account.get("nextMouthExpirePoint") or "0"
        if float(nx or 0) > 0:
            rows.append(("下月圆寂", "%s 分（建议诵「超度」）" % nx))
        lines += ui.panel("积分", ui.kv_table(rows))
        expired = account.get("expiredPoint") or "0"
        if float(expired or 0) > 0:
            grave = ui.tomb(["往 生 功 德 碑", "%s 积分" % expired, "卒于无人问津之日"],
                            epitaph="超度来晚了，便是来迟了一生。")
    else:
        lines += ui.panel("积分", ["（积分账户读取失败）"])
    if grave:
        lines += ui.blank() + grave
    if expiring:
        lines += _closing("施主，建议尽快「超度」。阿弥陀佛。")
    else:
        lines += _closing("阿弥陀佛，麦门永存。")
    return lines + ui.seal("【圣物 %d · 临期 %d】" % (total, len(expiring)))


def inventory():
    ui.out(render_inventory(fetch_inventory()))


# ─────────────────────────── 仪式四：超度 ───────────────────────────

def fetch_transcend():
    if is_demo():
        data = _demo_coupons()
        data["points_products"] = fixtures.SNAPSHOT["points_products"]
        data["points_err"] = None
        return data
    total, expiring = get_expiring_coupons()
    obj, _ = call("query-my-account")
    account = obj["data"] if (obj and obj.get("data")) else None
    points_products = None
    points_err = None
    if account:
        nx = account.get("nextMouthExpirePoint") or "0"
        if float(nx or 0) > 0:
            # 门槛不变：只有下月确有圆寂积分才去问积分商城
            try:
                pobj, _ = call("mall-points-products")
                points_products = pobj
            except Exception as e:
                points_err = "%s" % e
    return {"total": total, "expiring": expiring, "account": account,
            "points_products": points_products, "points_err": points_err}


def render_transcend(data):
    expiring = data["expiring"]
    lines = ui.plaque("超度仪式", _date_label(now()))
    if not expiring:
        lines += ui.panel("临期券抢救", ["施主券包安好，无临期之危。"])
    else:
        for (title, end), row in zip(_by_days(expiring), _countdown_rows(expiring)):
            days = _days_left(end)
            lines += ui.panel("%s · %s 魂飞魄散" % (ui.safe_text(title), end.strftime("%m-%d")),
                              [row,
                               "核销路径：请尽快到店使用；点餐时可让 AI 助手经",
                               "query-meals + calculate-price 核价后给出最优组合。"],
                              _days_color(days))
    account = data["account"] or {}
    nx = account.get("nextMouthExpirePoint") or "0"
    if float(nx or 0) > 0:
        rows = ["下月圆寂 %s 分。" % nx]
        if data["points_err"]:
            rows.append("（商城读取失败：%s）" % data["points_err"])
        else:
            pobj = data["points_products"]
            if pobj and pobj.get("data"):
                items = pobj["data"].get("items", [])
                best = None
                for it in items:
                    pt = float(it.get("point") or 0)
                    if 0 < pt <= float(nx):
                        if best is None or pt > float(best.get("point") or 0):
                            best = it
                if best:
                    rows.append("兑换建议：%s（%s 分）" % (best.get("spuName"), best.get("point")))
                else:
                    rows.append("积分商城暂无合适兑换品，施主可自行长老殿参详。")
        lines += ui.panel("积分超度", rows)
    return lines + _closing("阿弥陀佛，趁早超度，功德无量。")


def transcend():
    ui.out(render_transcend(fetch_transcend()))


# ─────────────────────────── 仪式五：功德簿 ───────────────────────────

def fetch_merit():
    if is_demo():
        snap = fixtures.SNAPSHOT["merit"]
        return {"order_count": snap["order_count"], "total_amount": snap["total_amount"],
                "top_store": snap["top_store"], "top_items": list(snap["top_items"]),
                "kcal": snap["kcal"]}
    obj, _ = call("order-list")
    orders = []
    if obj and obj.get("data"):
        orders = obj["data"].get("list", [])
    if not orders:
        return {"order_count": 0, "total_amount": 0.0, "top_store": None,
                "top_items": [], "kcal": 0.0}
    total_amt = 0.0
    store_count = {}
    item_count = {}
    kcal = 0.0
    # 营养库
    nobj, _ = call("list-nutrition-foods")
    nutrition = {}
    if nobj and nobj.get("data") and isinstance(nobj["data"], str):
        # toon 紧凑格式：首行为表头，其后每行一个餐品
        lines = nobj["data"].split("\n")
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                nutrition[parts[0].strip()] = parts[3].strip()
    for o in orders:
        try:
            total_amt += float(o.get("realTotalAmount") or 0)
        except (TypeError, ValueError):
            pass
        sn = o.get("storeName") or "未知道场"
        store_count[sn] = store_count.get(sn, 0) + 1
        for p in o.get("orderProductList") or []:
            name = p.get("productName") or ""
            qty = p.get("quantity") or 1
            item_count[name] = item_count.get(name, 0) + qty
            if name in nutrition:
                try:
                    kcal += float(nutrition[name]) * qty
                except (TypeError, ValueError):
                    pass
    top_store = max(store_count.items(), key=lambda kv: kv[1]) if store_count else None
    top_items = sorted(item_count.items(), key=lambda kv: -kv[1])[:3]
    return {"order_count": len(orders), "total_amount": total_amt,
            "top_store": top_store, "top_items": top_items, "kcal": kcal}


def render_merit(data):
    count = data["order_count"]
    lines = ui.plaque("功德簿", "施主的麦门修行")
    if not count:
        return (lines + ui.panel("功德", ["施主的功德簿尚是白卷。快去朝圣吧。阿弥陀佛。"])
                + _closing("阿弥陀佛，麦门永存。"))
    total_amt = data["total_amount"]
    merit_val = int(total_amt * 10 + count * 50)
    level = LEVELS[0][1]
    for threshold, label in LEVELS:
        if merit_val < threshold:
            level = label
            break
    else:
        level = LEVELS[-1][1]
    rows = [("修行等级", "%s（功德 %d 点）" % (level, merit_val)),
            ("修行足迹", "%d 次朝圣，累计布施 %.1f 元" % (count, total_amt))]
    if data["top_store"]:
        rows.append(("常驻道场", "%s（%d 次）" % data["top_store"]))
    lines += ui.panel("修行档案", ui.kv_table(rows))   # 与 inventory 的积分表同一口径：键值表一律进框
    top_items = data["top_items"]
    if top_items:
        top_qty = max(qty for _, qty in top_items)
        relics = []
        for name, qty in top_items:
            relics.append(ui.pad(ui.trunc(ui.safe_text(name), 28), 28)
                          + " " + ui.bar(qty, top_qty, BAR_W, ui.C.GOLD)
                          + " " + ui.pad("×%d" % qty, 5, "right"))
        lines += ui.panel("忠诚圣物", relics)
    kcal = data["kcal"]
    if kcal > 0:
        lines += ui.panel("累计火候", ["约 %.0f kcal（≈ %.1f 个巨无霸）" % (kcal, kcal / 513)])
    lines += _closing("阿弥陀佛，麦门永存。")
    return lines + ui.seal("【%s · 功德 %d】" % (level, merit_val))


def merit():
    ui.out(render_merit(fetch_merit()))


COMMANDS = {
    "morning": morning,
    "blessing": blessing,
    "inventory": inventory,
    "transcend": transcend,
    "merit": merit,
}

RITUALS = (
    ("morning", "晨课 · 今日日签与机缘"),
    ("blessing", "领福 · 一键领取可领之券"),
    ("inventory", "圣物盘点 · 券与积分巡检"),
    ("transcend", "超度 · 临期资产抢救"),
    ("merit", "功德簿 · 订单考古与段位"),
)
DEMO_BANNER = ("演示模式 · DEMO", "数据为 2026-10-10 09:26 真实实测快照，非实时查询")


def render_usage():
    rows = [ui.pad(ui.C.paint(name, ui.C.GOLD), 11) + desc for name, desc in RITUALS]
    return (ui.plaque("麦门修道院 · 五大仪式", "python cli/monastery.py <仪式> [选项]")
            + ui.panel("仪式", rows)
            + ui.panel("选项", [ui.pad("--demo", 11) + "离线演示，用实测快照，无需 Token",
                                ui.pad("--no-color", 11) + "关闭颜色",
                                ui.pad("-h/--help", 11) + "显示本用法"])
            + ui.panel("凭证", ["环境变量 MCD_MCP_TOKEN（open.mcd.cn/mcp 申请）",
                                "没有 Token 也能看：python cli/monastery.py --demo inventory"])
            + _closing("阿弥陀佛，麦门永存。"))


def main(argv):
    """手写参数解析：argparse 会自己 print，绕过 ui 的唯一出口。"""
    global _DEMO, _FROZEN
    cmd = ""
    demo = False
    no_color = False
    want_help = False
    bad = None
    for arg in argv:
        if arg in ("-h", "--help"):
            want_help = True
        elif arg == "--demo":
            demo = True
        elif arg == "--no-color":
            no_color = True
        elif arg.startswith("-"):
            bad = arg
            break
        elif not cmd:
            cmd = arg
    ui.init(no_color=no_color)
    if bad is not None:
        ui.out(ui.banner("无法辨识的选项", ui.safe_text(bad)), ui.blank(), render_usage())
        return 2
    if want_help or not cmd:
        ui.out(render_usage())
        return 0
    if cmd not in COMMANDS:
        ui.out(ui.banner("查无此仪式", ui.safe_text(cmd)), ui.blank(), render_usage())
        return 1
    if demo:
        _DEMO = True
        _FROZEN = fixtures.SNAPSHOT["now"]
        ui.out(ui.banner(DEMO_BANNER[0], DEMO_BANNER[1]), ui.blank())
    COMMANDS[cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
