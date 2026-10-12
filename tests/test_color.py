#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""颜色降级（R3）与源码纪律：转义码绝不能漏进重定向产物，输出只能走 ui.out。

降级三情形：--no-color 显式关、NO_COLOR 环境变量、stdout 非 TTY（重定向/管道）。
README 与 docs/demo.md 的代码块都是从重定向产物取的，这里是它们不带 \\x1b 的保险。
"""
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import ui  # noqa: E402  —— sys.path 注入之后才能 import


TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(TESTS_DIR, ".."))
CLI_DIR = os.path.join(REPO, "cli")
SCRIPT = os.path.join(CLI_DIR, "monastery.py")
ESC = "\x1b"
BARE_PRINT_RE = re.compile(r"(?<![\w.])print\(")


def _read(name):
    with open(os.path.join(CLI_DIR, name), encoding="utf-8") as f:
        return f.read()


def run_cli(args, env_extra=None, env_drop=()):
    """跑一次 CLI（stdout 走管道，天然非 TTY）。返回 (退出码, 文本)。"""
    env = dict(os.environ)
    env.pop("MCD_MCP_TOKEN", None)     # demo 模式不该需要凭证
    env.pop("NO_COLOR", None)
    for key in env_drop:
        env.pop(key, None)
    env.update(env_extra or {})
    proc = subprocess.Popen([sys.executable, SCRIPT] + list(args),
                            cwd=REPO, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_out, raw_err = proc.communicate(timeout=120)
    assert raw_err == b"", raw_err
    return proc.returncode, raw_out.decode("utf-8")


class DegradeTest(unittest.TestCase):
    """三种降级情形下输出都必须是纯文本。"""

    RITUALS = ("morning", "blessing", "inventory", "transcend", "merit")

    def test_no_color_flag(self):
        for name in self.RITUALS:
            with self.subTest(ritual=name):
                code, out = run_cli(["--demo", name, "--no-color"])
                self.assertEqual(code, 0)
                self.assertNotIn(ESC, out)

    def test_no_color_env(self):
        for name in self.RITUALS:
            with self.subTest(ritual=name):
                code, out = run_cli(["--demo", name], {"NO_COLOR": "1"})
                self.assertEqual(code, 0)
                self.assertNotIn(ESC, out)

    def test_pipe_is_not_a_tty(self):
        for name in self.RITUALS:
            with self.subTest(ritual=name):
                code, out = run_cli(["--demo", name])
                self.assertEqual(code, 0)
                self.assertNotIn(ESC, out)

    def test_usage_and_error_paths_are_plain_too(self):
        for args in ([], ["-h"], ["badcmd"], ["--nope", "merit"]):
            with self.subTest(args=args):
                _, out = run_cli(args)
                self.assertNotIn(ESC, out)

    def test_chinese_survives_without_pythonioencoding(self):
        """不设 PYTHONIOENCODING 也要正常输出中文（ui.init 自己把 stdout 换成 UTF-8）。"""
        code, out = run_cli(["--demo", "inventory"], env_drop=("PYTHONIOENCODING",))
        self.assertEqual(code, 0)
        self.assertIn("圣物盘点", out)
        self.assertIn("往 生 功 德 碑", out)
        self.assertNotIn("\ufffd", out)      # 没有替换字符 = 没有编码降级丢字


class PaletteGateTest(unittest.TestCase):
    """init() 的四条件判定：任一不满足就关色；全满足才开（防止上面的断言是空洞的）。"""

    def setUp(self):
        self._isatty = ui._isatty
        self._enable_vt = ui._enable_vt
        self._env = dict(os.environ)
        ui._isatty = lambda: True
        ui._enable_vt = lambda: True
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("TERM", None)

    def tearDown(self):
        ui._isatty = self._isatty
        ui._enable_vt = self._enable_vt
        os.environ.clear()
        os.environ.update(self._env)
        ui.init(no_color=True)

    def test_color_on_when_everything_allows(self):
        ui.init(no_color=False)
        self.assertTrue(ui.COLOR_ON)
        self.assertIn(ESC, "".join(ui.plaque("麦门", "x")))

    def test_no_color_flag_wins(self):
        ui.init(no_color=True)
        self.assertFalse(ui.COLOR_ON)
        self.assertNotIn(ESC, "".join(ui.plaque("麦门", "x")))

    def test_no_color_env_wins(self):
        os.environ["NO_COLOR"] = "1"
        ui.init(no_color=False)
        self.assertFalse(ui.COLOR_ON)

    def test_dumb_terminal_wins(self):
        os.environ["TERM"] = "dumb"
        ui.init(no_color=False)
        self.assertFalse(ui.COLOR_ON)

    def test_not_a_tty_wins(self):
        ui._isatty = lambda: False
        ui.init(no_color=False)
        self.assertFalse(ui.COLOR_ON)


class SourceDisciplineTest(unittest.TestCase):
    """monastery.py 只许通过 ui.out 说话，且只许 import 标准库。"""

    def test_no_bare_print_in_monastery(self):
        hits = [line for line in _read("monastery.py").splitlines()
                if BARE_PRINT_RE.search(line)]
        self.assertEqual(hits, [])

    def test_no_argparse_import(self):
        """不许 import argparse：它会自己 print，绕过 ui.out 这个唯一出口。"""
        imports = re.findall(r"^\s*(?:import|from)\s+argparse\b",
                             _read("monastery.py"), re.M)
        self.assertEqual(imports, [])

    def test_no_hr_helper_left_behind(self):
        src = _read("monastery.py")
        self.assertNotIn("def hr(", src)
        self.assertNotIn("hr()", src)

    def test_only_stdlib_imports(self):
        """零依赖红线：cli/ 只许 import 标准库与本项目模块（urllib.request 取根名 urllib）。"""
        stdlib = getattr(sys, "stdlib_module_names", None)
        if stdlib is None:
            self.skipTest("当前解释器没有 sys.stdlib_module_names")
        src = "".join(_read(name) for name in ("ui.py", "monastery.py", "fixtures.py"))
        roots = set(m.split(".")[0]
                    for m in re.findall(r"^(?:import|from)\s+([a-zA-Z_][\w.]*)", src, re.M))
        local = set(("ui", "fixtures"))
        outside = sorted(roots - set(stdlib) - local)
        self.assertEqual(outside, [], "非标准库依赖：%s" % outside)

    def test_no_requirements_file(self):
        self.assertFalse(os.path.exists(os.path.join(REPO, "requirements.txt")))

    def test_no_token_literals_in_sources(self):
        """仓库零凭证：只允许 ${MCD_MCP_TOKEN} 占位符与读环境变量。"""
        for name in ("ui.py", "monastery.py", "fixtures.py"):
            with self.subTest(file=name):
                src = _read(name)
                for line in src.splitlines():
                    if "Bearer" in line:
                        self.assertIn("token", line)      # 拼接的是环境变量里的值


if __name__ == "__main__":
    unittest.main()
