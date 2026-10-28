#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python 3.8 兼容扫描：用 ast 扫 cli/*.py 里的 3.9+ 构造。

红线要求 3.8+ 可跑，但本机只有 3.13 解释器，这个扫描是唯一的自动化防线。
"""
import ast
import os
import sys
import unittest

CLI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli")
BANNED_METHODS = ("removeprefix", "removesuffix")   # str 方法，3.9+
BANNED_MODULES = ("zoneinfo", "graphlib")           # 标准库模块，3.9+

# 内置泛型下标：list[str] / dict[str, int] 在 3.8 的运行时求值注解里直接 TypeError，
# 是实际工程中最常见的 3.8 破坏源。
GENERIC_BUILTINS = ("list", "dict", "set", "frozenset", "tuple", "type")
NEW_ATTRS = {                       # 3.9+/3.10+ 才有的属性，调用点一律判红
    ("math", "lcm"): "3.9", ("math", "nextafter"): "3.9", ("math", "ulp"): "3.9",
    ("ast", "unparse"): "3.9", ("random", "randbytes"): "3.9",
    ("functools", "cache"): "3.9",          # 与下面既有的专用分支同一口径
    ("itertools", "pairwise"): "3.10",
}
BIT_COUNT = "bit_count"             # int.bit_count()，3.10+；按方法名判，不看 receiver 类型
# 运行时位置的联合类型（isinstance(x, int | str)）。只认两侧都是小写内置类型名的情形，
# 与下面的 dict | dict 分支互斥，所以 elif 链的先后顺序不影响结果。
UNION_BUILTINS = frozenset({"bool", "bytes", "complex", "dict", "float", "frozenset",
                            "int", "list", "set", "str", "tuple", "type"})


def _sources():
    """逐个产出 cli/ 下的 .py 文件（文件名, 源码）。"""
    for name in sorted(os.listdir(CLI_DIR)):
        if name.endswith(".py"):
            with open(os.path.join(CLI_DIR, name), encoding="utf-8") as f:
                yield name, f.read()


def _annotations(tree):
    """产出所有注解位置的 AST 节点（参数注解 / 返回注解 / 变量注解）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            groups = [args.args, args.kwonlyargs, getattr(args, "posonlyargs", [])]
            for group in groups:
                for arg in group:
                    if arg.annotation is not None:
                        yield arg.annotation
            for extra in (args.vararg, args.kwarg):
                if extra is not None and extra.annotation is not None:
                    yield extra.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def scan(name, src):
    """返回 [(行号, 违规说明)]。"""
    tree = ast.parse(src, filename=name)
    bad = []
    match_node = getattr(ast, "Match", None)   # 3.10 才有这个节点类型
    for node in ast.walk(tree):
        if match_node is not None and isinstance(node, match_node):
            bad.append((node.lineno, "match 语句（3.10+）"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in BANNED_METHODS:
            bad.append((node.lineno, "str.%s()（3.9+）" % node.func.attr))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) \
                and (isinstance(node.left, ast.Dict) or isinstance(node.right, ast.Dict)):
            bad.append((node.lineno, "dict | dict 合并（3.9+）"))
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.BitOr) \
                and isinstance(node.value, ast.Dict):
            bad.append((node.lineno, "dict |= dict（3.9+）"))
        elif isinstance(node, ast.Attribute) and node.attr == "cache" \
                and isinstance(node.value, ast.Name) and node.value.id == "functools":
            bad.append((node.lineno, "functools.cache（3.9+）"))
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id in GENERIC_BUILTINS:
            bad.append((node.lineno, "内置泛型下标 %s[...]（3.9+）" % node.value.id))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and (node.value.id, node.attr) in NEW_ATTRS:
            ver = NEW_ATTRS[(node.value.id, node.attr)]
            bad.append((node.lineno, "%s.%s（%s+）" % (node.value.id, node.attr, ver)))
        elif isinstance(node, ast.Attribute) and node.attr == BIT_COUNT:
            # 宁可误报：cli/ 里没有任何自定义 bit_count，误报成本为零，
            # 漏判成本是 3.8 上直接 AttributeError。
            bad.append((node.lineno, "bit_count（3.10+）"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) \
                and isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name) \
                and node.left.id in UNION_BUILTINS and node.right.id in UNION_BUILTINS:
            # 复用注解分支的同一条消息，不另起一种措辞
            bad.append((node.lineno, "注解里的 X | Y（3.10+）"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BANNED_MODULES:
                    bad.append((node.lineno, "import %s（3.9+）" % alias.name))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BANNED_MODULES:
                bad.append((node.lineno, "from %s import（3.9+）" % root))
            if root == "functools":
                for alias in node.names:
                    if alias.name == "cache":
                        bad.append((node.lineno, "from functools import cache（3.9+）"))
    for annotation in _annotations(tree):
        for node in ast.walk(annotation):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                bad.append((getattr(node, "lineno", 0), "注解里的 X | Y（3.10+）"))
    return sorted(bad)


# 扫描器的正样本表：(标签, 源码, 预期消息关键词)。每条都必须被 scan() 判红。
# 模块级常量而不是方法内局部变量，这样 test_sample_table_is_complete 能把条数锁住：
# 清空样本表立刻红，而不是静默变成一个什么都不验的空循环。
SAMPLES = (
    # —— 既有 6 条 ——
    ("match 语句", "def f(x):\n    match x:\n        case 1:\n            pass\n",
     "match 语句（3.10+）"),
    ("注解联合", "def f(x: int | None) -> int | None:\n    return x\n",
     "注解里的 X | Y（3.10+）"),
    ("removeprefix", "def f(s):\n    return s.removeprefix('a')\n",
     "str.removeprefix()（3.9+）"),
    ("dict 合并", "a = {'x': 1} | {'y': 2}\n", "dict | dict 合并（3.9+）"),
    ("functools.cache", "import functools\n\n\n@functools.cache\ndef f():\n    pass\n",
     "functools.cache（3.9+）"),
    ("zoneinfo", "import zoneinfo\n", "import zoneinfo（3.9+）"),
    # —— 本轮新增 9 条（报告 M1 点名的 7 类漏判 + 2 类内置泛型）——
    ("内置泛型注解", "def f(x: list[str]):\n    return x\n", "内置泛型下标 list[...]（3.9+）"),
    ("内置泛型运行时", "X = dict[str, int]\n", "内置泛型下标 dict[...]（3.9+）"),
    ("math.lcm", "import math\nmath.lcm(2, 3)\n", "math.lcm（3.9+）"),
    ("ast.unparse", "import ast\nast.unparse(t)\n", "ast.unparse（3.9+）"),
    ("random.randbytes", "import random\nrandom.randbytes(4)\n", "random.randbytes（3.9+）"),
    ("math.nextafter", "import math\nmath.nextafter(1.0, 2.0)\n", "math.nextafter（3.9+）"),
    ("itertools.pairwise", "import itertools\nitertools.pairwise(s)\n",
     "itertools.pairwise（3.10+）"),
    ("int.bit_count", "n = 5\nn.bit_count()\n", "bit_count（3.10+）"),
    ("运行时联合类型", "isinstance(x, int | str)\n", "注解里的 X | Y（3.10+）"),
)
# 反向样本：证明扫描器不是无条件判红的。
CLEAN_SAMPLE = ("3.8 干净代码", "import os\nx = os.sep\n")


class Py38CompatTest(unittest.TestCase):

    def test_cli_files_are_scanned(self):
        names = [name for name, _ in _sources()]
        self.assertIn("ui.py", names)
        self.assertIn("cathedral.py", names)

    def test_no_py39_plus_constructs(self):
        for name, src in _sources():
            with self.subTest(file=name):
                self.assertEqual(scan(name, src), [])

    def test_sample_table_is_complete(self):
        """6 既有 + 9 新增；清空样本表立刻红。"""
        self.assertEqual(len(SAMPLES), 15)

    def test_scanner_is_not_unconditionally_red(self):
        label, src = CLEAN_SAMPLE
        self.assertEqual(scan("clean.py", src), [], label)

    def test_scanner_catches_known_samples(self):
        for label, src, expected in SAMPLES:
            with self.subTest(sample=label):
                if label == "match 语句" and sys.version_info < (3, 10):
                    self.skipTest("当前解释器无法解析 match 语句")
                hits = scan("sample.py", src)
                self.assertNotEqual(hits, [], label)
                self.assertIn(expected, hits[0][1], "%s: %r" % (label, hits))


if __name__ == "__main__":
    unittest.main()
