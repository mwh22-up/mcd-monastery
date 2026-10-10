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
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta

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


def call(tool, args=None):
    token = os.environ.get("MCD_MCP_TOKEN", "")
    if not token:
        print("先设环境变量 MCD_MCP_TOKEN（open.mcd.cn/mcp 申请）")
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
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")
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


def hr(title):
    print()
    print("=" * 46)
    print(" " + title)
    print("=" * 46)


def parse_date(s):
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s.strip()[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


# ─────────────────────────── 仪式一：晨课 ───────────────────────────

def morning():
    obj, _ = call("now-time-info")
    now = datetime.now()
    print()
    print("+" + "-" * 44 + "+")
    print("| 麦门修道院 · 晨课  %s" % now.strftime("%Y-%m-%d %A") + " " * 4 + "|")
    print("+" + "-" * 44 + "+")
    print()
    print("  今日箴言：%s" % VERSES[now.toordinal() % len(VERSES)])
    print()
    print("  【今日机缘】")
    try:
        obj, text = call("campaign-calendar")
        shown = 0
        # campaign-calendar 返回 Markdown 文本，从标题行提取
        for m in re.finditer(r"\*\*活动标题\*\*：(.+)", text):
            title = m.group(1).strip()
            if title:
                print("   - %s" % title)
                shown += 1
                if shown >= 5:
                    break
        if shown == 0:
            print("   （经卷暂无记载，施主可自行参悟）")
    except Exception as e:
        print("   （活动日历读取失败：%s）" % e)
    print()
    print("  【可领福报】")
    try:
        obj, text = call("available-coupons")
        n = 0
        if obj and obj.get("data"):
            items = obj["data"] if isinstance(obj["data"], list) else obj["data"].get("list", [])
            n = len(items)
        if n == 0:
            # 返回可能是 Markdown 文本，数券标题行
            n = len(re.findall(r"\*\*券名\*\*|\*\*优惠券\*\*|- \*\*", text))
        if n:
            print("   麦麦省现有 %d 张福报可领，诵「领福」即刻领取。" % n)
        else:
            print("   施主福缘已满，今日无可领之福。")
    except Exception as e:
        print("   （福报读取失败：%s）" % e)
    print()
    print("  阿弥陀佛，麦门永存。")


# ─────────────────────────── 仪式二：领福 ───────────────────────────

def blessing():
    print()
    print("  僧众正在替施主领取福报……")
    obj, text = call("auto-bind-coupons")
    # auto-bind-coupons 返回 Markdown 文本
    if "领券成功" in text or "成功" in text:
        m = re.search(r"(\d+)\s*张", text)
        n = m.group(1) if m else "?"
        print("  阿弥陀佛，今日领得 %s 张福报，功德 +%s。" % (n, n))
    else:
        print("  施主福缘已满，今日无可领之福。明日再来。")
    print("  麦门永存。")


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
    now = datetime.now()
    total, coupons = parse_coupons_md(text)
    expiring = []
    for c in coupons:
        if c["end"] and (c["end"] - now) <= timedelta(days=7):
            expiring.append((c["title"], c["end"]))
    return total, expiring


# ─────────────────────────── 仪式三：圣物盘点 ───────────────────────────

def inventory():
    hr("圣物盘点 · %s" % datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now()
    # 券
    print()
    print("  【优惠券】")
    total, expiring = get_expiring_coupons()
    if total:
        print("   在持 %s 张。" % total)
    else:
        print("   施主暂无在持之券。")
    if expiring:
        print("   ⚠️ 临期（7 天内魂飞魄散）：")
        for title, end in expiring:
            days = (end - now).days
            print("     - %s（%s，剩 %d 天）" % (title, end.strftime("%m-%d"), max(days, 0)))
    else:
        print("   券包安好，无需超度。")
    # 积分
    print()
    print("  【积分】")
    obj, _ = call("query-my-account")
    if obj and obj.get("data"):
        d = obj["data"]
        print("   可用 %s 分 | 累计 %s 分" % (d.get("availablePoint"), d.get("accumulativePoint")))
        expired = d.get("expiredPoint") or "0"
        if float(expired or 0) > 0:
            print("   ⚰️ 已往生 %s 分（历史损失，引以为戒）" % expired)
        nx = d.get("nextMouthExpirePoint") or "0"
        if float(nx or 0) > 0:
            print("   ⏰ 下月圆寂 %s 分，建议诵「超度」。" % nx)
    else:
        print("   （积分账户读取失败）")
    print()
    if expiring:
        print("  施主，建议尽快「超度」。阿弥陀佛。")
    else:
        print("  阿弥陀佛，麦门永存。")


# ─────────────────────────── 仪式四：超度 ───────────────────────────

def transcend():
    hr("超度仪式 · %s" % datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now()
    total, expiring = get_expiring_coupons()
    print()
    if not expiring:
        print("  施主券包安好，无临期之危。")
    else:
        print("  【临期券抢救】")
        for title, end in expiring:
            days = (end - now).days
            print()
            print("  ⚰️ %s" % title)
            print("     %s 魂飞魄散（剩 %d 天）" % (end.strftime("%m-%d"), max(days, 0)))
            print("     核销路径：请尽快到店使用；点餐时可让 AI 助手经")
            print("     query-meals + calculate-price 核价后给出最优组合。")
    # 积分
    obj, _ = call("query-my-account")
    if obj and obj.get("data"):
        nx = obj["data"].get("nextMouthExpirePoint") or "0"
        if float(nx or 0) > 0:
            print()
            print("  【积分超度】")
            print("  💾 下月圆寂 %s 分。" % nx)
            try:
                pobj, _ = call("mall-points-products")
                if pobj and pobj.get("data"):
                    items = pobj["data"].get("items", [])
                    best = None
                    for it in items:
                        pt = float(it.get("point") or 0)
                        if 0 < pt <= float(nx):
                            if best is None or pt > float(best.get("point") or 0):
                                best = it
                    if best:
                        print("     兑换建议：%s（%s 分）" % (best.get("spuName"), best.get("point")))
                    else:
                        print("     积分商城暂无合适兑换品，施主可自行长老殿参详。")
            except Exception as e:
                print("     （商城读取失败：%s）" % e)
    print()
    print("  阿弥陀佛，趁早超度，功德无量。")


# ─────────────────────────── 仪式五：功德簿 ───────────────────────────

def merit():
    hr("功德簿 · 施主的麦门修行")
    obj, _ = call("order-list")
    orders = []
    if obj and obj.get("data"):
        orders = obj["data"].get("list", [])
    if not orders:
        print()
        print("  施主的功德簿尚是白卷。快去朝圣吧。阿弥陀佛。")
        return
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
    merit_val = int(total_amt * 10 + len(orders) * 50)
    level = LEVELS[0][1]
    for threshold, name in LEVELS:
        if merit_val < threshold:
            level = name
            break
    else:
        level = LEVELS[-1][1]
    print()
    print("  修行等级：%s（功德 %d 点）" % (level, merit_val))
    print("  修行足迹：%d 次朝圣，累计布施 %.1f 元" % (len(orders), total_amt))
    top_store = max(store_count.items(), key=lambda kv: kv[1]) if store_count else None
    if top_store:
        print("  常驻道场：%s（%d 次）" % top_store)
    top_items = sorted(item_count.items(), key=lambda kv: -kv[1])[:3]
    if top_items:
        print("  忠诚圣物：" + "、".join("%s×%d" % t for t in top_items))
    if kcal > 0:
        print("  累计火候：约 %.0f kcal（≈ %.1f 个巨无霸）" % (kcal, kcal / 513))
    print()
    print("  阿弥陀佛，麦门永存。")


COMMANDS = {
    "morning": morning,
    "blessing": blessing,
    "inventory": inventory,
    "transcend": transcend,
    "merit": merit,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(0 if not cmd else 1)
    time.sleep(0)  # 单命令内调用已尽量精简
    COMMANDS[cmd]()
