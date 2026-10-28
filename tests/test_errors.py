#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误与降级路径（报告 S2 / S3）：网络不可达、凭证失效、代理拦截页都不许抛栈。

改造前实测：Token 缺失走框线提示 + exit 1 + stderr 零字节（体面），但网络不可达与
Token 无效是 10/10 抛未捕获栈，用户直接看到 traceback。这个文件把修好之后的行为锁住。

哨兵模式照 tests/test_throttle.py：把 urllib.request.urlopen 换成抛异常的替身，
**不发任何真实网络请求、不使用任何真实凭证**。时钟也是假的，所以不睡真实时间。
"""
import io
import json
import os
import subprocess
import sys
import unittest
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import cathedral  # noqa: E402  —— sys.path 注入之后才能 import
import ui  # noqa: E402


TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(TESTS_DIR, ".."))
SCRIPT = os.path.join(REPO, "cli", "cathedral.py")
RITUALS = ("matins", "grace", "relics", "vigil", "ledger")
MATINS_KEYS = {"campaigns", "campaigns_err", "available", "available_err"}
TRACE = "Traceback (most recent call last)"
FROZEN = datetime(2026, 10, 10, 9, 26)


def http_error(code):
    """造一个 HTTPError。fp=None 时 .code 照样可读，不需要真实响应体。"""
    return urllib.error.HTTPError("https://mcp.mcd.cn", code, "boom", {}, None)


ALL_FAILURES = (
    ("401", http_error(401)),
    ("429", http_error(429)),
    ("500", http_error(500)),
    ("parse", ValueError("unexpected response shape")),
    ("offline", urllib.error.URLError("sentinel")),
)


class _FakeClock(object):
    """time 模块的替身：sleep 只推进假时钟，不睡真实时间。"""

    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, seconds):
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


class _SentinelBase(unittest.TestCase):
    """共用的哨兵装卸：假时钟 + 假 urlopen + 冻结时钟 + 一个假 Token。"""

    def setUp(self):
        ui.init(no_color=True)
        self._saved_time = cathedral.time
        self._saved_urlopen = urllib.request.urlopen
        self._saved_last = cathedral._last_call_at
        self._saved_frozen = cathedral._FROZEN
        self._saved_demo = cathedral._DEMO
        self._saved_token = os.environ.get("MCD_MCP_TOKEN")
        cathedral.time = _FakeClock()
        cathedral._last_call_at = 0.0
        cathedral._FROZEN = FROZEN
        cathedral._DEMO = False
        os.environ["MCD_MCP_TOKEN"] = "dummy-token-for-tests"

    def tearDown(self):
        cathedral.time = self._saved_time
        urllib.request.urlopen = self._saved_urlopen
        cathedral._last_call_at = self._saved_last
        cathedral._FROZEN = self._saved_frozen
        cathedral._DEMO = self._saved_demo
        if self._saved_token is None:
            os.environ.pop("MCD_MCP_TOKEN", None)
        else:
            os.environ["MCD_MCP_TOKEN"] = self._saved_token

    def wire_raise(self, exc):
        """每次 urlopen 都抛同一个异常。"""
        def fake_urlopen(req, timeout=None):
            raise exc
        urllib.request.urlopen = fake_urlopen

    def wire_body(self, body):
        """每次 urlopen 都返回同一段原始响应体。"""
        def fake_urlopen(req, timeout=None):
            return _FakeResponse(body)
        urllib.request.urlopen = fake_urlopen

    def capture(self, fn, *args):
        """把 ui.out 的输出抓成字符串（ui 的唯一打印点是 print）。"""
        saved = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            rc = fn(*args)
        finally:
            sys.stdout = saved
        return rc, buf.getvalue()


class MissingTokenTest(unittest.TestCase):
    """Token 缺失的既有体面行为不许回退：exit 1 + 框线提示 + stderr 零字节。"""

    def test_missing_token_exits_one_with_panel(self):
        env = dict(os.environ)
        env.pop("MCD_MCP_TOKEN", None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        for name in RITUALS:
            with self.subTest(ritual=name):
                proc = subprocess.Popen([sys.executable, SCRIPT, name],
                                        cwd=REPO, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                raw_out, raw_err = proc.communicate(timeout=120)
                out = raw_out.decode("utf-8")
                self.assertEqual(proc.returncode, 1)
                self.assertIn("缺少凭证", out)
                self.assertEqual(raw_err, b"", raw_err)
                self.assertNotIn(TRACE, out)


class FailurePanelTest(unittest.TestCase):
    """_failure_reason / _failure_panel 是纯函数：不起进程、不触网就能覆盖全部错误路径。"""

    def setUp(self):
        ui.init(no_color=True)

    def test_invalid_token_panel(self):
        title, rows = cathedral._failure_panel(http_error(401))
        self.assertEqual(title, "凭证无效")
        self.assertTrue(any("MCD_MCP_TOKEN" in r for r in rows), rows)
        self.assertEqual(cathedral._failure_reason(http_error(401)), "凭证无效或已过期")
        # 永不回显 token 值，连前缀也不打
        self.assertFalse(any("dummy" in r or "Bearer" in r for r in rows), rows)

    def test_forbidden_maps_to_credential_panel(self):
        title, rows = cathedral._failure_panel(http_error(403))
        self.assertEqual(title, "凭证无效")
        self.assertTrue(any("MCD_MCP_TOKEN" in r for r in rows), rows)

    def test_rate_limit_panel(self):
        title, rows = cathedral._failure_panel(http_error(429))
        self.assertEqual(title, "触发限流")
        self.assertTrue(any("200ms" in r for r in rows), rows)
        self.assertEqual(cathedral._failure_reason(http_error(429)), "官方服务限流")

    def test_server_error_panel(self):
        title, rows = cathedral._failure_panel(http_error(500))
        self.assertEqual(title, "服务异常")
        self.assertTrue(any("HTTP 500" in r for r in rows), rows)
        self.assertEqual(cathedral._failure_reason(http_error(500)), "服务异常 HTTP 500")

    def test_network_down_panel(self):
        title, rows = cathedral._failure_panel(urllib.error.URLError("sentinel"))
        self.assertEqual(title, "无法连接")
        self.assertTrue(any("--demo" in r for r in rows), rows)
        self.assertEqual(cathedral._failure_reason(urllib.error.URLError("x")), "网络不可达")

    def test_proxy_html_maps_to_parse_panel(self):
        title, rows = cathedral._failure_panel(ValueError("not json"))
        self.assertEqual(title, "返回内容无法解析")
        self.assertTrue(rows)
        self.assertEqual(cathedral._failure_reason(ValueError("x")), "返回内容无法解析")

    def test_every_failure_panel_row_fits_the_card(self):
        """先断样本非空（每种异常至少 2 行），再逐行断宽度 —— 空集合不算通过。"""
        for label, exc in ALL_FAILURES:
            with self.subTest(failure=label):
                title, rows = cathedral._failure_panel(exc)
                self.assertGreaterEqual(len(rows), 2, label)
                block = ui.panel(title, rows, ui.C.RED)
                self.assertTrue(block, label)
                for line in block:
                    self.assertEqual(ui.disp_width(line), ui.CARD_W, repr(line))
                # 没有一行被 ui.trunc 截断 —— 这才是「列宽没数错」的真判据
                self.assertNotIn(ui.TRUNC_MARK, "\n".join(block))


class MatinsDegradeTest(_SentinelBase):
    """晨祷三路取数独立容错；两路业务取数全失败时降级为纯箴言日签，仍然 exit 0。"""

    def test_matins_degrades_to_verse_only_when_everything_fails(self):
        self.wire_raise(urllib.error.URLError("sentinel"))
        data = cathedral.fetch_matins()          # 不许抛
        text = "\n".join(cathedral.render_matins(data))
        self.assertIn("麦门信众，天下一家。", text)   # 冻结时钟选中的箴言
        self.assertIn("今日取数", text)
        self.assertIn("网络不可达", text)
        self.assertNotIn("今日布告", text)
        self.assertNotIn("可领恩惠", text)

    def test_fetch_matins_keys_are_identical_in_both_modes(self):
        """两条分支的键集必须完全相等 —— 多一个键就会在 --demo 上 KeyError。"""
        self.wire_raise(urllib.error.URLError("sentinel"))
        live = set(cathedral.fetch_matins().keys())
        cathedral._DEMO = True
        demo = set(cathedral.fetch_matins().keys())
        self.assertEqual(live, demo)
        self.assertEqual(live, MATINS_KEYS)


class FatalFailureTest(_SentinelBase):
    """主数据失败刻意不降级：半张卡片比一句实话更糟，所以必须上抛给 main() 兜。"""

    def test_relics_propagates_fatal_failure(self):
        self.wire_raise(urllib.error.URLError("sentinel"))
        with self.assertRaises(urllib.error.URLError):
            cathedral.fetch_relics()

    def test_main_returns_one_and_prints_panel_on_network_error(self):
        self.wire_raise(urllib.error.URLError("sentinel"))
        rc, out = self.capture(cathedral.main, ["relics"])
        self.assertEqual(rc, 1)
        self.assertIn("无法连接", out)
        self.assertNotIn(TRACE, out)


class ResponseShapeTest(_SentinelBase):
    """上游形状变化不该抛 AttributeError / KeyError 栈。"""

    def test_non_dict_response_raises_value_error(self):
        self.wire_body(json.dumps([1, 2, 3]))
        with self.assertRaises(ValueError):
            cathedral.call("query-my-account")
        self.assertEqual(cathedral._failure_reason(ValueError("x")), "返回内容无法解析")

    def test_malformed_content_item_yields_empty_text(self):
        self.wire_body(json.dumps({"result": {"content": ["not a dict"]}}))
        obj, text = cathedral.call("query-my-coupons")      # 不许抛
        self.assertIsNone(obj)
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
