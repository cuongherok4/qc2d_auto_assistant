"""Vẽ box kiểm tay trên ảnh giả: đủ 3 nguồn (nhãn, dự đoán, evidence) và ảnh xuất ra đúng chỗ."""
import pandas as pd
from PIL import Image

from src.contracts import PRED_COLS
from src.viz.draw import COLORS, draw_image


def test_draw_image(tmp_path):
    Image.new("RGB", (1280, 720)).save(tmp_path / "a.jpg")
    objects = pd.DataFrame([
        {"image_id": "a", "category": "car", "x1": 100, "y1": 100, "x2": 200, "y2": 200},
        {"image_id": "b", "category": "car", "x1": 500, "y1": 500, "x2": 600, "y2": 600},  # ảnh khác
    ])
    preds = pd.DataFrame([["a", 300, 300, 400, 400, "pedestrian", 0.9]], columns=PRED_COLS)
    evidence = [{"obj_id": "1", "box": [700, 100, 800, 200], "note": "nghi thiếu box"}]

    out = draw_image("a", objects, preds, evidence, out_dir=tmp_path / "viz", images_dir=tmp_path)

    img = Image.open(out).convert("RGB")
    assert out == tmp_path / "viz" / "a.jpg" and img.size == (1280, 720)

    def near(px, color):  # JPEG làm lệch màu vài đơn vị
        return all(abs(a - b) < 60 for a, b in zip(px, color, strict=True))

    assert near(img.getpixel((150, 100)), COLORS["label"])
    assert near(img.getpixel((350, 300)), COLORS["pred"])
    assert near(img.getpixel((750, 100)), COLORS["suspect"])
    assert img.getpixel((550, 500)) == (0, 0, 0)
