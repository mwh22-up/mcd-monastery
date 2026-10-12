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

import monastery  # noqa: E402  —— sys.path 注入之后才能 import


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
        self.total, self.coupons = monastery.parse_coupons_md(COUPONS_MD)

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
        total, coupons = monastery.parse_coupons_md("")
        self.assertEqual((total, coupons), (0, []))

    def test_total_tolerates_spaces(self):
        total, _ = monastery.parse_coupons_md("共 3 张可用优惠券")
        self.assertEqual(total, 3)


class ParseDateTest(unittest.TestCase):

    def test_date_only(self):
        self.assertEqual(monastery.parse_date("2026-10-16"), datetime(2026, 10, 16))

    def test_date_with_time_keeps_date_only(self):
        """基线行为：先按 '%Y-%m-%d' 切 10 字符就能解析成功，时分秒被丢掉。

        券的到期判定只看到日期粒度（7 天窗口），所以这是无害的；这里把它锁住，
        避免后人"顺手修一下"而改变 get_expiring_coupons 的筛选边界。
        """
        self.assertEqual(monastery.parse_date("2026-10-16 23:59:59"),
                         datetime(2026, 10, 16))

    def test_garbage(self):
        self.assertIsNone(monastery.parse_date("下周三"))


class ExtractJsonTest(unittest.TestCase):

    def test_json_wrapped_in_prose(self):
        obj = monastery.extract_json(ACCOUNT_JSON)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["data"]["availablePoint"], 1483)
        self.assertEqual(obj["data"]["expiredPoint"], 1572.8)

    def test_requires_success_data_or_code_key(self):
        self.assertIsNone(monastery.extract_json('{"foo": 1}'))
        self.assertEqual(monastery.extract_json('{"code": 0}'), {"code": 0})

    def test_skips_broken_braces_and_finds_real_object(self):
        self.assertEqual(monastery.extract_json('{ 坏的 } 后面才是真的 {"data": 1}'),
                         {"data": 1})

    def test_no_json_at_all(self):
        self.assertIsNone(monastery.extract_json("暂无可领取的优惠券"))

    def test_empty(self):
        self.assertIsNone(monastery.extract_json(""))


class NutritionToonTest(unittest.TestCase):
    """list-nutrition-foods 的 toon 紧凑 CSV：首行表头、名称第 0 列、kcal 第 3 列。"""

    def setUp(self):
        self._saved_call = monastery.call
        self.calls = []

    def tearDown(self):
        monastery.call = self._saved_call

    def _wire(self, orders):
        def fake_call(tool, args=None):
            self.calls.append(tool)
            if tool == "order-list":
                return ({"data": {"list": orders}}, "")
            if tool == "list-nutrition-foods":
                return ({"data": NUTRITION_TOON}, "")
            raise AssertionError("不该调用 %s" % tool)
        monastery.call = fake_call

    def test_kcal_sums_matched_items_only(self):
        self._wire([{"realTotalAmount": "20.9", "storeName": "南京徐庄路快捷小站",
                     "orderProductList": [{"productName": "巨无霸", "quantity": 2},
                                          {"productName": "薯条（中）", "quantity": 1},
                                          {"productName": "未在营养库里的套餐", "quantity": 3}]}])
        data = monastery.fetch_merit()
        self.assertEqual(data["kcal"], 513 * 2 + 310)
        self.assertEqual(self.calls, ["order-list", "list-nutrition-foods"])

    def test_aggregates_amount_store_and_top_items(self):
        orders = [{"realTotalAmount": "10.0", "storeName": "甲道场",
                   "orderProductList": [{"productName": "薯条（中）", "quantity": 1}]},
                  {"realTotalAmount": "5.5", "storeName": "甲道场",
                   "orderProductList": [{"productName": "薯条（中）", "quantity": 2}]},
                  {"realTotalAmount": "bad", "storeName": None,
                   "orderProductList": None}]
        self._wire(orders)
        data = monastery.fetch_merit()
        self.assertEqual(data["order_count"], 3)
        self.assertAlmostEqual(data["total_amount"], 15.5)
        self.assertEqual(data["top_store"], ("甲道场", 2))
        self.assertEqual(data["top_items"], [("薯条（中）", 3)])

    def test_no_orders_skips_nutrition_call(self):
        def fake_call(tool, args=None):
            self.calls.append(tool)
            return ({"data": {"list": []}}, "")
        monastery.call = fake_call
        data = monastery.fetch_merit()
        self.assertEqual(data["order_count"], 0)
        self.assertEqual(data["kcal"], 0.0)
        self.assertEqual(self.calls, ["order-list"])


class ExpiringFilterTest(unittest.TestCase):
    """get_expiring_coupons 的 7 天窗口 + now() 冻结时钟。"""

    def setUp(self):
        self._saved_call = monastery.call
        self._saved_frozen = monastery._FROZEN
        monastery._FROZEN = datetime(2026, 10, 10, 9, 26)
        monastery.call = lambda tool, args=None: (None, COUPONS_MD)

    def tearDown(self):
        monastery.call = self._saved_call
        monastery._FROZEN = self._saved_frozen

    def test_keeps_only_seven_day_window(self):
        total, expiring = monastery.get_expiring_coupons()
        self.assertEqual(total, 27)
        self.assertEqual([t for t, _ in expiring],
                         ["9.9元中杯冰美式", "巧克力味厚松饼猪柳蛋套餐"])

    def test_now_follows_frozen_clock(self):
        self.assertEqual(monastery.now(), datetime(2026, 10, 10, 9, 26))


if __name__ == "__main__":
    unittest.main()
