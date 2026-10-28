#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门大教堂 · --demo 离线快照
2026-10-10 09:26 真实 Token 实测数据，出处逐条标注到 docs/demo.md 的小节。

纪律（改这个文件前先读）：
  · 只存「原始数据 + 冻结时钟」，不存渲染结果、不存派生值 ——
    剩余天数、奉献值、阶位、kcal 换算一律由 cathedral.py 的现有公式在渲染时现算；
  · 活动标题逐字照抄上游返回（含 emoji 与数学字形），净化交给 ui.safe_text()，
    这样 demo 走的是和真实模式完全同一条渲染路径；
  · 不含任何凭证；本文件只 import datetime，别加第二个 import。
"""
from datetime import datetime

SNAPSHOT = {
    # docs/demo.md 头部：实测时间 2026-10-10 09:26（北京时间）
    "source": "docs/demo.md · 2026-10-10 09:26 真实 Token 实测",
    # 冻结时钟：所有「剩 N 天」都是以这一刻为基准算出来的
    "now": datetime(2026, 10, 10, 9, 26),

    # docs/demo.md 实测二 · 🌅 晨祷（campaign-calendar 返回 5 个进行中活动）
    # 键名沿用改造前的 morning/blessing/merit：纯内部结构，不进任何输出；
    # 改名只发生在用户可见层与文件名层。
    "morning": {
        "campaigns": [
            "超值𝟗.𝟗元早餐两件套陪你开工啦😋",
            "麦当劳 X PEACEMINUSONE",
            "麦咖啡一早现磨🥳元气早餐震撼来袭！",
            "麦当劳联动G-DRAGON",
            "韩式风味蘸酱上新❤️就「酱」心有所「薯」",
        ],
        # available-coupons：当日券已领完，可领 0 张
        "available": 0,
    },

    # docs/demo.md 实测二 · 🧧 领恩（auto-bind-coupons 幂等返回原文）
    "blessing": {"text": "暂无可领取的优惠券"},

    # docs/demo.md 发现 2 + 实测二 · 📦 圣物盘点（query-my-coupons：27 张在持、12 张临期）
    "coupons": {
        "total": 27,
        # (券名, 到期日)；顺序照抄 docs/demo.md 的临期清单，只存到期日、不存天数
        "expiring": [
            ("9.9元中杯冰美式", "2026-10-16"),
            ("巧克力味厚松饼猪柳蛋套餐", "2026-10-10"),
            ("中薯条买一送一", "2026-10-16"),
            ("王牌小食拼", "2026-10-16"),
            ("巧克力味厚松饼猪柳蛋套餐", "2026-10-11"),
            ("人气麦旋风买一送一", "2026-10-11"),
            ("火腿扒堡早餐两件套", "2026-10-12"),
            ("芝香脆鸡扒堡早餐两件套", "2026-10-13"),
            ("高达芝士蛋堡早餐两件套", "2026-10-14"),
            ("大脆鸡扒堡早餐两件套", "2026-10-15"),
            ("火腿扒堡早餐两件套", "2026-10-16"),
            ("巧克力味厚松饼猪柳蛋套餐", "2026-10-17"),
        ],
    },

    # docs/demo.md 实测二 · 📦 圣物盘点（query-my-account 积分全维度）
    "account": {
        "availablePoint": 1483,          # 可用 1483 分
        "accumulativePoint": 3465.8,     # 累计 3465.8 分
        "expiredPoint": 1572.8,          # 已熄灭 1572.8 分（历史过期损失）
        "nextMouthExpirePoint": 0,       # 下月无熄灭积分，实测未进入兑换分支
    },
    # nextMouthExpirePoint 为 0，mall-points-products 按原链路门槛不调用
    "points_products": None,

    # docs/demo.md 实测二 · 📜 奉献录（order-list 10 笔订单的聚合结果）
    # 只存聚合量：原始订单含门店/时间/商品明细属于个人消费数据，demo.md 本身也只公开聚合
    "merit": {
        "order_count": 10,                              # 10 次朝圣
        "total_amount": 220.9,                          # 累计奉献 220.9 元
        "top_store": ("南京徐庄路快捷小站", 6),          # 常驻堂区 6 次
        "top_items": [                                  # 忠诚圣物 TOP3，照抄 demo.md
            ("马来咖喱风味薄皮肉骨鸡随心配", 2),
            ("巧克力味厚松饼猪柳蛋堡套餐", 1),
            ("板烧鸡腿麦满分单人餐", 1),
        ],
        # 实测订单以组合套餐为主，套餐名未命中 list-nutrition-foods 的单品名，热量结算跳过
        "kcal": 0.0,
    },
}
