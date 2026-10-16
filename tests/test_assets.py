#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视觉资产接入 README 的机械校验：引用必须真实存在、每张图必须有 alt、无孤儿资产。

只用标准库。本文件绝不 import Pillow，也绝不 import tools/gen_assets.py ——
资产是预先生成好并提交的，没有 Pillow 的环境（评委、CI）跑这套测试也必须全绿。
"""
import os
import re
import sys
import unittest


TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(TESTS_DIR, ".."))
ASSETS_DIR = os.path.join(REPO, "assets")
README = os.path.join(REPO, "README.md")

ASSET_REF = re.compile(r"assets/[A-Za-z0-9._\-/]+?\.(?:webp|png|jpe?g|gif|svg)")
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ALT_ATTR = re.compile(r"""\balt\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
SRC_ATTR = re.compile(r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)

NOT_IN_README = {"og-card.png", "og-bg.webp"}   # 社交卡走仓库设置上传，不嵌 README
VAGUE_ALTS = {"logo", "image", "img", "icon", "banner",
              "图", "图片", "横幅", "徽章", "hero"}

RITUALS = ("morning", "blessing", "inventory", "transcend", "merit")
RITUAL_NAMES = ("晨课", "领福", "圣物盘点", "超度", "功德簿")
RANK_NAMES = ("见习麦门徒", "麦门侍僧", "薯条骑士", "巨无霸主教", "麦门大祭司")
RANK_RANGES = ("< 200", "200 ~ 999", "1000 ~ 4999", "5000 ~ 19999", "≥ 20000")
KEY_TOOLS = ("now-time-info", "auto-bind-coupons", "query-my-coupons", "order-list")


def read_readme():
    with open(README, encoding="utf-8") as f:
        return f.read()


def readme_refs():
    """README 里引用到的仓库内资产路径（去重后排序）。"""
    return sorted(set(ASSET_REF.findall(read_readme())))


def attr(tag, pattern):
    """取 HTML 属性值；双引号与单引号两种写法都认，取不到返回 None。"""
    m = pattern.search(tag)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def asset_files():
    """assets/ 顶层的真实文件。isfile 天然滤掉 assets/.raw/ 这类中间产物目录。"""
    return sorted(n for n in os.listdir(ASSETS_DIR)
                  if os.path.isfile(os.path.join(ASSETS_DIR, n)))


def own_imported_roots():
    """本文件自身 import 的模块名根集合。"""
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        src = f.read()
    mods = re.findall(r"^(?:import|from)\s+([A-Za-z_][\w.]*)", src, re.M)
    return set(m.split(".")[0] for m in mods)


class AssetReferenceTest(unittest.TestCase):
    """README 的引用与 assets/ 的文件互为闭环：没有死链，也没有孤儿。"""

    def test_readme_references_exist(self):
        missing = [r for r in readme_refs()
                   if not os.path.isfile(os.path.join(REPO, r))]
        self.assertEqual(missing, [], "README 引用了不存在的资产：%s" % missing)

    def test_every_asset_is_used_or_excepted(self):
        used = set(os.path.basename(r) for r in readme_refs())
        orphan = [n for n in asset_files()
                  if n not in used and n not in NOT_IN_README]
        self.assertEqual(orphan, [], "资产未被 README 引用且不在例外清单里：%s" % orphan)

    def test_exceptions_still_exist(self):
        for name in sorted(NOT_IN_README):
            path = os.path.join(ASSETS_DIR, name)
            self.assertTrue(os.path.isfile(path),
                            "例外清单里的 %s 已不在磁盘上，清单该清理了" % name)

    def test_asset_paths_are_repo_relative(self):
        text = read_readme()
        self.assertNotIn("raw.githubusercontent", text,
                         "资产必须走仓库内相对路径，不要 raw.githubusercontent 外链")
        external = re.findall(r"https?://[^\s\"'()]*assets/", text)
        self.assertEqual(external, [], "资产出现了绝对 URL 引用：%s" % external)


class ImgAltTest(unittest.TestCase):
    """图挂了也要读得通：每个 <img> 都得有一句说清画了什么的 alt。"""

    def setUp(self):
        self.tags = IMG_TAG.findall(read_readme())

    def test_every_img_has_nonempty_alt(self):
        for tag in self.tags:
            alt = attr(tag, ALT_ATTR)
            self.assertIsNotNone(alt, "<img> 缺少 alt 属性：%s" % tag)
            self.assertNotEqual(alt.strip(), "", "<img> 的 alt 为空：%s" % tag)

    def test_alt_text_is_informative(self):
        for tag in self.tags:
            alt = (attr(tag, ALT_ATTR) or "").strip()
            self.assertGreaterEqual(len(alt), 8,
                                    "alt 太短，说不清画的是什么：%r" % alt)
            self.assertNotIn(alt.lower(), VAGUE_ALTS,
                             "alt 是无信息量的套话：%r" % alt)

    def test_every_img_src_is_a_repo_asset(self):
        for tag in self.tags:
            src = attr(tag, SRC_ATTR)
            self.assertIsNotNone(src, "<img> 缺少 src 属性：%s" % tag)
            self.assertTrue(src.startswith("assets/"),
                            "<img> 的 src 不是仓库内资产：%r" % src)


class TextFallbackTest(unittest.TestCase):
    """关键信息不得只存在于图里：仪式、命令、Tool、段位都要有文字版本。"""

    def setUp(self):
        self.text = read_readme()

    def test_every_ritual_command_is_text(self):
        for name in RITUALS:
            cmd = "python cli/monastery.py %s" % name
            self.assertIn(cmd, self.text, "仪式命令没有文字版本：%s" % cmd)

    def test_every_ritual_name_is_text(self):
        for name in RITUAL_NAMES:
            self.assertIn(name, self.text, "仪式名没有文字版本：%s" % name)

    def test_every_rank_name_and_range_is_text(self):
        for name in RANK_NAMES:
            self.assertIn(name, self.text, "等级名没有文字版本：%s" % name)
        for rng in RANK_RANGES:
            self.assertIn(rng, self.text, "功德区间没有文字版本：%s" % rng)

    def test_key_tools_are_text(self):
        for tool in KEY_TOOLS:
            self.assertIn(tool, self.text, "Tool 名没有文字版本：%s" % tool)


class HtmlCellTest(unittest.TestCase):
    """HTML 表格里写 markdown 不会渲染，所以单元格区段内不许出现 markdown 语法。"""

    def test_html_cells_have_no_markdown(self):
        text = read_readme()
        start = text.index("<table>")
        end = text.index("</table>") + len("</table>")
        region = text[start:end]
        for token in ("`", "**", "!["):
            self.assertNotIn(token, region,
                             "HTML 表格里出现了不会渲染的 markdown 记号：%r" % token)


class StdlibOnlyTest(unittest.TestCase):
    """本测试自身的零依赖纪律：只碰标准库，不碰构建期工具。"""

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "需要 Python 3.10+ 的标准库清单")
    def test_no_third_party_imports(self):
        mods = own_imported_roots()
        self.assertEqual(mods - set(sys.stdlib_module_names), set())

    def test_does_not_import_build_tool(self):
        mods = own_imported_roots()
        self.assertEqual([m for m in sorted(mods) if m.startswith("PIL")], [],
                         "资产测试不许 import Pillow：资产已提交，无需生成")
        for forbidden in ("tools", "gen_assets"):
            self.assertNotIn(forbidden, mods,
                             "资产测试不许 import 构建期工具：%s" % forbidden)


if __name__ == "__main__":
    unittest.main()
