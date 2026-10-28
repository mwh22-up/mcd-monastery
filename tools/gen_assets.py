#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦门大教堂 · 视觉资产生成器（构建期工具，非运行时依赖）

================================================================================
这个脚本不是跑 CLI 所必需的。`cli/` 与 `tests/` 永不 import 它。
大教堂 CLI 本身零依赖、纯标准库；本工具额外需要 Pillow，且需要一个图像生成
网关的凭证。资产已生成并提交在 assets/ 下，使用者无需运行本脚本。
================================================================================

用途：生成 README 用的全套视觉资产，并把体积压到可进仓库的程度。

设计要点
--------
1. 样式统一靠机制而非人工挑片：所有 prompt 共用同一段 STYLE 常量，锁死三色
   调色板、材质、构图与"禁止任何文字/字母/商标/人脸"。
2. 凭证只从环境变量读取，不接受命令行传参，不写入任何文件：
       AI_GATEWAY_API_KEY   必填
       AI_GATEWAY_BASE_URL  可选，默认测试网关
       AI_IMAGE_MODEL       可选，默认 gpt-image-2
3. 原图落在 assets/.raw/（已被 .gitignore 排除），仓库只收优化后的 WebP。
4. OG 社交卡的文字不交给图像模型画（中文必糊），用 Pillow 以本机 CJK 字体
   合成，保证文字边缘清晰。

用法
----
    python tools/gen_assets.py                # 生成缺失的资产
    python tools/gen_assets.py --force        # 全部重新生成
    python tools/gen_assets.py --only hero    # 只生成某一个
    python tools/gen_assets.py --optimize-only  # 跳过调用，只用已有原图重新压缩
"""
import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - 构建期工具，缺库时给出明确指引
    sys.stderr.write(
        "需要 Pillow：pip install Pillow\n"
        "（这是构建期工具的依赖，大教堂 CLI 本身零依赖）\n"
    )
    raise SystemExit(2)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")
RAW = os.path.join(ASSETS, ".raw")

BASE_URL = os.environ.get("AI_GATEWAY_BASE_URL", "https://ai-gateway-test.mcdchina.net")
MODEL = os.environ.get("AI_IMAGE_MODEL", "gpt-image-2")

WEBP_QUALITY = 88

# 通栏图裁切时在主体上方留出的空白高度，占窗口高度的比例。
# 不再使用手调的绝对偏移量：那种做法换一张图就失效 —— 实测过一次，
# 按东方寺庙版校准出来的偏移量，换成哥特教堂版后顶部空出大片天空、
# 底部却把拱基切掉了。现在改为按内容自动取景（见 _content_top）。
BANNER_HEADROOM = 0.03

# 判定「这一行有内容」的阈值：与背景色的曼哈顿距离，以及非背景像素占比。
CONTENT_TOLERANCE = 45
CONTENT_MIN_DENSITY = 0.02
CONTENT_SAMPLE_STEP = 4

# ── 统一视觉语言 ──────────────────────────────────────────────────────────
# 每个 prompt 都会拼上这段。改这里等于整套资产换皮，不会出现半新半旧。
STYLE = (
    "Flat vector illustration, minimal geometric construction, bold clean silhouettes. "
    "Strict three-colour palette: warm golden yellow, deep crimson red, soft cream. "
    "Gothic cathedral architecture: pointed lancet arches, circular rose window tracery, "
    "ribbed stone vaulting, leaded stained-glass panels, candlelight. "
    "Subtle carved-stone texture, matte finish, soft even ambient light, "
    "no gradients beyond gentle shading. "
    "Symmetrical centered composition with generous negative space, solemn reverent mood. "
    "ABSOLUTELY NO text, no letters, no numbers, no calligraphy, no logos, "
    "no brand marks, no trademarks, no human faces, no photorealism, no 3D render. "
    # 刻意排除真实宗教符号：本项目是建筑美学意义上的「教堂」，
    # 不做任何具体信仰的礼仪戏仿。
    "ABSOLUTELY NO crosses, no crucifixes, no saints, no icons, "
    "no symbols of any real-world religion."
)

# 三种框型。同一套 STYLE 下用框型区分资产类别。
FRAME_BANNER = (
    "Wide horizontal banner composition, panoramic, the subject centered and "
    "symmetrical, cream sky, deep crimson ground band. "
)
# 环宽与越界约束固化在框型里，不再依赖单张 prompt 补救。
# 教训：上一版只在框型里写了「thin golden ring」，结果其中一枚出了明显的
# 重边、云纹越出环外、底色还带放射线肌理，并排时脱开家族，得单独重出一次。
FRAME_MEDALLION = (
    "Single centered object inside a circular medallion. The ring frame must be a thin "
    "plain hairline of uniform width, exactly like a simple drawn circle. Nothing may "
    "extend beyond or overlap the ring. The field behind the object is flat plain deep "
    "crimson with no radiating lines and no texture pattern. Cream outside the ring. "
)
FRAME_BADGE = (
    "Heraldic shield-shaped badge medallion, thin golden border, deep crimson field, "
    "single centered emblem, cream background outside the shield. "
)

CATHEDRAL_SUBJECT = (
    "A stone cathedral facade on a stepped platform, its twin tall pointed lancet "
    "arches echoing the shape of a letter M without ever drawing a letter, "
    "a large circular rose window with radiating stone tracery set above and between "
    "the two arches, a slender spire on the roof ridge, "
    "a lit candle sconce glowing on either side."
)

# ── 资产清单 ──────────────────────────────────────────────────────────────
# (名称, 生成尺寸, 目标展示尺寸, 框型, 主体描述)
MANIFEST = [
    # 门面横幅。
    # 裁成 1280×740 而非原生 3:2：满宽铺开时 3:2 在 GitHub 正文宽度下约占
    # 600px 高，会把 tagline、badge 和对评委最关键的 `--demo` 钩子命令挤到
    # 折叠线以下。裁后渲染高度约 520px。
    # 高度不能再压：实测哥特立面从尖塔顶到基座底跨 856px（原图 1024 高），
    # 660 的窗口只给 792px，装不下，必然要切塔尖或切拱基 —— 都破了「M」形。
    # 740 对应窗口 888px，刚好把整座立面连基座一起装进去。
    # 垂直位置由 _content_top 自动取景，不写死偏移量。
    ("hero", "1536x1024", (1280, 740), FRAME_BANNER, CATHEDRAL_SUBJECT),

    # 五大日课徽记。环宽与越界约束已固化在 FRAME_MEDALLION 里，
    # 各条主体描述不再重复交代，只写画什么。
    ("ritual-matins", "1024x1024", (360, 360), FRAME_MEDALLION,
     "A sunrise disc seen through a large circular rose window, three thin radiating "
     "light beams above it, a small bell hanging below the window."),
    ("ritual-grace", "1024x1024", (360, 360), FRAME_MEDALLION,
     "A wide shallow offering bowl on a small stone pedestal, three round coin-like "
     "discs floating in an arc above the bowl."),
    ("ritual-relics", "1024x1024", (360, 360), FRAME_MEDALLION,
     "A tiered stone niche holding three small reliquary caskets, a short stack of "
     "round coin-like discs beside them, a single row of short candle stubs below."),
    ("ritual-vigil", "1024x1024", (360, 360), FRAME_MEDALLION,
     "A tall lit candle standing beside an hourglass, both under a pointed lancet "
     "arch, a few grains falling inside the hourglass, melted wax pooling at the base."),
    # 教训沿用：东方版的册页首版画得过大且偏浅色，破了「金器落在绛红底」的
    # 家族规律，得单独重出一次。故此处显式强调 small / golden / 大片绛红留白。
    ("ritual-ledger", "1024x1024", (360, 360), FRAME_MEDALLION,
     "A small golden open ledger book resting on a stone lectern, a few rows of carved "
     "tally marks on its pages, a slender golden quill laid diagonally across it, "
     "a tiny wax seal beside it. The book is golden, compact, and sits on a large deep "
     "crimson field with plenty of crimson space around it."),

    # 五级段位盾徽。由低到高逐级更繁复，这是晒图动机的来源。
    ("badge-1-catechumen", "1024x1024", (200, 200), FRAME_BADGE,
     "A single slender lit candle standing under a plain pointed lancet arch."),
    ("badge-2-acolyte", "1024x1024", (200, 200), FRAME_BADGE,
     "A small offering bowl with one tall slender candle behind it, "
     "a plain pointed lancet arch above."),
    ("badge-3-knight", "1024x1024", (200, 200), FRAME_BADGE,
     "Two crossed slender golden batons, a small pointed lancet arch above them, "
     "three dots in a row beneath."),
    ("badge-4-bishop", "1024x1024", (200, 200), FRAME_BADGE,
     "A tall stack of three round tiered discs forming a tower, crowned by a tall "
     "pointed mitre-like arch, two slender side pinnacles."),
    ("badge-5-highpriest", "1024x1024", (200, 200), FRAME_BADGE,
     "A radiant sun disc with long aura rays above a large circular rose window "
     "flanked by twin pointed lancet arches, ornate Gothic tracery border, "
     "the most elaborate emblem of the set."),

    # OG 社交卡背景：下三分之一留白给 Pillow 合成文字
    ("og-bg", "1536x1024", (1280, 640), FRAME_BANNER,
     CATHEDRAL_SUBJECT + " The lower third of the image is a large empty calm cream "
     "area with nothing in it, reserved as blank space."),
]

# OG 卡文案（由 Pillow 绘制，不交给图像模型）
OG_TITLE = "麦门大教堂"
OG_LATIN = "MCD  CATHEDRAL"
OG_TAGLINE = "每天 30 秒，替你抢救正在过期的券和积分"

CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

GOLD = (235, 173, 46)
CRIMSON = (150, 28, 32)
CREAM = (247, 241, 227)


def _api_key():
    key = os.environ.get("AI_GATEWAY_API_KEY", "")
    if not key:
        raise SystemExit(
            "AI_GATEWAY_API_KEY 未设置。本脚本只从环境变量读取凭证，"
            "不接受命令行传参，也不会把凭证写入任何文件。"
        )
    return key


def _ssl_ctx():
    # 测试网关使用自签证书，与官方 MCP 通道无关，仅影响本构建期工具。
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def generate(name, size, frame, subject, key):
    """调用网关生成一张原图，存入 assets/.raw/。返回路径或 None。"""
    prompt = frame + subject + " " + STYLE
    payload = {"model": MODEL, "prompt": prompt, "size": size, "n": 1}
    req = urllib.request.Request(
        BASE_URL + "/v1/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=300) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = exc.read().decode("utf-8")[:300]
                except Exception:
                    pass
            sys.stderr.write("  第 %d 次失败 %s: %s %s\n" % (attempt, name, exc, detail))
            if attempt == 2:
                return None
            time.sleep(3)

    b64 = (obj.get("data") or [{}])[0].get("b64_json")
    if not b64:
        sys.stderr.write("  %s 无 b64_json，返回键=%s\n" % (name, sorted(obj.keys())))
        return None
    path = os.path.join(RAW, name + ".png")
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


# 需要镂空米白底的资产：圆形徽记与盾形徽章。
# 起因：不透明米白方底在 GitHub 亮色模式下给每枚徽记加一圈米白方边，
# 在暗色模式下直接变成深色页面上的米白瓷砖。横幅与 OG 卡是整幅构图，不镂空。
ALPHA_CUTOUT = {
    "ritual-matins", "ritual-grace", "ritual-relics",
    "ritual-vigil", "ritual-ledger",
    "badge-1-catechumen", "badge-2-acolyte", "badge-3-knight",
    "badge-4-bishop", "badge-5-highpriest",
}

# 泛洪容差。米白底与金色描边在蓝色通道上差了近 180，40 的容差不会越过描边。
FLOOD_THRESH = 40

# 泛洪哨兵色。取纯洋红，确保不与三色调色板里的任何颜色相撞。
_SENTINEL = (255, 0, 255)


def _cutout_alpha(im):
    """把四角连通的背景变透明。

    用「四角泛洪」而不是几何蒙版：圆徽是正圆，但五枚盾徽的外轮廓各不相同
    （五级徽章越高越华丽，边框形状也不一样），固定蒙版必然啃掉描边或留下月牙。
    泛洪沿实际描边走，与形状无关。且只填四角连通的区域，
    图案内部的浅色区域不会被误伤。
    """
    probe = im.copy()
    w, h = probe.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(probe, xy, _SENTINEL, thresh=FLOOD_THRESH)

    # 掩膜建在副本上再贴回原图：直接在原图上泛洪的话，
    # 羽化会把哨兵色的洋红混进边缘像素。
    mask = Image.new("L", probe.size, 255)
    mask.putdata([0 if px == _SENTINEL else 255 for px in probe.getdata()])
    mask = mask.filter(ImageFilter.GaussianBlur(0.6))  # 羽化约 1px 去锯齿

    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def optimize(name, target):
    """裁切 + 镂空 + 缩放 + 转 WebP，落到 assets/。返回字节数。

    顺序是先在 1024 原图上镂空再缩放：反过来在小图上抠，
    金环描边只有一两个像素宽，边缘会糊。
    """
    src = os.path.join(RAW, name + ".png")
    im = Image.open(src).convert("RGB")
    if name in ("hero", "og-bg"):
        im = _crop_to_ratio(im, target[0] / float(target[1]))
    if name in ALPHA_CUTOUT:
        im = _cutout_alpha(im)
    im = im.resize(target, Image.LANCZOS)
    out = os.path.join(ASSETS, name + ".webp")
    im.save(out, "WEBP", quality=WEBP_QUALITY, method=6)
    return os.path.getsize(out)


def _content_top(im):
    """返回第一行「有内容」的 y 坐标，背景色取左上角像素。

    用来替代手调的裁切偏移量。主体在画面里的垂直位置每次生成都不一样，
    写死偏移量必然在换图后切错地方。
    """
    rgb = im.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    bg = px[2, 2]
    cols = range(0, w, CONTENT_SAMPLE_STEP)
    need = len(cols) * CONTENT_MIN_DENSITY
    for y in range(0, h, CONTENT_SAMPLE_STEP):
        n = 0
        for x in cols:
            r, g, b = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > CONTENT_TOLERANCE:
                n += 1
                if n > need:
                    return y
    return 0


def _crop_to_ratio(im, ratio):
    """裁到指定长宽比，竖向按内容取景。

    正常情况下把主体顶部连同一小段空白一起框进来。窗口装不下全部内容时
    （实测哥特立面含细塔尖跨约 970px，而 1280×740 的窗口只有 888px），
    下面那行 min() 会把窗口夹成底部对齐，于是**优先保住基座**，
    细塔尖允许出框 —— 通栏横幅里主体顶端出框是可接受的构图，
    而基座被切断会让整座建筑显得悬空。

    注意这条优先级是 min() 夹取的结果，不是额外判断。改动夹取逻辑
    会连带改变「装不下时保哪头」的行为。
    """
    w, h = im.size
    if w / float(h) > ratio:
        new_w = int(h * ratio)
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = int(w / ratio)
    top = _content_top(im) - int(new_h * BANNER_HEADROOM)
    top = max(0, min(top, h - new_h))
    return im.crop((0, top, w, top + new_h))


def _font(size):
    for path in CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    raise SystemExit("找不到可用的中文字体，无法合成 OG 卡文字")


def build_og_card():
    """把文字用 Pillow 画到 og-bg 上，输出 PNG。

    GitHub 的 Social preview 只接受 PNG/JPG，所以这张不转 WebP。
    文字由矢量字体渲染，不经过图像模型，边缘清晰可读。
    """
    src = os.path.join(RAW, "og-bg.png")
    im = Image.open(src).convert("RGB")
    im = _crop_to_ratio(im, 1280 / 640.0).resize((1280, 640), Image.LANCZOS)

    draw = ImageDraw.Draw(im, "RGBA")
    # 底部压一条米白带承载文字。带高控制在 204px：再高就会吃掉教堂立面的双尖拱，
    # 而双拱正是「M」形的识别点。
    draw.rectangle([(0, 436), (1280, 640)], fill=CREAM + (242,))
    draw.line([(0, 436), (1280, 436)], fill=GOLD, width=3)

    f_title = _font(68)
    f_latin = _font(22)
    f_tag = _font(27)

    def centered(text, font, y, fill):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((1280 - (box[2] - box[0])) / 2 - box[0], y), text, font=font, fill=fill)

    centered(OG_TITLE, f_title, 452, CRIMSON)
    centered(OG_LATIN, f_latin, 536, GOLD)
    centered(OG_TAGLINE, f_tag, 572, (90, 70, 50))

    # 平面插画 + 矢量文字，调色板量化后体积降一个数量级，文字边缘无肉眼可见损失。
    # 关掉抖动，否则大色块会出现噪点。
    out = os.path.join(ASSETS, "og-card.png")
    im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE).save(
        out, "PNG", optimize=True
    )
    return os.path.getsize(out)


def main():
    ap = argparse.ArgumentParser(description="生成麦门大教堂视觉资产")
    ap.add_argument("--force", action="store_true", help="已存在也重新生成")
    ap.add_argument("--only", metavar="NAME", help="只处理指定资产")
    ap.add_argument("--optimize-only", action="store_true",
                    help="不调用网关，只用已有原图重新压缩")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    key = None if args.optimize_only else _api_key()

    items = [m for m in MANIFEST if not args.only or m[0] == args.only]
    if not items:
        raise SystemExit("没有匹配的资产名：%s" % args.only)

    print("模型 %s  输出 %s" % (MODEL, ASSETS))
    total = 0
    failed = []
    for name, size, target, frame, subject in items:
        raw_path = os.path.join(RAW, name + ".png")
        if not args.optimize_only and (args.force or not os.path.exists(raw_path)):
            if generate(name, size, frame, subject, key) is None:
                failed.append(name)
                continue
        if not os.path.exists(raw_path):
            sys.stderr.write("  缺少原图，跳过 %s\n" % name)
            failed.append(name)
            continue
        nbytes = optimize(name, target)
        total += nbytes
        print("  %-20s %-10s %4d KB" % (name, "%dx%d" % target, nbytes // 1024))

    if any(m[0] == "og-bg" for m in items) and "og-bg" not in failed:
        nbytes = build_og_card()
        total += nbytes
        print("  %-20s %-10s %4d KB" % ("og-card.png", "1280x640", nbytes // 1024))

    print("\n仓库内资产合计 %d KB" % (total // 1024))
    if failed:
        print("失败：%s" % ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
