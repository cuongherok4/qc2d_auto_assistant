"""Vẽ box lên ảnh để kiểm tay. Phụ trách: Sơn. Hướng dẫn: skill `bdd100k-data` mục "Vẽ box để kiểm tay".

Tô màu theo nguồn: nhãn gốc / dự đoán model / box nghi vấn (từ evidence). Ghi class + chiều cao px
cạnh box. Ảnh xuất ra reports/viz/ (không commit).
"""

from __future__ import annotations

from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from src import config

COLORS = {"label": (0, 200, 0), "pred": (0, 140, 255), "suspect": (255, 40, 40)}
# DejaVu Sans đi kèm matplotlib, có đủ dấu tiếng Việt
FONT = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 12)


def draw_image(
    image_id: str, objects, preds=None, evidence=None, out_dir: Path | None = None,
    images_dir: Path | None = None,
) -> Path:
    """objects/preds: bảng object-level và quy ước 2; evidence: list {obj_id, box, note} từ SignalResult."""
    img = Image.open(Path(images_dir or config.path("images_dir")) / f"{image_id}.jpg").convert("RGB")
    d = ImageDraw.Draw(img)

    def box(xyxy, color, text, width=2):
        x1, y1, x2, y2 = map(float, xyxy)
        d.rectangle((x1, y1, x2, y2), outline=color, width=width)
        d.text((x1, max(0.0, y1 - 14)), text, fill=color, font=FONT)

    for r in objects[objects["image_id"] == image_id].itertuples(index=False):
        box((r.x1, r.y1, r.x2, r.y2), COLORS["label"], f"{r.category} {r.y2 - r.y1:.0f}px")
    if preds is not None:
        for r in preds[preds["image_id"] == image_id].itertuples(index=False):
            box((r.x1, r.y1, r.x2, r.y2), COLORS["pred"], f"{r.category} {r.conf:.2f} {r.y2 - r.y1:.0f}px")
    for ev in evidence or []:
        box(ev["box"], COLORS["suspect"], ev.get("note", ""), width=3)

    out_dir = Path(out_dir or config.path("reports_dir") / "viz")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{image_id}.jpg"
    img.save(out, quality=90)
    return out
