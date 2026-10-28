#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五日课 --demo 输出的黄金回归：版式对齐 + 数值与 docs/demo.md 逐条一致。

golden 由 `python cli/cathedral.py --demo <日课> > tests/golden/<日课>.txt` 生成
（必须重定向到文件，借非 TTY 自动降级拿纯文本无转义码版本）。
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
SCRIPT = os.path.join(REPO, "cli", "cathedral.py")
GOLDEN_DIR = os.path.join(TESTS_DIR, "golden")
RITUALS = ("matins", "grace", "relics", "vigil", "ledger")
FRAME_CHARS = set("┏┓┗┛━┃┌┐└┘─│")
HEAVY_CHARS = set("┏┓┗┛━┃")
DOC_SOURCES = ("README.md", os.path.join("docs", "demo.md"))
DEMO_MARK = "演示模式 · DEMO"      # 日课输出块的判据：目录树与命令示例都不带它


def run_cli(*args):
    """跑一次 CLI（stdout 是管道，非 TTY，颜色自动降级）。返回 (退出码, 文本, stderr)。"""
    env = dict(os.environ)
    env.pop("MCD_MCP_TOKEN", None)      # demo 模式不该需要凭证
    env.pop("NO_COLOR", None)
    proc = subprocess.Popen([sys.executable, SCRIPT] + list(args),
                            cwd=REPO, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_out, raw_err = proc.communicate(timeout=120)
    return proc.returncode, raw_out.decode("utf-8"), raw_err.decode("utf-8")


def read_golden(name):
    with open(os.path.join(GOLDEN_DIR, "%s.txt" % name), encoding="utf-8") as f:
        return f.read()


def read_doc(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


def fenced_blocks(rel):
    """提取 Markdown 围栏代码块，返回 [(正文起始行号, 正文)]。"""
    lines = read_doc(rel).splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("```"):
            i += 1
            continue
        start = i + 1
        end = start
        while end < len(lines) and not lines[end].startswith("```"):
            end += 1
        blocks.append((start + 1, "\n".join(lines[start:end])))
        i = end + 1
    return blocks


class GoldenTest(unittest.TestCase):
    """--demo 输出必须与 golden 逐行一致（换行符差异不计）。"""

    def test_golden_files_exist_and_are_plain_text(self):
        for name in RITUALS:
            path = os.path.join(GOLDEN_DIR, "%s.txt" % name)
            with self.subTest(ritual=name):
                self.assertTrue(os.path.isfile(path), path)
                text = read_golden(name)
                self.assertNotIn("\x1b", text)
                self.assertTrue(text.strip())

    def test_output_matches_golden(self):
        for name in RITUALS:
            with self.subTest(ritual=name):
                code, out, err = run_cli("--demo", name)
                self.assertEqual(code, 0, err)
                self.assertEqual(err, "")
                self.assertEqual(out.splitlines(), read_golden(name).splitlines())


class DocBlockTest(unittest.TestCase):
    """文档里的日课输出块必须逐字取自 golden —— README 自己声明「一律从 golden 复制，不手写」。

    golden 已由 GoldenTest 锁在 CLI 上，这里把文档也锁上，补齐 CLI → golden → 文档的最后一环：
    改了版面只重新生成 golden 而忘了回填文档，会在这里红。
    """

    def test_doc_blocks_are_golden_substrings(self):
        goldens = [read_golden(name) for name in RITUALS]
        found = 0
        for rel in DOC_SOURCES:
            for lineno, body in fenced_blocks(rel):
                if DEMO_MARK not in body:
                    continue
                found += 1
                with self.subTest(doc=rel, line=lineno):
                    self.assertTrue(
                        any(body in text for text in goldens),
                        "%s 第 %d 行起的输出块已与 tests/golden/ 漂移，请从 golden 重新复制"
                        % (rel, lineno))
        self.assertEqual(found, 6, "应有 6 个日课输出块：README 晨祷 1 + demo.md 五日课 5")

    def test_demo_md_quotes_every_ritual_in_full(self):
        doc = read_doc(os.path.join("docs", "demo.md"))
        for name in RITUALS:
            with self.subTest(ritual=name):
                self.assertIn(read_golden(name).strip(), doc,
                              "docs/demo.md 缺 %s 的完整 golden 输出" % name)

    def test_readme_shows_the_matins_ritual(self):
        self.assertIn(read_golden("matins").strip(), read_doc("README.md"),
                      "README 第二屏的晨祷输出块已与 golden 漂移")


class DemoBannerTest(unittest.TestCase):
    """--demo 必须在所有输出之前打诚信横幅，明示是快照不是实时数据。"""

    def test_banner_is_the_first_block(self):
        for name in RITUALS:
            with self.subTest(ritual=name):
                lines = read_golden(name).splitlines()
                self.assertTrue(lines[0].startswith("┏"))
                head = "\n".join(lines[:5])
                self.assertIn("演示模式 · DEMO", head)
                self.assertIn("2026-10-10 09:26 真实实测快照", head)
                self.assertIn("非实时查询", head)


class AlignmentTest(unittest.TestCase):
    """框线行的显示宽度必须等于所属区块宽度 —— 这是「对齐」唯一可自动化的判据。"""

    def test_card_lines_are_card_wide(self):
        for name in RITUALS:
            for line in read_golden(name).splitlines():
                if line and line[0] in FRAME_CHARS:
                    self.assertEqual(ui.disp_width(line), ui.CARD_W,
                                     "%s: %r" % (name, line))

    def test_every_non_blank_line_is_card_wide(self):
        for name in RITUALS:
            for line in read_golden(name).splitlines():
                if line.strip():
                    self.assertEqual(ui.disp_width(line), ui.CARD_W,
                                     "%s: %r" % (name, line))

    def test_tomb_block_is_narrower_but_self_consistent(self):
        body = [line.strip() for line in read_golden("relics").splitlines()
                if line.startswith(" ") and line.strip() and line.strip()[0] in HEAVY_CHARS]
        self.assertTrue(body, "relics 应有安息名录碑区块")
        widths = set(ui.disp_width(line) for line in body)
        self.assertEqual(len(widths), 1, widths)
        self.assertLess(widths.pop(), ui.CARD_W)

    def test_frame_families_do_not_mix(self):
        for name in RITUALS:
            for line in read_golden(name).splitlines():
                chars = set(line)
                if chars & HEAVY_CHARS:
                    self.assertFalse(chars & (FRAME_CHARS - HEAVY_CHARS),
                                     "%s: %r" % (name, line))


class DemoDataTest(unittest.TestCase):
    """渲染出的数值必须与 docs/demo.md 逐条一致（派生值现算，不是写死的）。"""

    def test_countdown_days_are_sorted_ascending(self):
        days = [int(m) for m in re.findall(r"剩 (\d+) 天", read_golden("relics"))]
        self.assertEqual(days, [0, 0, 0, 1, 2, 3, 4, 5, 5, 5, 5, 6])

    def test_vigil_shares_the_same_order(self):
        days = [int(m) for m in re.findall(r"剩 (\d+) 天", read_golden("vigil"))]
        self.assertEqual(days, [0, 0, 0, 1, 2, 3, 4, 5, 5, 5, 5, 6])

    def test_countdown_bars_are_colorless_and_full_width(self):
        for name in ("relics", "vigil"):
            bars = re.findall(r"[%s%s]+" % (ui.BAR_FULL, ui.BAR_EMPTY), read_golden(name))
            self.assertEqual(len(bars), 12)
            for one in bars:
                self.assertEqual(len(one), 10, one)

    def test_zero_day_bar_is_empty_and_six_day_bar_is_nearly_full(self):
        rows = [line for line in read_golden("relics").splitlines() if "剩 0 天" in line]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertIn(ui.BAR_EMPTY * 10, row)
        six = [line for line in read_golden("relics").splitlines() if "剩 6 天" in line]
        self.assertIn(ui.BAR_FULL * 9 + ui.BAR_EMPTY, six[0])

    def test_relics_numbers(self):
        text = read_golden("relics")
        self.assertIn("在持 27 张，其中 12 张七日内烛火熄灭", text)
        self.assertIn("1483 分", text)
        self.assertIn("3465.8 分", text)
        self.assertIn("1572.8 积分", text)
        self.assertIn("【圣物 27 · 临期 12】", text)
        self.assertNotIn("下月熄灭", text)      # nextMouthExpirePoint 为 0，不出现该行

    def test_ledger_numbers(self):
        text = read_golden("ledger")
        self.assertIn("薯条骑士（奉献值 2709 点）", text)
        self.assertIn("10 次朝圣，累计奉献 220.9 元", text)
        self.assertIn("南京徐庄路快捷小站（6 次）", text)
        self.assertIn("【薯条骑士 · 奉献值 2709】", text)
        # 实测未命中营养库，不出现热量行；非零分支由 tests/test_render_branches.py 覆盖
        self.assertNotIn("kcal", text)

    def test_matins_campaigns_are_sanitized(self):
        text = read_golden("matins")
        self.assertIn("超值9.9元早餐两件套陪你开工啦", text)
        self.assertIn("麦当劳 X PEACEMINUSONE", text)
        self.assertIn("2026-10-10 星期六", text)   # D10：自维护中文星期表
        self.assertNotIn("Saturday", text)
        for junk in ("😋", "🥳", "❤", "𝟗"):
            self.assertNotIn(junk, text)

    def test_grace_is_idempotent_message(self):
        text = read_golden("grace")
        self.assertIn("信徒的恩惠已领尽，今日无可领之券。明日再来。", text)
        self.assertIn("【恩惠已领尽】", text)


class ExitCodeTest(unittest.TestCase):

    def test_demo_rituals_exit_zero(self):
        for name in RITUALS:
            with self.subTest(ritual=name):
                code, out, err = run_cli("--demo", name)
                self.assertEqual(code, 0, err)
                self.assertTrue(out.strip())

    def test_no_argument_prints_usage_and_exits_zero(self):
        code, out, _ = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("麦门大教堂 · 五大日课", out)
        for name in RITUALS:
            self.assertIn(name, out)

    def test_help_exits_zero(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                code, out, _ = run_cli(flag)
                self.assertEqual(code, 0)
                self.assertIn("麦门大教堂 · 五大日课", out)

    def test_bad_command_exits_one(self):
        code, out, _ = run_cli("badcmd")
        self.assertEqual(code, 1)
        self.assertIn("查无此日课", out)

    def test_unknown_flag_exits_two(self):
        code, out, _ = run_cli("--nope", "ledger")
        self.assertEqual(code, 2)
        self.assertIn("无法辨识的选项", out)

    def test_extra_positional_arg_exits_two(self):
        """多余位置参数不许被静默吞掉（报告 L4）。只断退出码与首行文案，不断颜色。"""
        code, out, _ = run_cli("matins", "relics")
        self.assertEqual(code, 2)
        self.assertIn("多余的参数", out)
        self.assertNotIn("缺少凭证", out)

    def test_usage_shows_the_full_demo_command(self):
        """凭证面板里的 --demo 命令必须完整可见 —— 挤成一行会被 ui.trunc 截成 '..'。"""
        code, out, _ = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("python cli/cathedral.py --demo relics", out)
        self.assertNotIn("--demo relic..", out)


if __name__ == "__main__":
    unittest.main()
