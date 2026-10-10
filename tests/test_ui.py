#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cli/ui.py 的宽度地基、净化层与版面组件单测（stdlib unittest，零依赖）。"""
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

import ui  # noqa: E402  —— sys.path 注入之后才能 import


UI_SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli", "ui.py")
HEAVY_CHARS = set("┏┓┗┛━┃")
LIGHT_CHARS = set("┌┐└┘─│")


def _read_ui_src():
    with open(UI_SRC_PATH, encoding="utf-8") as f:
        return f.read()


class DispWidthTest(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(ui.disp_width(""), 0)

    def test_pure_ascii(self):
        self.assertEqual(ui.disp_width("abc 9.9"), 7)

    def test_pure_cjk(self):
        self.assertEqual(ui.disp_width("麦门修道院"), 10)

    def test_mixed(self):
        self.assertEqual(ui.disp_width("麦门 9.9"), 8)

    def test_ansi_is_stripped(self):
        plain = "麦门"
        colored = ui.C.GOLD + plain + ui.C.RESET
        self.assertEqual(ui.disp_width(colored), 4)
        self.assertEqual(ui.disp_width(colored), ui.disp_width(plain))

    def test_fullwidth_punctuation(self):
        self.assertEqual(ui.disp_width("（）「」"), 8)
        self.assertEqual(ui.disp_width("！：、"), 6)

    def test_emoji(self):
        self.assertEqual(ui.disp_width("😋"), 2)
        self.assertEqual(ui.disp_width("🍟 薯条"), 7)

    def test_box_drawing_counts_one(self):
        # D2：框线与 █ ░ 的 EAW=A，本项目按 1 列计
        self.assertEqual(ui.disp_width("┏━┓"), 3)
        self.assertEqual(ui.disp_width(ui.BAR_FULL + ui.BAR_EMPTY), 2)
        self.assertFalse(ui.AMBIGUOUS_AS_WIDE)


class PadTest(unittest.TestCase):

    def test_left(self):
        self.assertEqual(ui.pad("麦门", 10), "麦门" + " " * 6)

    def test_right(self):
        self.assertEqual(ui.pad("麦门", 10, "right"), " " * 6 + "麦门")

    def test_center_even_gap(self):
        self.assertEqual(ui.pad("麦门", 10, "center"), "   麦门   ")

    def test_center_odd_gap_is_left_light(self):
        # 居中时左少右多
        self.assertEqual(ui.pad("a", 4, "center"), " a  ")

    def test_all_aligns_hit_exact_width(self):
        for align in ("left", "right", "center"):
            for text in ("", "a", "麦门", "麦门 9.9 元", "（麦门）"):
                self.assertEqual(ui.disp_width(ui.pad(text, 20, align)), 20,
                                 "%s / %r" % (align, text))

    def test_overwide_is_truncated(self):
        got = ui.pad("麦" * 40, 20)
        self.assertEqual(ui.disp_width(got), 20)
        self.assertTrue(got.endswith(ui.TRUNC_MARK))

    def test_ansi_does_not_eat_padding(self):
        got = ui.pad(ui.C.GOLD + "麦门" + ui.C.RESET, 10)
        self.assertEqual(ui.disp_width(got), 10)


class TruncTest(unittest.TestCase):

    def test_exact_width_untouched(self):
        self.assertEqual(ui.trunc("麦门修道院", 10), "麦门修道院")

    def test_shorter_untouched(self):
        self.assertEqual(ui.trunc("麦门", 10), "麦门")

    def test_one_column_over(self):
        got = ui.trunc("麦门修道院", 9)
        self.assertEqual(ui.disp_width(got), 9)
        self.assertTrue(got.endswith(ui.TRUNC_MARK))

    def test_cjk_cut_in_half_still_exact(self):
        # 预算只剩 1 列、下一个字要 2 列：补一个空格，总宽仍然精确
        for width in range(3, 12):
            got = ui.trunc("麦门修道院麦门修道院", width)
            self.assertEqual(ui.disp_width(got), width, repr(got))

    def test_mark_is_ascii(self):
        got = ui.trunc("麦门修道院", 6)
        self.assertNotIn("…", got)
        self.assertIn("..", got)

    def test_tiny_widths(self):
        self.assertEqual(ui.trunc("麦门", 2), "..")
        self.assertEqual(ui.trunc("麦门", 1), ".")
        self.assertEqual(ui.trunc("麦门", 0), "")

    def test_ansi_aware(self):
        got = ui.trunc(ui.C.GOLD + "麦" * 10 + ui.C.RESET, 10)
        self.assertEqual(ui.disp_width(got), 10)
        self.assertTrue(got.endswith(ui.TRUNC_MARK + ui.C.RESET))


class SafeTextTest(unittest.TestCase):

    def test_acceptance_sample(self):
        self.assertEqual(ui.safe_text("超值𝟗.𝟗元早餐两件套陪你开工啦😋"),
                         "超值9.9元早餐两件套陪你开工啦")

    def test_math_digits(self):
        self.assertEqual(ui.safe_text("𝟗.𝟗"), "9.9")

    def test_emoji_dropped(self):
        self.assertEqual(ui.safe_text("麦咖啡一早现磨🥳元气早餐震撼来袭！"),
                         "麦咖啡一早现磨元气早餐震撼来袭！")

    def test_symbol_and_variation_selector_dropped(self):
        self.assertEqual(ui.safe_text("韩式风味蘸酱上新❤️就「酱」心有所「薯」"),
                         "韩式风味蘸酱上新就「酱」心有所「薯」")

    def test_zero_width_dropped(self):
        self.assertEqual(ui.safe_text("麦\u200b门\u200d修"), "麦门修")

    def test_whitespace_folded(self):
        self.assertEqual(ui.safe_text("  麦门\n\n 修道院  "), "麦门 修道院")

    def test_fullwidth_punctuation_preserved(self):
        # 只对数学字形块逐字符 NFKC，整串 NFKC 会把这些压成半角
        self.assertEqual(ui.safe_text("（麦门）「薯」"), "（麦门）「薯」")

    def test_empty(self):
        self.assertEqual(ui.safe_text(""), "")

    def test_keeps_width_safe(self):
        raw = "超值𝟗.𝟗元早餐两件套陪你开工啦😋"
        self.assertEqual(ui.disp_width(ui.safe_text(raw)), 29)


class BarTest(unittest.TestCase):

    def test_returns_str(self):
        self.assertIsInstance(ui.bar(3, 7), str)

    def test_zero_is_all_empty(self):
        self.assertEqual(ui.bar(0, 7, 10), ui.BAR_EMPTY * 10)

    def test_negative_is_all_empty(self):
        self.assertEqual(ui.bar(-3, 7, 10), ui.BAR_EMPTY * 10)

    def test_zero_maxv_is_all_empty(self):
        self.assertEqual(ui.bar(5, 0, 10), ui.BAR_EMPTY * 10)

    def test_over_maxv_is_clamped_full(self):
        self.assertEqual(ui.bar(99, 7, 10), ui.BAR_FULL * 10)

    def test_half(self):
        self.assertEqual(ui.bar(5, 10, 10), ui.BAR_FULL * 5 + ui.BAR_EMPTY * 5)

    def test_rounding(self):
        self.assertEqual(ui.bar(1, 7, 10), ui.BAR_FULL * 1 + ui.BAR_EMPTY * 9)

    def test_width_is_exact(self):
        for value in (0, 1, 3, 7, 70):
            self.assertEqual(ui.disp_width(ui.bar(value, 7, 10)), 10)


class PaletteTest(unittest.TestCase):

    def setUp(self):
        self._saved = dict((name, getattr(ui.C, name)) for name in ui.Palette.ATTRS)
        self._no_color = os.environ.get("NO_COLOR")

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(ui.C, name, value)
        if self._no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = self._no_color

    def test_disable_blanks_every_attr(self):
        ui.C.disable()
        for name in ui.Palette.ATTRS:
            self.assertEqual(getattr(ui.C, name), "")

    def test_enable_restores(self):
        ui.C.disable()
        ui.C.enable()
        for name in ui.Palette.ATTRS:
            self.assertTrue(getattr(ui.C, name).startswith("\033["))

    def test_init_no_color(self):
        ui.init(no_color=True)
        for name in ("GOLD", "RED", "DIM", "RESET"):
            self.assertEqual(getattr(ui.C, name), "")
        self.assertFalse(ui.COLOR_ON)

    def test_init_honours_no_color_env(self):
        os.environ["NO_COLOR"] = "1"
        ui.init()
        for name in ("GOLD", "RED", "DIM", "RESET"):
            self.assertEqual(getattr(ui.C, name), "")
        self.assertFalse(ui.COLOR_ON)

    def test_init_is_idempotent(self):
        ui.init(no_color=True)
        first = dict((name, getattr(ui.C, name)) for name in ui.Palette.ATTRS)
        ui.init(no_color=True)
        self.assertEqual(first, dict((n, getattr(ui.C, n)) for n in ui.Palette.ATTRS))

    def test_paint_degrades_to_identity(self):
        ui.C.disable()
        self.assertEqual(ui.C.paint("麦门", ui.C.GOLD), "麦门")

    def test_paint_wraps_when_enabled(self):
        ui.C.enable()
        self.assertEqual(ui.C.paint("麦门", ui.C.GOLD), ui.C.GOLD + "麦门" + ui.C.RESET)

    def test_components_are_colorless_after_degrade(self):
        ui.C.disable()
        rendered = "\n".join(ui.plaque("麦门", "副标题") + ui.seal("【朱印】") + ui.divider())
        self.assertNotIn("\x1b", rendered)


class ComponentWidthTest(unittest.TestCase):
    """每个组件的每一行显示宽度都必须等于 CARD_W —— 这是「对齐」唯一可自动化的判据。"""

    def _blocks(self):
        countdown = "%s %s %s" % (ui.pad(ui.trunc("9.9元中杯冰美式", 24), 24),
                                  ui.bar(0, 7, 10, ui.C.RED),
                                  ui.pad("剩 0 天", 8, "right"))
        return {
            "plaque": ui.plaque("麦门修道院 · 晨课", "2026-10-10 星期六"),
            "plaque_no_subtitle": ui.plaque("麦门修道院 · 领福"),
            "plaque_overwide": ui.plaque("麦" * 40, "门" * 40),
            "panel": ui.panel("今日机缘", ["超值9.9元早餐两件套陪你开工啦",
                                            "麦当劳 X PEACEMINUSONE"]),
            "panel_no_title": ui.panel("", ["在持 27 张，其中 12 张七日内魂飞魄散"]),
            "panel_overwide": ui.panel("长内容", ["麦" * 60]),
            "panel_str_arg": ui.panel("单行", "施主福缘已满，今日无可领之福。"),
            "panel_colored": ui.panel("临期", [countdown], ui.C.RED),
            "panel_nested_bullet": ui.panel("今日机缘", ui.bullet(["超值9.9元早餐两件套",
                                                                   "麦当劳 X PEACEMINUSONE"])),
            "panel_nested_kv": ui.panel("积分", ui.kv_table([("可用", "1483 分"),
                                                              ("累计", "3465.8 分"),
                                                              ("下月圆寂", "0 分")])),
            "kv_table": ui.kv_table([("修行等级", "薯条骑士（功德 2709 点）"),
                                     ("修行足迹", "10 次朝圣，累计布施 220.9 元"),
                                     ("常驻道场", "南京徐庄路快捷小站（6 次）")]),
            "kv_table_fixed_key_w": ui.kv_table([("可用", "1483 分")], key_w=12),
            "seal": ui.seal("【薯条骑士 · 功德 2709】"),
            "rule": ui.rule(),
            "divider": ui.divider(),
            "banner": ui.banner("演示模式 · DEMO",
                                "数据为 2026-10-10 09:26 真实实测快照，非实时查询"),
            "banner_no_sub": ui.banner("演示模式 · DEMO"),
            "bullet": ui.bullet(["短", "麦" * 40, "多行\n悬挂缩进"]),
        }

    def test_every_line_equals_card_w(self):
        for name, block in self._blocks().items():
            self.assertTrue(block, name)
            for line in block:
                self.assertEqual(ui.disp_width(line), ui.CARD_W,
                                 "%s: %r" % (name, line))

    def test_nesting_does_not_truncate(self):
        # 整宽组件塞进 panel 时，行尾填充空格被剥掉，不该触发 '..' 截断
        nested = ui.panel("积分", ui.kv_table([("可用", "1483 分"), ("下月圆寂", "0 分")]))
        self.assertNotIn(ui.TRUNC_MARK, "\n".join(nested))

    def test_tomb_is_self_consistent_and_narrower(self):
        block = ui.tomb(["往 生 功 德 碑", "1572.8 积分", "卒于无人问津之日"],
                        epitaph="超度来晚了，便是来迟了一生。")
        widths = set(ui.disp_width(line) for line in block)
        self.assertEqual(len(widths), 1, widths)
        self.assertLessEqual(widths.pop(), ui.CARD_W)
        self.assertLess(ui.disp_width(block[0].strip()), ui.CARD_W)

    def test_blank(self):
        self.assertEqual(ui.blank(), [""])

    def test_components_return_lists(self):
        self.assertIsInstance(ui.plaque("麦门"), list)
        self.assertIsInstance(ui.seal("【朱印】"), list)
        self.assertIsInstance(ui.rule(), list)


class FrameDisciplineTest(unittest.TestCase):
    """重线只给 plaque/tomb/banner，细线只给 panel/rule，不混搭。"""

    def test_heavy_only(self):
        heavy_blocks = (ui.plaque("麦门", "副标题"),
                        ui.banner("演示模式", "快照"),
                        ui.tomb(["往生"], epitaph="碑文"))
        for block in heavy_blocks:
            text = "".join(block)
            self.assertFalse(set(text) & LIGHT_CHARS, text)

    def test_light_only(self):
        for block in (ui.panel("标签", ["内容"]), ui.rule(), ui.divider()):
            text = "".join(block)
            self.assertFalse(set(text) & HEAVY_CHARS, text)

    def test_cells_carry_no_emoji(self):
        # 框内单元格只放 ASCII+CJK：emoji 必须由调用方过 safe_text 后再进框
        block = ui.panel("今日机缘", ui.bullet([ui.safe_text("超值𝟗.𝟗元早餐两件套陪你开工啦😋")]))
        self.assertNotIn("😋", "".join(block))


class SourceDisciplineTest(unittest.TestCase):
    """ui.py 的硬性纪律：唯一出口、无裸转义码、无写死卡片宽度、只用标准库。"""

    def setUp(self):
        self.src = _read_ui_src()

    def test_single_print_call(self):
        self.assertEqual(len(re.findall(r"(?<![\w.])print\(", self.src)), 1)

    def test_raw_escapes_only_in_palette(self):
        start = self.src.index("class Palette")
        end = self.src.index("C = Palette()")
        palette_src = self.src[start:end]
        for line in self.src.splitlines():
            if "\\033[" in line:
                self.assertIn(line, palette_src, line)

    def test_card_width_is_written_once(self):
        self.assertEqual(len(re.findall(r"(?<![\w.])%d(?![\w.])" % ui.CARD_W, self.src)), 1)

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "需要 Python 3.10+ 的标准库清单")
    def test_stdlib_only(self):
        mods = set(re.findall(r"^(?:import|from)\s+([a-zA-Z_][\w.]*)", self.src, re.M))
        self.assertEqual(mods - set(sys.stdlib_module_names), set())


class OutTest(unittest.TestCase):

    def _capture(self, *blocks):
        saved = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            ui.out(*blocks)
        finally:
            sys.stdout = saved
        return buf.getvalue()

    def test_flattens_lists_and_strings(self):
        self.assertEqual(self._capture(["a", "b"], "c", [""]), "a\nb\nc\n\n")

    def test_prints_block_lines_in_order(self):
        got = self._capture(ui.plaque("麦门"))
        self.assertEqual(got.splitlines(), ui.plaque("麦门"))


if __name__ == "__main__":
    unittest.main()
