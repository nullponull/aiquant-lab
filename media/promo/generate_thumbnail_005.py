"""フラッグシップ記事 #005 番外編 サムネ生成

連載「AIで投資の壁を越える」第7の壁シリーズの番外編サムネイル。
note (1280x670) + X (1200x675) 両対応。
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# サイズ仕様（note 推奨）
W, H = 1280, 670

# AIコンパス連載カラーパレット (eyecatch_design_brief.md 準拠)
COLOR_BG = (15, 23, 42)         # #0F172A 深いネイビー
COLOR_BG2 = (30, 41, 59)        # #1E293B ダークスレート
COLOR_ACCENT = (6, 182, 212)    # #06B6D4 シアン
COLOR_WARN = (245, 158, 11)     # #F59E0B アンバー
COLOR_TEXT = (248, 250, 252)    # #F8FAFC オフホワイト
COLOR_DIM = (148, 163, 184)     # #94A3B8 グレー


def get_font(size: int, bold: bool = True):
    """日本語フォント取得"""
    paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
    ]
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_gradient_bg(img, color1, color2):
    """上→下のグラデーション背景"""
    draw = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def draw_grid_overlay(draw):
    """微細なグリッド線（テック感）"""
    grid_color = (40, 50, 70)
    for x in range(0, W, 40):
        draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
    for y in range(0, H, 40):
        draw.line([(0, y), (W, y)], fill=grid_color, width=1)


def make_thumbnail(output_path: str, variant: str = "note"):
    """サムネ生成

    variant: "note" (1280x670) or "x" (1200x675)
    """
    global W, H
    if variant == "x":
        W, H = 1200, 675
    else:
        W, H = 1280, 670

    img = Image.new("RGB", (W, H), COLOR_BG)
    draw_gradient_bg(img, COLOR_BG, COLOR_BG2)
    draw = ImageDraw.Draw(img)
    draw_grid_overlay(draw)

    # === シリーズタグ（左上）===
    f_tag = get_font(22, bold=False)
    draw.text((60, 50), "// AICOMPASS / AIで投資の壁を越える", fill=COLOR_ACCENT, font=f_tag)

    # === エピソード番号バッジ（左上、タグの下）===
    f_ep_label = get_font(18, bold=False)
    f_ep_num = get_font(56, bold=True)

    badge_y = 90
    draw.text((60, badge_y), "番外編", fill=COLOR_DIM, font=f_ep_label)
    draw.text((60, badge_y + 30), "第7の壁", fill=COLOR_WARN, font=f_ep_num)

    # === メインタイトル（中央〜下半分）===
    f_title = get_font(56, bold=True)
    f_title_sub = get_font(40, bold=True)

    title_lines = [
        "2,245人の行動データで",
        "投資家ペルソナを再現したら",
    ]
    title_y = 210
    for i, line in enumerate(title_lines):
        draw.text((60, title_y + i * 70), line, fill=COLOR_TEXT, font=f_title)

    # サブタイトル（黄色強調）
    f_sub = get_font(36, bold=True)
    sub_y = title_y + 70 * len(title_lines) + 20
    # 「AIには見えない」を強調
    sub_line = "AIには絶対に見えない"
    draw.text((60, sub_y), sub_line, fill=COLOR_WARN, font=f_sub)

    sub_line2 = "第7の壁が浮かび上がった"
    draw.text((60, sub_y + 50), sub_line2, fill=COLOR_TEXT, font=f_sub)

    # === 右側の数字ハイライト（実験規模） ===
    # 大きな数字
    f_big = get_font(120, bold=True)
    f_big_label = get_font(20, bold=False)

    big_x = W - 360
    big_y = 200
    draw.text((big_x, big_y), "2,245", fill=COLOR_ACCENT, font=f_big)
    draw.text((big_x, big_y + 135), "ペルソナを実装で検証", fill=COLOR_DIM, font=f_big_label)

    # 装飾ライン
    draw.rectangle([big_x, big_y + 170, big_x + 280, big_y + 172], fill=COLOR_ACCENT)

    # === 下部の footer ===
    f_foot = get_font(20, bold=False)
    foot_y = H - 60
    draw.text((60, foot_y), "ai-media.co.jp · note @ai_compass_media · GitHub: nullponull/aiquant-lab", fill=COLOR_DIM, font=f_foot)

    # === 価格バッジ（右下）===
    f_price = get_font(24, bold=True)
    price_text = "¥3,000 有料記事"
    bbox = draw.textbbox((0, 0), price_text, font=f_price)
    pw = bbox[2] - bbox[0]
    ph = bbox[3] - bbox[1]
    px = W - pw - 90
    py = H - 100
    # バッジ背景
    draw.rectangle([px - 16, py - 8, px + pw + 16, py + ph + 16], fill=COLOR_WARN)
    draw.text((px, py), price_text, fill=COLOR_BG, font=f_price)

    img.save(output_path, "PNG", quality=95, optimize=True)
    print(f"  ✓ Generated: {output_path} ({W}x{H})")


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    make_thumbnail(str(out_dir / "005_wall7_note.png"), variant="note")
    make_thumbnail(str(out_dir / "005_wall7_x.png"), variant="x")
    print("\n完了。note記事ヘッダーとX投稿カードに使用してください。")
