#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视觉资产接入 README 的机械校验：引用必须真实存在、每张图必须有 alt、无孤儿资产，
十枚徽记必须带 alpha 透明底。

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
TABLE_REGION = re.compile(r"<table\b.*?</table>", re.I | re.S)
ALT_PUNCT = re.compile(r"""[\s:：;；,，.。、_\-/|()（）\[\]"']+""")

NOT_IN_README = {"og-card.png", "og-bg.webp"}   # 社交卡走仓库设置上传，不嵌 README

# 必须镂空透明底的徽记：五枚日课圆徽 + 五级阶位盾徽。
# 不透明米白方底在 GitHub 亮色模式下会给每枚徽记镶一圈米白方边，
# 暗色模式下直接变成深色页面上的米白瓷砖 —— 这条断言把镂空结果锁住，
# 以后重跑 tools/gen_assets.py 漏了镂空步骤，这里就会红。
ALPHA_REQUIRED = re.compile(r"^(?:ritual|badge)-[A-Za-z0-9._\-]+\.webp$", re.I)
ALPHA_REQUIRED_COUNT = 10
# 整幅构图、铺满自己的画布，按设计就不镂空。
ALPHA_EXEMPT = {"hero.webp", "og-bg.webp", "og-card.png"}
IMAGE_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".gif")
VAGUE_ALTS = {"logo", "image", "img", "icon", "banner",
              "图", "图片", "横幅", "徽章", "hero"}

RITUALS = ("matins", "grace", "relics", "vigil", "ledger")
RITUAL_NAMES = ("晨祷", "领恩", "圣物盘点", "守夜", "奉献录")
RANK_NAMES = ("望教者", "麦门侍者", "薯条骑士", "巨无霸主教", "麦门大祭司")
RANK_RANGES = ("< 200", "200 ~ 999", "1000 ~ 4999", "5000 ~ 19999", "≥ 20000")
KEY_TOOLS = ("now-time-info", "auto-bind-coupons", "query-my-coupons", "order-list")

# 参赛必需内容的四要素标题。改名会动「为什么是…」这一行，而四要素是硬约束，
# 所以给它一条机械判据：缺一即红。
CONTEST_HEADINGS = (
    r"^#\s+麦门大教堂",          # 项目介绍（标题区）
    r"^##\s+.*为什么是大教堂",   # 项目介绍（立意段）
    r"^##\s+.*安装",             # 安装方法
    r"^##\s+.*使用示例",         # 使用示例
    r"^##\s+.*目标用户",         # 目标用户
)


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


def webp_has_alpha(path):
    """只用标准库读 RIFF 容器，判断 webp 是否带 alpha 通道。

    扩展格式的 webp 在第 12–16 字节写下 chunk 名 ``VP8X``，紧随其后 chunk 头的
    第 1 个字节（偏移 20）是特性标志位，bit4 置位即带 alpha。简单有损 ``VP8 ``
    与无损 ``VP8L`` 这里一律按「没有镂空」处理 —— 本仓库的徽记都是带 VP8X
    alpha 块导出的。不是 webp（比如 og-card.png）返回 None。

    TODO：``VP8L`` 其实可以自带 alpha（无损格式的标志位在位流里，不在容器头）。
    当前判据会把无损导出误判为「没镂空」，失败方向是保守的（该绿的变红，
    不会该红的变绿）。若将来把 ``tools/gen_assets.py`` 的导出改成无损 WebP，
    必须同步修改这里的判据，否则这条校验会误报。

    不 import Pillow：资产是预先生成并提交的，没装 Pillow 的环境也要能跑这条。
    """
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        return None
    if head[12:16] != b"VP8X":
        return False
    return bool((head[20] >> 4) & 1)


def normalized_alt(alt):
    """去掉空白与标点后的小写 alt，用来判断整句 alt 是不是只有一个套话词。"""
    return ALT_PUNCT.sub("", alt).strip().lower()


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


class AssetAlphaTest(unittest.TestCase):
    """十枚徽记必须带透明底：镂空一丢，暗色模式下它们就是十块米白瓷砖。"""

    def cutout_assets(self):
        return [n for n in asset_files() if ALPHA_REQUIRED.match(n)]

    def test_cutout_set_is_complete(self):
        names = self.cutout_assets()
        self.assertEqual(len(names), ALPHA_REQUIRED_COUNT,
                         "需要镂空的徽记应为 %d 枚（五日课圆徽 + 五级阶位盾徽），"
                         "实际 %d 枚：%s" % (ALPHA_REQUIRED_COUNT, len(names), names))

    def test_cutout_assets_have_alpha_channel(self):
        for name in self.cutout_assets():
            self.assertIs(webp_has_alpha(os.path.join(ASSETS_DIR, name)), True,
                          "%s 没有 alpha 通道（RIFF 头不是 VP8X 或 alpha 标志位未置）："
                          "镂空步骤丢了，GitHub 暗色模式下会变成米白方片" % name)

    def test_every_asset_image_is_classified(self):
        """新增的图必须明确要不要镂空：既不符合徽记命名、又不在例外清单里就判红。"""
        images = [n for n in asset_files() if n.lower().endswith(IMAGE_SUFFIXES)]
        unclassified = [n for n in images
                        if not ALPHA_REQUIRED.match(n) and n not in ALPHA_EXEMPT]
        self.assertEqual(unclassified, [],
                         "这些图没说清要不要透明底，请归入徽记命名或 ALPHA_EXEMPT：%s"
                         % unclassified)


class ImgAltTest(unittest.TestCase):
    """图挂了也要读得通：每个 <img> 都得有一句说清画了什么的 alt。"""

    def setUp(self):
        self.tags = IMG_TAG.findall(read_readme())

    def test_every_img_has_nonempty_alt(self):
        for tag in self.tags:
            alt = attr(tag, ALT_ATTR)
            self.assertIsNotNone(alt, "<img> 缺少 alt 属性：%s" % tag)
            self.assertNotEqual(alt.strip(), "", "<img> 的 alt 为空：%s" % tag)

    def test_alt_text_is_long_enough(self):
        for tag in self.tags:
            alt = (attr(tag, ALT_ATTR) or "").strip()
            self.assertGreaterEqual(len(alt), 8,
                                    "alt 太短，说不清画的是什么：%r" % alt)

    def test_alt_text_is_not_a_placeholder(self):
        """套话黑名单独立成一个用例。

        黑名单里的词都短于上一条的 8 字下限，和长度断言写在同一个方法里就永不触发
        （先失败先中断）—— 分开成两个用例，alt="logo" 这类才会由这一条自己判红。
        """
        for tag in self.tags:
            alt = (attr(tag, ALT_ATTR) or "").strip()
            self.assertNotIn(normalized_alt(alt), VAGUE_ALTS,
                             "alt 是无信息量的套话：%r" % alt)

    def test_every_img_src_is_a_repo_asset(self):
        for tag in self.tags:
            src = attr(tag, SRC_ATTR)
            self.assertIsNotNone(src, "<img> 缺少 src 属性：%s" % tag)
            self.assertTrue(src.startswith("assets/"),
                            "<img> 的 src 不是仓库内资产：%r" % src)


class TextFallbackTest(unittest.TestCase):
    """关键信息不得只存在于图里：日课、命令、Tool、阶位都要有文字版本。"""

    def setUp(self):
        self.text = read_readme()

    def test_every_ritual_command_is_text(self):
        for name in RITUALS:
            cmd = "python cli/cathedral.py %s" % name
            self.assertIn(cmd, self.text, "日课命令没有文字版本：%s" % cmd)

    def test_every_ritual_name_is_text(self):
        for name in RITUAL_NAMES:
            self.assertIn(name, self.text, "日课名没有文字版本：%s" % name)

    def test_every_rank_name_and_range_is_text(self):
        for name in RANK_NAMES:
            self.assertIn(name, self.text, "等级名没有文字版本：%s" % name)
        for rng in RANK_RANGES:
            self.assertIn(rng, self.text, "奉献值区间没有文字版本：%s" % rng)

    def test_key_tools_are_text(self):
        for tool in KEY_TOOLS:
            self.assertIn(tool, self.text, "Tool 名没有文字版本：%s" % tool)


class ContestElementsTest(unittest.TestCase):
    """参赛必需内容的四要素标题必须齐备：项目介绍、安装方法、使用示例、目标用户。

    独立成一个 TestCase 而不是塞进 TextFallbackTest：这样改造中途的预期红名单
    能按类名点到它。
    """

    def test_contest_four_elements_are_present(self):
        text = read_readme()
        self.assertEqual(len(CONTEST_HEADINGS), 5)
        for pattern in CONTEST_HEADINGS:
            with self.subTest(heading=pattern):
                self.assertRegex(text, re.compile(pattern, re.M),
                                 "参赛四要素标题缺失：%s" % pattern)


class HtmlCellTest(unittest.TestCase):
    """HTML 表格里写 markdown 不会渲染，所以单元格区段内不许出现 markdown 语法。"""

    def test_html_cells_have_no_markdown(self):
        """遍历**所有** <table>…</table> 区段，将来再加一个表格不会被静默跳过。"""
        regions = TABLE_REGION.findall(read_readme())
        self.assertTrue(regions, "README 里找不到 HTML 表格，这条校验失去了对象")
        for i, region in enumerate(regions):
            for token in ("`", "**", "!["):
                self.assertNotIn(token, region,
                                 "第 %d 个 HTML 表格里出现了不会渲染的 markdown 记号：%r"
                                 % (i + 1, token))


class StdlibOnlyTest(unittest.TestCase):
    """本测试自身的零依赖纪律：只碰标准库，不碰构建期工具。"""

    # 本文件允许 import 的模块白名单。
    # 用白名单而不是只靠 sys.stdlib_module_names：后者是 Python 3.10+ 才有的，
    # 而项目声明支持 3.8+，单靠它会让「只用标准库」这条纪律在 3.8/3.9 上被
    # skip 掉，等于没有校验。白名单是版本无关的，在最低支持版本上照样生效。
    ALLOWED_IMPORTS = frozenset({"os", "re", "sys", "unittest"})

    def test_imports_stay_within_allowlist(self):
        """任何新增 import 都必须显式进白名单，第三方模块一律挡掉。"""
        extra = own_imported_roots() - self.ALLOWED_IMPORTS
        self.assertEqual(extra, set(),
                         "资产测试引入了白名单外的模块：%s。"
                         "新增标准库模块请显式加进 ALLOWED_IMPORTS；"
                         "第三方模块一律不允许。" % sorted(extra))

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"),
                         "白名单交叉校验需要 Python 3.10+ 的标准库清单")
    def test_allowlist_contains_only_stdlib(self):
        """3.10+ 上额外确认白名单自身全是标准库，防止有人往白名单里塞第三方模块。"""
        extra = self.ALLOWED_IMPORTS - set(sys.stdlib_module_names)
        self.assertEqual(extra, set(), "白名单里出现了非标准库模块：%s" % sorted(extra))

    def test_does_not_import_build_tool(self):
        mods = own_imported_roots()
        self.assertEqual([m for m in sorted(mods) if m.startswith("PIL")], [],
                         "资产测试不许 import Pillow：资产已提交，无需生成")
        for forbidden in ("tools", "gen_assets"):
            self.assertNotIn(forbidden, mods,
                             "资产测试不许 import 构建期工具：%s" % forbidden)


if __name__ == "__main__":
    unittest.main()
