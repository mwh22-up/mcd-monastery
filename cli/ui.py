#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门大教堂 · 统一渲染层
中文显示宽度对齐地基 + 麦当劳金红语义调色板 + 全部版面组件。仅用标准库，3.8+ 可跑。

契约（改这个文件前先读）：
  · 组件都是纯函数、返回 List[str]，每行显示宽度恒等于 CARD_W（tomb 自成窄宽但自身一致）；
  · 只有 out() 会打印，业务代码一律写 ui.out(ui.plaque(...), ui.panel(...))；
  · 颜色只走 C.*（降级后自动是空串），组件内不写裸转义码、不写死卡片宽度；
  · 重线框只给 plaque / tomb / banner，细线框只给 panel / rule，不混搭；
  · 框内单元格只放 ASCII + CJK，emoji 只能由调用方放在框外行首。
"""
import ctypes
import io
import os
import re
import sys
import unicodedata

# ─────────────────────────── 版面规格 ───────────────────────────

CARD_W = 54   # 卡片显示列宽：全局唯一宽度来源，组件内禁止再写死数字
PAD_X = 1     # 框内左右内边距

# D2：·(U+00B7) ×(U+00D7) ≈(U+2248) →(U+2192) █(U+2588) ░(U+2591) 以及全部框线字符
# (U+2500–257F) 的 East_Asian_Width 都是 A(ambiguous)，本项目一律按 1 列计 ——
# Windows Terminal / conhost / iTerm2 / GNOME Terminal 默认都这么渲染。极少数
# 「ambiguous 按宽」的终端下，把这里改成 True 即可整体切换。
AMBIGUOUS_AS_WIDE = False

H = dict(tl="┏", tr="┓", bl="┗", br="┛", h="━", v="┃")  # 重线：牌匾 / 安息名录碑 / 横幅
L = dict(tl="┌", tr="┐", bl="└", br="┘", h="─", v="│")  # 细线：内容框 / 分隔线
BAR_FULL = "█"
BAR_EMPTY = "░"
TRUNC_MARK = ".."   # D9：… 是 ambiguous 宽度，又恰好落在行尾最敏感处，故用 ASCII
TOMB_INSET = 6      # 安息名录碑左右各内缩的列数，使碑窄于卡片、自成一片版面

# ─────────────────────────── 宽度地基 ───────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TAIL_WS_RE = re.compile(r"[ \t]+((?:\x1b\[[0-9;]*m)*)$")
_WS_RE = re.compile(r"\s+")

# D1：自维护区间表，不用 unicodedata.east_asian_width —— 后者的 Unicode 数据版本
# 随 Python 版本漂移，会让 3.8 与 3.13 上的对齐结果不一致。区间按码位升序排列。
#
# 已知边界（实测，暂不覆盖）：U+A960 朝鲜文字母扩展 A、U+1B000 假名补充、
# U+17000 西夏文在终端按 2 列渲染，本表按 1 列计，会各差 1~2 列。
# 这三块不可能出现在麦当劳中国的营销文案里，故不进表 —— 进表要付的代价是
# 每加一个区间都要同步 _AMBIGUOUS_RANGES 的语义边界并重跑全部宽度用例。
_WIDE_RANGES = (
    (0x1100, 0x115F),      # 朝鲜文字母
    (0x2E80, 0x303E),      # CJK 部首补充 / 康熙部首 / CJK 符号标点
    (0x3041, 0x33FF),      # 平假名 片假名 注音 朝鲜文兼容 CJK 字母及月份
    (0x3400, 0x4DBF),      # CJK 扩展 A
    (0x4E00, 0x9FFF),      # CJK 基本区
    (0xA000, 0xA4CF),      # 彝文
    (0xAC00, 0xD7A3),      # 朝鲜文音节
    (0xF900, 0xFAFF),      # CJK 兼容汉字
    (0xFE10, 0xFE19),      # 竖排标点
    (0xFE30, 0xFE6F),      # CJK 兼容形式 / 小写变体
    (0xFF00, 0xFF60),      # 全角 ASCII 与全角标点
    (0xFFE0, 0xFFE6),      # 全角货币符号
    (0x1F300, 0x1FAFF),    # emoji 与象形符号
    (0x20000, 0x3FFFD),    # CJK 扩展 B 及以后
)

# AMBIGUOUS_AS_WIDE=True 时才生效的 ambiguous 区间（同样升序）
_AMBIGUOUS_RANGES = (
    (0x00B7, 0x00B7),      # ·
    (0x00D7, 0x00D7),      # ×
    (0x2026, 0x2026),      # …
    (0x2190, 0x2199),      # ← ↑ → ↓
    (0x2248, 0x2248),      # ≈
    (0x2500, 0x259F),      # 框线与方块元素（含 █ ░）
)

# safe_text 剔除区间：emoji / 象形符号 / 变体选择符 / 零宽字符（升序）
_DROP_RANGES = (
    (0x200B, 0x200F),      # 零宽空格 零宽连接符 方向标记
    (0x2600, 0x27BF),      # 杂项符号与装饰符号（含 ❤ ☕）
    (0x2B00, 0x2BFF),      # 杂项符号箭头
    (0xFE00, 0xFE0F),      # 变体选择符（❤️ 的后半截）
    (0x1F000, 0x1FAFF),    # emoji 主区
)

_MATH_LO, _MATH_HI = 0x1D400, 0x1D7FF   # 数学字母数字符号块：𝟗 → 9


def _in_ranges(cp, ranges):
    """码位是否落在升序区间表内。"""
    for lo, hi in ranges:
        if cp < lo:
            return False
        if cp <= hi:
            return True
    return False


def _char_width(cp):
    # 组合附加符号不占列（é 的 NFD 形式 e + U+0301 是 macOS 来源文本的默认形态）。
    # 跳过必须放在这里而不是 disp_width：trunc() 自己的循环也直接调 _char_width，
    # 规则加在上层会让两条算宽路径分叉。
    if unicodedata.combining(chr(cp)):
        return 0
    if AMBIGUOUS_AS_WIDE and _in_ranges(cp, _AMBIGUOUS_RANGES):
        return 2
    return 2 if _in_ranges(cp, _WIDE_RANGES) else 1


def disp_width(s):
    """字符串在等宽终端里占的列数：先剥 ANSI 转义码，CJK / 全角 / emoji 算 2 列。"""
    total = 0
    for ch in _ANSI_RE.sub("", s):
        total += _char_width(ord(ch))
    return total


def trunc(s, width):
    """按显示宽度截断并追加 '..'。结果显示宽度恒等于 width（中文被半格切断时补空格）。"""
    if width <= 0:
        return ""
    if disp_width(s) <= width:
        return s
    if width <= len(TRUNC_MARK):
        return TRUNC_MARK[:width]
    budget = width - len(TRUNC_MARK)
    kept = []
    used = 0
    has_ansi = False
    i = 0
    while i < len(s):
        m = _ANSI_RE.match(s, i)
        if m:                       # 转义码不占列宽，原样带走
            kept.append(m.group(0))
            has_ansi = True
            i = m.end()
            continue
        cw = _char_width(ord(s[i]))
        if used + cw > budget:
            break
        kept.append(s[i])
        used += cw
        i += 1
    if used < budget:
        kept.append(" " * (budget - used))
    kept.append(TRUNC_MARK)
    if has_ansi:
        kept.append(C.RESET)
    return "".join(kept)


def pad(s, width, align="left"):
    """补空格到指定显示宽度；超宽先 trunc。align 取 left / right / center（居中左少右多）。"""
    s = trunc(s, width)
    gap = width - disp_width(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def safe_text(s):
    """净化 MCP 来源字符串（D3）：整串 NFC、数学字形逐字符 NFKC、剔除 emoji/变体选择符/零宽、折叠空白。

    只给上游数据用；项目自己的中文字面量不要过这里。整串 NFKC 会把（）「」压成半角，
    所以只对 U+1D400–1D7FF 块逐字符规范化。

    整串这一次必须是 NFC，不能是 NFKC：NFC 把 e + U+0301 合成 é（宽度回到 1 列），
    而数学字形块 U+1D400–1D7FF 在 NFC 下不分解，所以 𝟗 → 9 仍由下面的逐字符
    NFKC 负责，两者顺序不冲突。
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    buf = []
    for ch in s:
        cp = ord(ch)
        if _MATH_LO <= cp <= _MATH_HI:
            buf.append(unicodedata.normalize("NFKC", ch))
            continue
        if _in_ranges(cp, _DROP_RANGES):
            continue
        buf.append(ch)
    return _WS_RE.sub(" ", "".join(buf)).strip()


def _rstrip(s):
    """剥掉行尾填充空格（保留尾部转义码），这样整宽组件能原样塞进 panel。"""
    return _TAIL_WS_RE.sub(r"\1", s)


# ─────────────────────────── 调色板 ───────────────────────────

class Palette:
    """麦当劳金红语义调色板。init() 之后属性要么是转义码、要么是空串。"""

    ATTRS = ("GOLD", "RED", "DIM", "BOLD", "RESET")

    GOLD = "\033[38;5;220m"    # 麦当劳金
    RED = "\033[38;5;196m"     # 麦当劳红
    DIM = "\033[38;5;240m"     # 辅助暗灰
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def paint(self, s, color):
        """上色；降级（color 为空串）时原样返回。"""
        if not color:
            return s
        return color + s + self.RESET

    def enable(self):
        for name in self.ATTRS:
            setattr(self, name, getattr(Palette, name))

    def disable(self):
        for name in self.ATTRS:
            setattr(self, name, "")


C = Palette()

# ─────────────────────────── 自举与降级 ───────────────────────────

_STD_OUTPUT_HANDLE = -11
_VT_FLAG = 0x0004      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
_BOOTSTRAPPED = False
COLOR_ON = False       # init() 之后记录颜色是否真的启用了


def _enable_utf8():
    """把 stdout / stderr 换成 UTF-8，Windows 控制台中文不乱码。失败静默。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            try:
                setattr(sys, name, io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace", line_buffering=True))
            except Exception:
                pass
        except Exception:
            pass


def _enable_vt():
    """Windows 下开启 VT 转义解析（本机实测原 mode 0x7，SetConsoleMode 返回 1）。失败返回 False。"""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | _VT_FLAG))
    except Exception:
        return False


def _isatty():
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def init(no_color=False):
    """自举三件套：UTF-8 → Windows VT → 调色板。幂等，main 里调一次即可。"""
    global _BOOTSTRAPPED, COLOR_ON
    if not _BOOTSTRAPPED:
        _enable_utf8()
        _BOOTSTRAPPED = True
    enabled = (not no_color
               and "NO_COLOR" not in os.environ
               and os.environ.get("TERM") != "dumb"
               and _isatty()
               and (os.name != "nt" or _enable_vt()))
    if enabled:
        C.enable()
    else:
        C.disable()
    COLOR_ON = enabled


# ─────────────────────────── 框体私有件 ───────────────────────────

def _edge(frame, kind, width=None, color=None):
    """一条横边。kind 取 top / bottom。"""
    w = CARD_W if width is None else width
    if kind == "top":
        left, right = frame["tl"], frame["tr"]
    else:
        left, right = frame["bl"], frame["br"]
    return C.paint(left + frame["h"] * (w - 2) + right, color)


def _row(frame, text, align="left", width=None, color=None):
    """一行单元格：左右竖边 + 内边距 + 对齐后的内容（超宽自动截断，绝不破框）。"""
    w = CARD_W if width is None else width
    inner = w - 2 - 2 * PAD_X
    side = C.paint(frame["v"], color)
    return side + " " * PAD_X + pad(_rstrip(text), inner, align) + " " * PAD_X + side


def _sep(frame, width=None, color=None):
    """框内分隔线，用的是本族框线字符（重线框内不混细线）。"""
    w = CARD_W if width is None else width
    inner = w - 2 - 2 * PAD_X
    side = C.paint(frame["v"], color)
    return side + " " * PAD_X + C.paint(frame["h"] * inner, color or C.DIM) + " " * PAD_X + side


# ─────────────────────────── 版面组件 ───────────────────────────

def plaque(title, subtitle=""):
    """重线牌匾：标题金色加粗居中，副标题暗灰居中。"""
    lines = [_edge(H, "top", color=C.GOLD),
             _row(H, C.paint(title, C.BOLD + C.GOLD), "center", color=C.GOLD)]
    if subtitle:
        lines.append(_row(H, C.paint(subtitle, C.DIM), "center", color=C.GOLD))
    lines.append(_edge(H, "bottom", color=C.GOLD))
    return lines


def panel(title, lines, color=None):
    """细线内容框：title 非空时作框内首行标签 + 一条分隔线；内容逐行对齐，超宽截断不换行。

    传进来的行可以是别的组件产出的整宽行（行尾填充空格会被剥掉），也可以含 ANSI。
    """
    rows = [lines] if isinstance(lines, str) else list(lines)
    body = [_edge(L, "top", color=color)]
    if title:
        body.append(_row(L, C.paint(title, color or C.GOLD), color=color))
        body.append(_sep(L, color=color))
    for row in rows:
        body.append(_row(L, row, color=color))
    body.append(_edge(L, "bottom", color=color))
    return body


def kv_table(rows, key_w=None):
    """对齐键值表：键暗灰、值原色，整行补到 CARD_W。key_w 缺省取最大键宽。"""
    pairs = [(str(k), str(v)) for k, v in rows]
    if key_w is None:
        key_w = max([disp_width(k) for k, _ in pairs] or [0])
    lines = []
    for key, value in pairs:
        lines.append(pad(pad(C.paint(key, C.DIM), key_w) + "  " + value, CARD_W))
    return lines


def bar(value, maxv, width=10, color=None):
    """条形图字符串（不打印）。value<=0 得全空条，超过 maxv 也只画满。"""
    try:
        top = float(maxv)
        ratio = float(value) / top if top > 0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = 0.0
    filled = max(0, min(width, int(round(ratio * width))))
    return C.paint(BAR_FULL * filled + BAR_EMPTY * (width - filled), color)


def tomb(lines, epitaph=""):
    """安息名录碑：重线窄框 + 碑文居中，左右各内缩 TOMB_INSET 列，自成一片版面。"""
    width = CARD_W - 2 * TOMB_INSET
    box = [_edge(H, "top", width, C.DIM)]
    for line in lines:
        box.append(_row(H, C.paint(_rstrip(line), C.DIM), "center", width, C.DIM))
    if epitaph:
        box.append(_sep(H, width, C.DIM))
        box.append(_row(H, C.paint(epitaph, C.DIM), "center", width, C.DIM))
    box.append(_edge(H, "bottom", width, C.DIM))
    return [pad(" " * TOMB_INSET + line, CARD_W) for line in box]


def seal(text):
    """右下蜡封落款：单行红色右对齐到 CARD_W。"""
    return [pad(C.paint(text, C.RED), CARD_W, "right")]


def rule(char="─", color=None):
    """整宽分隔线。"""
    step = disp_width(char) or 1
    return [pad(C.paint(char * (CARD_W // step), color), CARD_W)]


def divider():
    """rule('─', C.DIM) 的语义别名。"""
    return rule(L["h"], C.DIM)


def banner(text, sub="", tone="warn"):
    """醒目横幅（--demo 诚信声明用）：重线框 + 色调标题。tone 取 warn / info / dim。"""
    color = {"warn": C.RED, "info": C.GOLD, "dim": C.DIM}.get(tone, C.RED)
    lines = [_edge(H, "top", color=color),
             _row(H, C.paint(text, C.BOLD + color), "center", color=color)]
    if sub:
        lines.append(_sep(H, color=color))
        lines.append(_row(H, C.paint(sub, color), "center", color=color))
    lines.append(_edge(H, "bottom", color=color))
    return lines


def bullet(items, mark="·"):
    """列表项：统一前缀 + 悬挂缩进。整行补到 CARD_W，可直接塞进 panel。"""
    head = mark + " "
    hang = " " * disp_width(head)
    lines = []
    for item in items:
        parts = str(item).split("\n")
        lines.append(pad(head + parts[0], CARD_W))
        for extra in parts[1:]:
            lines.append(pad(hang + extra, CARD_W))
    return lines


def blank():
    """一行空行。"""
    return [""]


# ─────────────────────────── 唯一出口 ───────────────────────────

def out(*blocks):
    """接受 str 或 List[str]，扁平化后逐行打印。全文件唯一的打印点。"""
    for block in blocks:
        rows = [block] if isinstance(block, str) else list(block)
        for line in rows:
            print(line)
