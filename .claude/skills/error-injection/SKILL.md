---
name: error-injection
description: Thiết kế và code bước tiêm lỗi nhãn giả lập (xoá nhãn, đổi class, box giả, dịch box, co/giãn box) vào BDD100K để có đáp án đo recall cho hệ thống ưu tiên review QC. Dùng khi viết/sửa module tiêm lỗi, đổi tỉ lệ hay phân phối lỗi, đọc file injected_errors.json, thêm loại lỗi mới, hoặc khi kết quả đánh giá tốt bất thường (nghi rò rỉ từ cách tiêm lỗi).
---

# Tiêm lỗi có đáp án

Vì chưa có nhãn lỗi thật, ta tự làm hỏng một phần nhãn và giữ lại đáp án. Lỗi tiêm là **thước đo lúc phát triển**, không phải thước đo cuối — nên phân phối lỗi càng giống thực tế càng tốt, và mọi giả định phải ghi ra.

## Tham số (ở `configs/injection.yaml`)

- 15% ảnh có ít nhất 1 box bị chọn; mỗi ảnh 1–3 lỗi; mỗi object chịu tối đa 1 lỗi.
- Seed 42. Chạy lại phải ra đúng cùng một file đáp án.

## 5 loại lỗi

| Loại | Cách làm | Trọng số đánh giá | Ghi chú |
|---|---|---|---|
| `missing` | Xoá 1 box | 1.0 | Ưu tiên box nhỏ (< 30px cao), bị che, ảnh đêm — đó là loại người gán hay bỏ sót |
| `wrong_class` | Đổi class theo cặp hay nhầm | 1.0 | car↔truck, bus↔truck, pedestrian↔rider, bicycle↔motorcycle, traffic light↔traffic sign |
| `spurious` | Thêm box giả | 0.6 | Lấy kích thước từ phân phối thật của class đó; đặt ở vùng không trùng box có sẵn (IoU < 0.1). Chỉ ở tập test |
| `shift` | Dịch box một đoạn theo tỉ lệ kích thước | 0.3 | Sao cho IoU với box gốc rơi vào khoảng ~0.4–0.7 (dưới ngưỡng IoU 0.7 mặc định) |
| `resize` | Co/giãn box | 0.3 | Như trên; chỉ ở tập test |

Vì sao `spurious`/`resize` chỉ ở tập test: đây là quyết định đã chốt 07/10 — để kiểm tra GBM có khái quát sang loại lỗi chưa thấy hay không.

Sau mọi biến đổi: clip box vào 1280×720 và bỏ box có cạnh < 2px.

## Làm trên JSON gốc

Tiêm trên bản sao của `det_val.json` rồi ghi ra `data/injected/det_val_injected.json` cùng định dạng — để mọi module phía sau (loader, model so sánh, công cụ review) dùng y như dữ liệu thật, không cần nhánh code riêng.

## File đáp án `data/injected/injected_errors.json`

```json
{
  "meta": {"seed": 42, "rate": 0.15, "weights": {"missing": 1.0, "...": 0.3}, "config_hash": "..."},
  "image_order": ["...image_id theo thứ tự file gốc, dùng cho baseline thứ tự file..."],
  "splits": {"<image_id>": "train|val|test"},
  "errors": [
    {"image_id": "...", "split": "test", "type": "shift", "obj_id": "12",
     "category": "car", "box_before": [x1, y1, x2, y2], "box_after": [x1, y1, x2, y2]}
  ]
}
```

`box_before` là null với `spurious`, `box_after` là null với `missing`. Với `wrong_class` thêm `category_after`.

## Rò rỉ cần cảnh báo

Nếu `missing` ưu tiên ảnh đêm / box nhỏ thì tín hiệu "đêm" và "nhiều box nhỏ" sẽ được lợi một phần **do chính cách tiêm**. Đây không phải lý do bỏ cách tiêm thực tế, nhưng phải:

- ghi là hạn chế trong báo cáo,
- báo thêm kết quả trên phiên bản tiêm đều (uniform) để so,
- và kiểm chứng trên tập kiểm tay lỗi thật.

Tương tự: tín hiệu nào tính trên chính file nhãn (z-score kích thước) phải tính sau khi tiêm, không dùng thống kê từ nhãn sạch.

## Test tối thiểu

- Cùng seed → cùng `errors` (so hash).
- Không object nào có 2 lỗi; số ảnh có lỗi ≈ 15% (sai số ±1%).
- `spurious`/`resize` không xuất hiện ngoài split test.
- Mọi box sau tiêm nằm trong khung ảnh.
- `shift`/`resize` có IoU(box_before, box_after) < 0.7.
