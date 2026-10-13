# Báo cáo Sơn · 13/10/2026

**Nhánh:** `feat/son-viz` → PR vào `develop`

```
Done:      Vẽ box kiểm tay (src/viz/draw.py + tests/test_viz.py); đọc lại detector.py + model_disagreement.py,
           chạy thử trên 10k ảnh: tìm ra 2 lỗi (mục 2)
Doing:     Kiểm chứng 2 lỗi trên dự đoán RT-DETR (~0%); chuẩn bị kiểm tay 150 ảnh cùng Long
Blocked:   Cần file RT-DETR data/yolo_preds.parquet của anh Cường (Drive) để đo lại mục 2
Link:      PR feat/son-viz
Questions: Xem mục 4
```

## 1. Vẽ box để kiểm tay (`src/viz/draw.py`)

`draw_image(image_id, objects, preds=None, evidence=None, out_dir=None, images_dir=None)` → `reports/viz/<image_id>.jpg`.

| Màu | Nguồn | Chữ cạnh box |
|---|---|---|
| Xanh lá | Nhãn | class + chiều cao px |
| Xanh dương | Dự đoán (`yolo_preds.parquet`) | class + conf + chiều cao px |
| Đỏ, nét dày | Evidence của `SignalResult` / `evidence_<version>.jsonl` | `note` |

Font DejaVu Sans (đi kèm matplotlib) nên hiện đủ dấu tiếng Việt, không thêm dependency. Test: `tests/test_viz.py` kiểm đủ 3 màu đúng chỗ và không vẽ box của ảnh khác.

## 2. Đọc lại detector và 4 tín hiệu bất đồng

Cách thử: tạo lỗi giả trên 500 ảnh ngẫu nhiên (seed 42), mỗi ảnh 1 box car/pedestrian/truck/bus cao ≥ 30px; dự đoán dùng **YOLOv8n** em chạy trước khi biết anh đã chạy RT-DETR (237.928 box / 10k ảnh, 67 giây trên GTX 1650). Hai lỗi dưới đây nằm ở logic khớp nên dự kiến vẫn đúng với RT-DETR, nhưng cần đo lại.

### Lỗi 1: `model_loose_box` không bắt box lệch nhiều

`_match` chỉ ghép cặp khi IoU ≥ `min_iou` (0.5), sau đó box lệch là cặp có IoU trong [0.5, 0.7). Box dịch 1/3 bề rộng có IoU ≈ 0.48 → không ghép → không bao giờ bị báo lệch (cũng không bị báo thiếu vì `missing_max_iou` 0.3 chặn).

| Dịch box | Box lỗi có trong evidence | value > 0.3: ảnh lỗi | value > 0.3: ảnh sạch |
|---|---|---|---|
| 20% bề rộng | 36% | 44% | 15% |
| 35% bề rộng | **2%** | 16% | 15% |

Bản em thử: riêng box lệch ghép với IoU ≥ 0.3 → dịch 35% bắt được 54% (ảnh sạch 18%). Đề xuất thêm `loose_min_iou: 0.3` và cho `model_loose_box` ghép lại với ngưỡng đó; giữ 0.5 cho 3 tín hiệu còn lại.

### Lỗi 2: capo xe mình bị báo "thiếu box"

Detector hay nhận capo xe mình là `car` (box chạm đáy ảnh, rộng gần hết ảnh). BDD không gán nhãn xe mình, nên đây luôn là báo nhầm: **38/686 box báo thiếu (6%)**. Trong nhãn chỉ có 8 box chạm đáy và rộng ≥ 640px, nên lọc dự đoán `y2 ≥ 715 và rộng ≥ 640` gần như không mất gì. Ví dụ: `b1e0c01d-dd9e6e2f`.

### Điểm tốt đã xác nhận

- `model_class_conflict` bắt được **lỗi thật trong nhãn BDD**: ảnh `ba01e424-d3effc2d` có 4 người đi bộ bị gán `car`.
- Trên lỗi giả: xoá box → `model_missing_label` bắt ~48%; đổi class → `model_class_conflict` ~44%; box giả → `label_unsupported` ~85% (số từ bản của em, cùng ý tưởng; sẽ đo lại trên bản của anh).

## 3. Dữ liệu trên máy em

- Ảnh: bản Kaggle `bdd100k-yolo` (10.000 ảnh val), symlink vào `data/bdd100k/images/100k/val`.
- Nhãn: BDD100K **bản 2018, mỗi ảnh một JSON**; em gộp thành `data/bdd100k/labels/det_20/det_val.json` (10.000 ảnh, 185.578 box). Cần so với bản HuggingFace anh dùng xem có khớp không.

## 4. Câu hỏi

1. **Anh Cường:** anh đồng ý sửa 2 lỗi ở mục 2 không? Em mở PR nhỏ cho `model_disagreement.py` hay anh sửa?
2. **Anh Cường:** cho em link Drive file RT-DETR `yolo_preds.parquet` để đo lại mục 2.
3. **Long:** kiểm tay 150 ảnh: dùng `draw_image` để xuất ảnh cho phiếu kiểm, mình chốt mẫu phiếu hôm nay được không?

## 5. Hạn chế

- Số liệu mục 2 đo trên dự đoán YOLOv8n, không phải RT-DETR đang dùng trong pipeline.
- Chữ trên box đè nhau ở ảnh đông object.
