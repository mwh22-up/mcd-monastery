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


class Py38CompatTest(unittest.TestCase):

    def test_cli_files_are_scanned(self):
        names = [name for name, _ in _sources()]
        self.assertIn("ui.py", names)
        self.assertIn("monastery.py", names)

    def test_no_py39_plus_constructs(self):
        for name, src in _sources():
            with self.subTest(file=name):
                self.assertEqual(scan(name, src), [])

    def test_scanner_catches_known_samples(self):
        samples = (
            ("match 语句", "def f(x):\n    match x:\n        case 1:\n            pass\n"),
            ("注解联合", "def f(x: int | None) -> int | None:\n    return x\n"),
            ("removeprefix", "def f(s):\n    return s.removeprefix('a')\n"),
            ("dict 合并", "a = {'x': 1} | {'y': 2}\n"),
            ("functools.cache", "import functools\n\n\n@functools.cache\ndef f():\n    pass\n"),
            ("zoneinfo", "import zoneinfo\n"),
        )
        for label, src in samples:
            with self.subTest(sample=label):
                if label == "match 语句" and sys.version_info < (3, 10):
                    self.skipTest("当前解释器无法解析 match 语句")
                self.assertNotEqual(scan("sample.py", src), [])


if __name__ == "__main__":
    unittest.main()
