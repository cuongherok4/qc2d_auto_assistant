---
name: qc-signals
description: Cách viết tín hiệu rủi ro (risk signal) cho từng ảnh trong hệ thống ưu tiên review nhãn 2D — tín hiệu hình học/ngữ cảnh (z-score kích thước, box chạm mép, box trùng, ảnh đông, điều kiện khó) và tín hiệu bất đồng với detector độc lập (YOLO/RT-DETR: thiếu box, sai class, lệch IoU). Dùng khi thêm hoặc sửa file trong src/features/, khi viết lý do tiếng Việt cho reviewer, khi so khớp dự đoán model với nhãn, hoặc khi chạy detector để sinh yolo_preds.parquet.
---

# Tín hiệu rủi ro

Mỗi tín hiệu trả lời một câu hỏi: "ảnh này có dấu hiệu gì khiến nhãn dễ sai?" và phải đưa được **bằng chứng cụ thể** để reviewer kiểm trong vài giây.

## Hợp đồng

```python
from src.features.base import SignalResult

def edge_without_truncated(objs: pd.DataFrame, cfg: dict) -> dict[str, SignalResult]:
    """Trả về {image_id: SignalResult} cho mọi ảnh (kể cả ảnh value=0)."""
```

- `value` trong [0, 1], **đã chuẩn hoá** (dùng hàm bão hoà như `min(1, x / k)` hoặc bách phân vị), để trọng số trong `configs/weights.yaml` có nghĩa so sánh được.
- `reason` tiếng Việt, **có con số và tên đối tượng**:
  - Tốt: "Box car #12 chạm mép phải nhưng không gắn truncated"
  - Tốt: "Model thấy pedestrian cao 46px (conf 0.82), nhãn không có box nào trùng"
  - Dở: "Box bất thường", "Nguy cơ cao"
- `evidence` (tuỳ chọn): list box liên quan `[{obj_id, box, note}]` — giao diện review dùng để tô màu.
- Ảnh không kích hoạt tín hiệu: `value=0`, `reason=""`. Không bỏ ảnh khỏi kết quả.
- Vectorise bằng pandas/numpy theo nhóm `image_id`; 10k ảnh phải chạy trong vài giây, không vòng for Python trên từng box nếu tránh được.

Hàm IoU, clip, khớp box có sẵn trong `scripts/geometry.py` của skill này — chép sang `src/features/geometry.py` thay vì viết lại.

## a. Tín hiệu hình học / ngữ cảnh

| Tên | Ý tưởng | Gợi ý tham số |
|---|---|---|
| `size_outlier` | z-score robust (median/MAD) của log diện tích và log tỉ lệ khung, **theo từng class** | |z| > 3 → value bão hoà |
| `edge_no_trunc` | box cách mép < 2px mà `truncated=false` | |
| `dup_same_class` | hai box cùng class IoU > 0.5 (nghi gán trùng) | |
| `overlap_cross_class` | hai box khác class IoU > 0.7 (nghi sai class) | trừ cặp hợp lệ rider–bicycle/motorcycle |
| `rare_class` | ảnh có class chiếm < 1% toàn tập | |
| `crowded` | số box theo bách phân vị 75–99 | ảnh đông → dễ sót |
| `many_tiny` | nhiều box cao < 20px | |
| `hard_condition` | đêm, mưa, tuyết, sương | |

Thống kê (median, MAD, tần suất class) **tính trên file nhãn đang được chấm** (đã tiêm lỗi), không dùng nhãn sạch — nếu không sẽ rò đáp án.

## b. Bất đồng với detector độc lập

Lý do dùng model pretrained COCO thay vì train trên BDD: model train trên nhãn có lỗi sẽ học luôn lỗi có hệ thống, nên nó "đồng ý" với chính các lỗi ta muốn bắt.

1. **Chạy model** (chạy nền, lưu `data/yolo_preds.parquet` theo quy ước trong `qc2d-project`). Ngưỡng conf thấp (0.05) khi lưu; lọc ngưỡng khi tính tín hiệu để còn tinh chỉnh.
2. **Map COCO → BDD**: person→pedestrian, bicycle, car, motorcycle, bus, train, truck, traffic light. COCO không có `rider` và `traffic sign` → **bỏ hai class này khỏi tín hiệu bất đồng** (nếu không mọi rider sẽ bị báo là sai class, mọi biển báo bị báo là box thừa).
3. **Lọc theo guideline** (nếu có spec, xem `guideline-rules`): bỏ dự đoán nhỏ hơn ngưỡng chiều cao tối thiểu trước khi so, để không báo "thiếu box" cho object không bắt buộc gán.
4. **Khớp** từng ảnh bằng Hungarian trên ma trận 1−IoU (`scipy.optimize.linear_sum_assignment`), IoU tối thiểu 0.5 để coi là cùng object. Ngưỡng IoU "box lệch" mặc định 0.7, lấy từ guideline nếu có.
5. **Sinh tín hiệu** từ kết quả khớp:
   - `model_missing_label`: dự đoán conf cao không khớp nhãn nào → nghi **thiếu box**. value tăng theo conf và kích thước.
   - `model_class_conflict`: khớp nhưng khác class, model conf cao → nghi **sai class**.
   - `model_loose_box`: khớp cùng class nhưng 0.5 ≤ IoU < 0.7 → nghi **box lệch/co giãn**.
   - `label_unsupported`: nhãn lớn, không có dự đoán nào gần → nghi **box giả**. Yếu hơn các tín hiệu trên (model hay sót vật bị che), cho trọng số thấp.

Detector: kế hoạch gốc là YOLOv8n (Ultralytics, **AGPL-3.0**); câu trả lời Q15 nghiêng về RT-DETR / mmdetection (Apache-2.0) vì tool dùng nội bộ thật. Viết phần khớp tách khỏi phần chạy model để đổi detector chỉ phải đổi một hàm sinh parquet.

Nếu `torch.cuda.is_available()` là False, chạy trên Colab rồi tải parquet về, đừng cố chạy 10k ảnh trên CPU trong vòng lặp phát triển.

## Test tối thiểu

Dựng ảnh giả bằng DataFrame nhỏ, mỗi tín hiệu ít nhất: một ca kích hoạt (kiểm `value > 0` và `reason` có con số), một ca không kích hoạt (`value == 0`), và ca ảnh không có box.
