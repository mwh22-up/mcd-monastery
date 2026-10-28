#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染分支覆盖：--demo 快照取不到的那些取值组合。

快照是 2026-10-10 的一次真实采样，它只覆盖真实数据的一种组合；凡是快照里
取 0 / 取空的字段，其非零分支在 golden 里根本不出现（例如 kcal=0.0 让
「累计灯油」框永不渲染，而真实账号现在是 774.0 —— 评委拿真 Token 一跑就命中）。
这个文件直接调 render_*()，用手搓的数据结构把那些分支一条条走到。

判据是两段式的：先断样本非空 + 断该分支的标志性文案出现（证明分支真的走到了），
再逐行断显示宽度恒等于 CARD_W（这才是判据本身）。只断宽度是不够的 ——
空集合里当然不存在宽度 != 54 的行。

这里的数值是合成数据，刻意不与 cli/fixtures.py 共用，也绝不回灌任何文档。
kcal=774.0 取自 2026-10-19 真实账号冒烟的实测值。
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import cathedral  # noqa: E402  —— sys.path 注入之后才能 import
import ui  # noqa: E402


FROZEN = datetime(2026, 10, 10, 9, 26)


class _RenderCase(unittest.TestCase):
    """冻结时钟在 setUp 设、tearDown 还原，照 tests/test_parsers.py 的既有模式。"""

    def setUp(self):
        ui.init(no_color=True)
        self._saved_frozen = cathedral._FROZEN
        self._saved_demo = cathedral._DEMO
        cathedral._FROZEN = FROZEN
        cathedral._DEMO = False

    def tearDown(self):
        cathedral._FROZEN = self._saved_frozen
        cathedral._DEMO = self._saved_demo

    def check(self, lines, *expected):
        """总则 B：先证明样本抓到了，再断宽度。"""
        self.assertTrue(lines, "render_* 返回空，分支没走到")
        text = "\n".join(lines)
        for token in expected:
            self.assertIn(token, text, "分支标志性文案缺失：%s" % token)
        body = [l for l in lines if l.strip()]
        self.assertTrue(body, "render_* 只返回了空行，分支没走到")
        for line in body:
            self.assertEqual(ui.disp_width(line), ui.CARD_W, repr(line))
        return text


class MatinsBranchTest(_RenderCase):

    def test_available_coupons_are_offered(self):
        """快照 available=0，「麦麦省现有 N 张恩惠可领」这一行从未渲染过。"""
        lines = cathedral.render_matins({"campaigns": ["麦咖啡现磨早餐"], "campaigns_err": None,
                                         "available": 3, "available_err": None})
        self.check(lines, "麦麦省现有 3 张恩惠可领", "诵「领恩」即刻领取")

    def test_single_path_failure_degrades_only_its_own_panel(self):
        """一路失败只影响对应的框，另一框照常渲染。"""
        lines = cathedral.render_matins({"campaigns": [], "campaigns_err": "网络不可达",
                                         "available": 2, "available_err": None})
        text = self.check(lines, "今日布告读取失败", "麦麦省现有 2 张恩惠可领")
        self.assertNotIn("今日取数", text)      # 只有两路都失败才走全失败分支

    def test_empty_campaign_list_falls_back_to_the_scripture_line(self):
        lines = cathedral.render_matins({"campaigns": [], "campaigns_err": None,
                                         "available": 0, "available_err": None})
        self.check(lines, "典籍暂无记载，信徒可自行参详", "信徒的恩惠已领尽")

    def test_total_failure_degrades_to_a_verse_and_keeps_the_closing(self):
        """两路全失败的降级分支：--demo 走不到，golden 也看不见。

        这个分支的落款行（cli/cathedral.py 全失败 return 的 _closing）此前零断言，
        改成旧词也不会有任何用例变红 —— 而残留扫描已被证明有词表盲区，所以这里
        把落款文案一并钉住。
        """
        lines = cathedral.render_matins({"campaigns": [], "campaigns_err": "网络不可达",
                                         "available": 0, "available_err": "网络不可达"})
        text = self.check(lines, "今日取数", "网络不可达，今日先只收一句箴言。",
                          "python cli/cathedral.py --demo matins", "阿门，麦门永存。")
        self.assertNotIn("今日布告", text)      # 全失败分支在这两框之前就 return 了
        self.assertNotIn("可领恩惠", text)


class GraceBranchTest(_RenderCase):

    def test_successful_claim_renders_the_seal(self):
        """快照是幂等的「暂无可领取的优惠券」，领券成功分支与落款从未渲染过。"""
        lines = cathedral.render_grace({"text": "领券成功，共领取 3 张优惠券"})
        self.check(lines, "阿门，今日领得 3 张恩惠，奉献值 +3。", "【今日奉献值 +3】")


class RelicsBranchTest(_RenderCase):

    def _account(self, **kw):
        base = {"availablePoint": 1200, "accumulativePoint": 3000.0,
                "expiredPoint": 0, "nextMouthExpirePoint": 0}
        base.update(kw)
        return base

    def test_next_month_expiring_points_row(self):
        """快照 nextMouthExpirePoint=0，「下月熄灭」这一行从未渲染过。"""
        lines = cathedral.render_relics({"total": 5, "expiring": [],
                                         "account": self._account(nextMouthExpirePoint=360)})
        self.check(lines, "下月熄灭", "360 分（建议诵「守夜」）")

    def test_empty_wallet(self):
        """快照 total=27，「信徒暂无在持之券」从未渲染过。"""
        lines = cathedral.render_relics({"total": 0, "expiring": [], "account": self._account()})
        self.check(lines, "信徒暂无在持之券。")

    def test_nothing_expiring(self):
        """快照有 12 张临期，「券包安好，无需守夜」从未渲染过。"""
        lines = cathedral.render_relics({"total": 5, "expiring": [], "account": self._account()})
        self.check(lines, "券包安好，无需守夜。")

    def test_account_read_failure(self):
        """快照 account 非 None，「积分账户读取失败」从未渲染过。"""
        lines = cathedral.render_relics({"total": 5, "expiring": [], "account": None})
        self.check(lines, "（积分账户读取失败）")

    def test_zero_expired_points_omits_the_memorial(self):
        """快照 expiredPoint=1572.8，碑被省略的分支从未渲染过。"""
        lines = cathedral.render_relics({"total": 5, "expiring": [],
                                         "account": self._account(expiredPoint=0)})
        text = self.check(lines, "圣物盘点")
        self.assertNotIn("安 息 名 录", text)
        self.assertNotIn("卒于无人问津之日", text)

    def test_expired_points_raise_the_memorial(self):
        lines = cathedral.render_relics({"total": 5, "expiring": [],
                                         "account": self._account(expiredPoint=820.5)})
        self.check(lines, "安 息 名 录", "820.5 积分", "守夜来晚了，便是来迟了一生。")


class VigilBranchTest(_RenderCase):

    def _data(self, **kw):
        base = {"total": 5, "expiring": [], "account": None,
                "points_products": None, "points_err": None}
        base.update(kw)
        return base

    def test_no_expiring_assets(self):
        """快照有 12 张临期，「信徒券包安好，无临期之危」从未渲染过。"""
        lines = cathedral.render_vigil(self._data())
        self.check(lines, "信徒券包安好，无临期之危。")

    def test_points_vigil_frame_with_a_redemption_suggestion(self):
        """快照 nextMouthExpirePoint=0 且 points_products=None，整个「积分守夜」框从未渲染过。"""
        products = {"data": {"items": [{"spuName": "中杯拿铁", "point": 300},
                                       {"spuName": "超纲大礼包", "point": 900}]}}
        lines = cathedral.render_vigil(self._data(
            account={"nextMouthExpirePoint": 360}, points_products=products))
        self.check(lines, "积分守夜", "下月熄灭 360 分。", "兑换建议：中杯拿铁（300 分）")

    def test_points_vigil_falls_back_when_nothing_is_affordable(self):
        """门槛内挑不到兑换品时的兜底一行。"""
        products = {"data": {"items": [{"spuName": "超纲大礼包", "point": 900}]}}
        lines = cathedral.render_vigil(self._data(
            account={"nextMouthExpirePoint": 360}, points_products=products))
        self.check(lines, "积分商城暂无合适兑换品，信徒可自行参详。")

    def test_points_shop_failure_is_reported_in_place(self):
        lines = cathedral.render_vigil(self._data(
            account={"nextMouthExpirePoint": 360}, points_err="网络不可达"))
        self.check(lines, "商城读取失败", "网络不可达")

    def test_expiring_coupons_get_a_frame_each(self):
        expiring = [("9.9元中杯冰美式", datetime(2026, 10, 11)),
                    ("中薯条买一送一", datetime(2026, 10, 15))]
        lines = cathedral.render_vigil(self._data(expiring=expiring))
        self.check(lines, "9.9元中杯冰美式 · 10-11 烛火熄灭", "中薯条买一送一 · 10-15 烛火熄灭")


class LedgerBranchTest(_RenderCase):

    def _data(self, **kw):
        base = {"order_count": 4, "total_amount": 88.0,
                "top_store": ("南京徐庄路快捷小站", 3),
                "top_items": [("巨无霸", 2)], "kcal": 0.0}
        base.update(kw)
        return base

    def test_kcal_frame_renders_when_nutrition_matches(self):
        """快照 kcal=0.0，「累计灯油」整框从未渲染过 —— 真实账号现在是 774.0。"""
        lines = cathedral.render_ledger(self._data(kcal=774.0))
        self.check(lines, "累计灯油", "约 774 kcal", "个巨无霸")

    def test_blank_ledger(self):
        """快照 order_count=10，白卷分支从未渲染过。"""
        lines = cathedral.render_ledger(self._data(order_count=0))
        self.check(lines, "信徒的奉献录尚是白卷。快去朝圣吧。阿门。")

    def test_no_top_items_omits_the_relics_frame(self):
        """快照 top_items 非空，「忠诚圣物」框被省略的分支从未渲染过。"""
        lines = cathedral.render_ledger(self._data(top_items=[]))
        text = self.check(lines, "信徒档案", "奉献阶位")
        self.assertNotIn("忠诚圣物", text)

    def test_missing_top_store_omits_the_parish_row(self):
        lines = cathedral.render_ledger(self._data(top_store=None))
        text = self.check(lines, "奉献足迹")
        self.assertNotIn("常驻堂区", text)


if __name__ == "__main__":
    unittest.main()
