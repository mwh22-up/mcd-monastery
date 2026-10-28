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
SCRIPT = os.path.join(CLI_DIR, "cathedral.py")
ESC = "\x1b"
BARE_PRINT_RE = re.compile(r"(?<![\w.])print\(")
CLI_SOURCES = ("ui.py", "cathedral.py", "fixtures.py")

# L2：从「含 Bearer 的行里有没有 token 这个词」改成扫凭证形状。
# 旧判据放过写在别处的裸 key（API_KEY = "sk-..."），而硬编码
# "Bearer sk-live-…" 这类整串反而能通过 —— 方向正好是反的。
# 这行注释刻意不写出完整形状：仓库级凭证红线的 pattern 已收紧成
# sk-[A-Za-z0-9_\-]{8,}，整串写出来会让这条注释自己变成假阳性。
CREDENTIAL_SHAPES = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),          # OpenAI/网关风格
    re.compile(r"eyJ[A-Za-z0-9_\-]{15,}"),         # JWT 头
    re.compile(r"Bearer\s+\S{20,}"),               # 拼死的 Bearer 串
)
# 三条形状各命中一条，用来证明扫描器不是恒绿的。
# 刻意用拼接而不是整串字面量：整串写出来会让「全仓 grep 凭证形状」这条红线
# 自己命中本文件，那条红线就再也分不清「真漏了凭证」和「测试样本」。
# 拼接之后样本的**取值**一字不差，只是源码里不再出现完整形状。
_FAKE_SK = "sk-" + "live-token-abcdef12"
_FAKE_JWT = "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6"
_FAKE_BEARER = "Bearer" + " " + "abcdefghijklmnopqrstuvwxyz012345"
CAUGHT = ('API_KEY = "%s"' % _FAKE_SK,
          't = "%s"' % _FAKE_JWT,
          'h = "%s"' % _FAKE_BEARER)
# cli/cathedral.py 里拼接环境变量的真实写法，必须放行。
NOT_CAUGHT = ('"Authorization": "Bearer " + token,',)


def _import_roots(src):
    """源码里所有 import 的顶层模块名（urllib.request → urllib）。"""
    return set(m.split(".")[0]
               for m in re.findall(r"^(?:import|from)\s+([a-zA-Z_][\w.]*)", src, re.M))


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

    RITUALS = ("matins", "grace", "relics", "vigil", "ledger")

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
        for args in ([], ["-h"], ["badcmd"], ["--nope", "ledger"]):
            with self.subTest(args=args):
                _, out = run_cli(args)
                self.assertNotIn(ESC, out)

    def test_chinese_survives_without_pythonioencoding(self):
        """不设 PYTHONIOENCODING 也要正常输出中文（ui.init 自己把 stdout 换成 UTF-8）。"""
        code, out = run_cli(["--demo", "relics"], env_drop=("PYTHONIOENCODING",))
        self.assertEqual(code, 0)
        self.assertIn("圣物盘点", out)
        self.assertIn("安 息 名 录", out)
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
    """cathedral.py 只许通过 ui.out 说话，且只许 import 标准库。"""

    # cli/ 允许出现的标准库顶层模块。显式白名单而不是 sys.stdlib_module_names：
    # 后者是 3.10+ 才有的，而项目承诺 3.8+，单靠它会让这条红线在 3.8/3.9 上被
    # skip 掉，等于没有校验。白名单是版本无关的，在最低支持版本上照样有判别力。
    ALLOWED_IMPORTS = frozenset({
        "ctypes", "datetime", "io", "json", "os", "re",
        "sys", "time", "unicodedata", "urllib",
    })
    LOCAL_MODULES = frozenset({"ui", "fixtures"})

    def test_no_bare_print_in_cathedral(self):
        hits = [line for line in _read("cathedral.py").splitlines()
                if BARE_PRINT_RE.search(line)]
        self.assertEqual(hits, [])

    def test_no_argparse_import(self):
        """不许 import argparse：它会自己 print，绕过 ui.out 这个唯一出口。"""
        imports = re.findall(r"^\s*(?:import|from)\s+argparse\b",
                             _read("cathedral.py"), re.M)
        self.assertEqual(imports, [])

    def test_no_hr_helper_left_behind(self):
        src = _read("cathedral.py")
        self.assertNotIn("def hr(", src)
        self.assertNotIn("hr()", src)

    def test_only_stdlib_imports(self):
        """零依赖红线：cli/ 只许 import 白名单内的标准库与本项目模块。无 skip。"""
        src = "".join(_read(name) for name in CLI_SOURCES)
        outside = sorted(_import_roots(src) - self.ALLOWED_IMPORTS - self.LOCAL_MODULES)
        self.assertEqual(outside, [], "白名单外的依赖：%s" % outside)

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"),
                         "白名单交叉校验需要 Python 3.10+ 的标准库清单")
    def test_allowlist_contains_only_stdlib(self):
        """3.10+ 上额外确认白名单自身全是标准库，防止有人往白名单里塞第三方模块。"""
        extra = sorted(self.ALLOWED_IMPORTS - set(sys.stdlib_module_names))
        self.assertEqual(extra, [], "白名单里出现了非标准库模块：%s" % extra)

    def test_scanner_flags_third_party_imports(self):
        """证明判据非恒真：喂合成源码，差集必须恰为那两个第三方模块。3.8 上也跑。"""
        src = "import requests\nfrom numpy import array\nimport os\n"
        outside = _import_roots(src) - self.ALLOWED_IMPORTS - self.LOCAL_MODULES
        self.assertEqual(sorted(outside), ["numpy", "requests"])

    def test_no_requirements_file(self):
        self.assertFalse(os.path.exists(os.path.join(REPO, "requirements.txt")))

    def test_no_credential_shapes_in_sources(self):
        """仓库零凭证：只允许 ${MCD_MCP_TOKEN} 占位符与读环境变量。"""
        for name in CLI_SOURCES:
            with self.subTest(file=name):
                src = _read(name)
                for shape in CREDENTIAL_SHAPES:
                    hit = shape.search(src)
                    self.assertIsNone(hit, "%s 出现了凭证形状：%r"
                                      % (name, hit.group(0) if hit else None))

    def test_credential_scanner_catches_fakes(self):
        """证明判据非恒真：三个假凭证各命中一条形状，环境变量拼接的写法必须放行。"""
        for sample in CAUGHT:
            with self.subTest(sample=sample):
                self.assertTrue(any(s.search(sample) for s in CREDENTIAL_SHAPES),
                                "凭证扫描漏了：%r" % sample)
        for sample in NOT_CAUGHT:
            with self.subTest(sample=sample):
                self.assertFalse(any(s.search(sample) for s in CREDENTIAL_SHAPES),
                                 "凭证扫描误报了环境变量拼接：%r" % sample)


if __name__ == "__main__":
    unittest.main()
