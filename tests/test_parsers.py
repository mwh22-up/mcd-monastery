#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锁住 MCP 返回解析行为（R6）：本次重构里这些函数只许位移、不许改内容。

样本按 docs/demo.md 与 MCP_INTEGRATION.md 记录的真实返回格式构造。
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import cathedral  # noqa: E402  —— sys.path 注入之后才能 import


COUPONS_MD = """# 我的优惠券

共 27 张可用优惠券

## 9.9元中杯冰美式
- **券码**: 1001
- **有效期**: 10-10 10:00 - 2026-10-16
- **适用**: 全国门店

## 巧克力味厚松饼猪柳蛋套餐
- **券码**: 1002
- **有效期**: 10-01 00:00 - 2026-10-10

## 无有效期的券
- **券码**: 1003
"""

ACCOUNT_JSON = """查询成功，以下是账户信息：
{"success": true, "data": {"availablePoint": 1483, "accumulativePoint": 3465.8,
 "expiredPoint": 1572.8, "nextMouthExpirePoint": 0}}
以上数据来自会员中心。
"""

NUTRITION_TOON = """name,weight,protein,kcal
薯条（中）,102,4.1,310
可乐（中）,450,0,180
巨无霸,219,26.2,513
"""


class ParseCouponsMdTest(unittest.TestCase):

    def setUp(self):
        self.total, self.coupons = cathedral.parse_coupons_md(COUPONS_MD)

    def test_total_from_summary_line(self):
        self.assertEqual(self.total, 27)

    def test_one_block_per_coupon(self):
        self.assertEqual([c["title"] for c in self.coupons],
                         ["9.9元中杯冰美式", "巧克力味厚松饼猪柳蛋套餐", "无有效期的券"])

    def test_end_date_is_the_tail_of_valid_range(self):
        self.assertEqual(self.coupons[0]["end"], datetime(2026, 10, 16))
        self.assertEqual(self.coupons[1]["end"], datetime(2026, 10, 10))

    def test_missing_valid_range_gives_none(self):
        self.assertIsNone(self.coupons[2]["end"])

    def test_empty_text(self):
        total, coupons = cathedral.parse_coupons_md("")
        self.assertEqual((total, coupons), (0, []))

    def test_total_tolerates_spaces(self):
        total, _ = cathedral.parse_coupons_md("共 3 张可用优惠券")
        self.assertEqual(total, 3)


class ParseDateTest(unittest.TestCase):

    def test_date_only(self):
        self.assertEqual(cathedral.parse_date("2026-10-16"), datetime(2026, 10, 16))

    def test_date_with_time_keeps_date_only(self):
        """基线行为：先按 '%Y-%m-%d' 切 10 字符就能解析成功，时分秒被丢掉。

        券的到期判定只看到日期粒度（7 天窗口），所以这是无害的；这里把它锁住，
        避免后人"顺手修一下"而改变 get_expiring_coupons 的筛选边界。
        """
        self.assertEqual(cathedral.parse_date("2026-10-16 23:59:59"),
                         datetime(2026, 10, 16))

    def test_garbage(self):
        self.assertIsNone(cathedral.parse_date("下周三"))


class ExtractJsonTest(unittest.TestCase):

    def test_json_wrapped_in_prose(self):
        obj = cathedral.extract_json(ACCOUNT_JSON)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["data"]["availablePoint"], 1483)
        self.assertEqual(obj["data"]["expiredPoint"], 1572.8)

    def test_requires_success_data_or_code_key(self):
        self.assertIsNone(cathedral.extract_json('{"foo": 1}'))
        self.assertEqual(cathedral.extract_json('{"code": 0}'), {"code": 0})

    def test_skips_broken_braces_and_finds_real_object(self):
        self.assertEqual(cathedral.extract_json('{ 坏的 } 后面才是真的 {"data": 1}'),
                         {"data": 1})

    def test_no_json_at_all(self):
        self.assertIsNone(cathedral.extract_json("暂无可领取的优惠券"))

    def test_empty(self):
        self.assertIsNone(cathedral.extract_json(""))


class NutritionToonTest(unittest.TestCase):
    """list-nutrition-foods 的 toon 紧凑 CSV：首行表头、名称第 0 列、kcal 第 3 列。"""

    def setUp(self):
        self._saved_call = cathedral.call
        self.calls = []

    def tearDown(self):
        cathedral.call = self._saved_call

    def _wire(self, orders):
        def fake_call(tool, args=None):
            self.calls.append(tool)
            if tool == "order-list":
                return ({"data": {"list": orders}}, "")
            if tool == "list-nutrition-foods":
                return ({"data": NUTRITION_TOON}, "")
            raise AssertionError("不该调用 %s" % tool)
        cathedral.call = fake_call

    def test_kcal_sums_matched_items_only(self):
        self._wire([{"realTotalAmount": "20.9", "storeName": "南京徐庄路快捷小站",
                     "orderProductList": [{"productName": "巨无霸", "quantity": 2},
                                          {"productName": "薯条（中）", "quantity": 1},
                                          {"productName": "未在营养库里的套餐", "quantity": 3}]}])
        data = cathedral.fetch_ledger()
        self.assertEqual(data["kcal"], 513 * 2 + 310)
        self.assertEqual(self.calls, ["order-list", "list-nutrition-foods"])

    def test_aggregates_amount_store_and_top_items(self):
        orders = [{"realTotalAmount": "10.0", "storeName": "甲堂区",
                   "orderProductList": [{"productName": "薯条（中）", "quantity": 1}]},
                  {"realTotalAmount": "5.5", "storeName": "甲堂区",
                   "orderProductList": [{"productName": "薯条（中）", "quantity": 2}]},
                  {"realTotalAmount": "bad", "storeName": None,
                   "orderProductList": None}]
        self._wire(orders)
        data = cathedral.fetch_ledger()
        self.assertEqual(data["order_count"], 3)
        self.assertAlmostEqual(data["total_amount"], 15.5)
        self.assertEqual(data["top_store"], ("甲堂区", 2))
        self.assertEqual(data["top_items"], [("薯条（中）", 3)])

    def test_no_orders_skips_nutrition_call(self):
        def fake_call(tool, args=None):
            self.calls.append(tool)
            return ({"data": {"list": []}}, "")
        cathedral.call = fake_call
        data = cathedral.fetch_ledger()
        self.assertEqual(data["order_count"], 0)
        self.assertEqual(data["kcal"], 0.0)
        self.assertEqual(self.calls, ["order-list"])


class ExpiringFilterTest(unittest.TestCase):
    """get_expiring_coupons 的 7 天窗口 + now() 冻结时钟。"""

    def setUp(self):
        self._saved_call = cathedral.call
        self._saved_frozen = cathedral._FROZEN
        cathedral._FROZEN = datetime(2026, 10, 10, 9, 26)
        cathedral.call = lambda tool, args=None: (None, COUPONS_MD)

    def tearDown(self):
        cathedral.call = self._saved_call
        cathedral._FROZEN = self._saved_frozen

    def test_keeps_only_seven_day_window(self):
        total, expiring = cathedral.get_expiring_coupons()
        self.assertEqual(total, 27)
        self.assertEqual([t for t, _ in expiring],
                         ["9.9元中杯冰美式", "巧克力味厚松饼猪柳蛋套餐"])

    def test_now_follows_frozen_clock(self):
        self.assertEqual(cathedral.now(), datetime(2026, 10, 10, 9, 26))


class ByDaysOrderTest(unittest.TestCase):
    """_by_days 的排序契约（报告 L1）。

    test_align.py 原本有一条 `assertEqual(days, sorted(days))` —— 它拿同一个列表
    和它自己的排序版比，恒真，删掉了。真正的排序校验要喂乱序输入，这是它的新家：
    _by_days 能直接调用，不必经过 golden。
    """

    def setUp(self):
        self._saved_frozen = cathedral._FROZEN
        cathedral._FROZEN = datetime(2026, 10, 10, 9, 26)

    def tearDown(self):
        cathedral._FROZEN = self._saved_frozen

    def test_by_days_sorts_unordered_input(self):
        items = [("丙", datetime(2026, 10, 17)),
                 ("甲", datetime(2026, 10, 10)),
                 ("乙", datetime(2026, 10, 13))]
        self.assertEqual([t for t, _ in cathedral._by_days(items)], ["甲", "乙", "丙"])

    def test_by_days_keeps_upstream_order_within_a_day(self):
        """同一天多张保持上游顺序 —— docstring 声称这条，此前没有任何用例锁它。"""
        same_day = datetime(2026, 10, 13)
        items = [("先来", same_day), ("后到", same_day), ("更早到期", datetime(2026, 10, 11))]
        self.assertEqual([t for t, _ in cathedral._by_days(items)],
                         ["更早到期", "先来", "后到"])


if __name__ == "__main__":
    unittest.main()
