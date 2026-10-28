#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锁住 call() 的 200ms 节流（MCP_INTEGRATION.md §5 / SKILL.md 红线）。

重点是失败路径：fetch_matins / fetch_vigil 把部分 call() 包在 try/except 里继续
往下调，若时间戳只在成功时更新，429 之后的下一个 tool 就会零间隔发出 —— 节流失效的
时刻正是最需要它的时刻。这里用假时钟驱动，不睡真实时间、不触达网络。
"""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import cathedral  # noqa: E402  —— sys.path 注入之后才能 import


OK_BODY = json.dumps({"result": {"content": [{"text": '{"success": true}'}]}})


class _FakeClock(object):
    """time 模块的替身：sleep 只推进假时钟并记账。"""

    def __init__(self, start=1000.0):
        self.t = start
        self.slept = []

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds

    def tick(self, seconds):
        self.t += seconds


class _FakeResponse(object):

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body.encode("utf-8")


class ThrottleTest(unittest.TestCase):

    def setUp(self):
        self.clock = _FakeClock()
        self._saved_time = cathedral.time
        self._saved_urlopen = urllib.request.urlopen
        self._saved_last = cathedral._last_call_at
        self._saved_token = os.environ.get("MCD_MCP_TOKEN")
        cathedral.time = self.clock
        cathedral._last_call_at = 0.0
        os.environ["MCD_MCP_TOKEN"] = "dummy-token-for-tests"
        self.outcomes = []          # 每次 urlopen 的剧本：OK_BODY 字符串或异常实例

    def tearDown(self):
        cathedral.time = self._saved_time
        urllib.request.urlopen = self._saved_urlopen
        cathedral._last_call_at = self._saved_last
        if self._saved_token is None:
            os.environ.pop("MCD_MCP_TOKEN", None)
        else:
            os.environ["MCD_MCP_TOKEN"] = self._saved_token

    def _wire(self, outcomes):
        self.outcomes = list(outcomes)

        def fake_urlopen(req, timeout=None):
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return _FakeResponse(outcome)

        urllib.request.urlopen = fake_urlopen

    def test_back_to_back_calls_sleep_the_floor(self):
        self._wire([OK_BODY, OK_BODY])
        cathedral.call("now-time-info")
        cathedral.call("campaign-calendar")
        self.assertEqual(self.clock.slept, [cathedral.THROTTLE_S])

    def test_next_call_after_a_failure_still_sleeps_the_floor(self):
        """429 之后紧接的 tool 不许零间隔发出。"""
        self._wire([urllib.error.URLError("429 Too Many Requests"), OK_BODY])
        with self.assertRaises(urllib.error.URLError):
            cathedral.call("campaign-calendar")
        cathedral.call("available-coupons")
        self.assertEqual(self.clock.slept, [cathedral.THROTTLE_S])

    def test_failure_updates_the_timestamp(self):
        self._wire([urllib.error.URLError("boom")])
        with self.assertRaises(urllib.error.URLError):
            cathedral.call("query-my-account")
        self.assertEqual(cathedral._last_call_at, self.clock.time())

    def test_no_sleep_when_the_gap_already_elapsed(self):
        self._wire([OK_BODY, OK_BODY])
        cathedral.call("order-list")
        self.clock.tick(cathedral.THROTTLE_S * 3)
        cathedral.call("list-nutrition-foods")
        self.assertEqual(self.clock.slept, [])


if __name__ == "__main__":
    unittest.main()
