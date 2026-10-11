---
name: risk-scoring
description: Gộp các tín hiệu rủi ro thành điểm 0–100 cho mỗi ảnh và xuất hàng đợi review xếp hạng (ranked_queue) kèm 3 lý do — từ rule có trọng số, rule + detector, đến GBM (LightGBM) học từ verdict của reviewer, kể cả vòng học lại theo đợt có cổng kiểm tra. Dùng khi code src/scoring/, chỉnh configs/weights.yaml, train/học lại GBM, chọn top lý do, hoặc khi thứ hạng hàng đợi trông sai.
---

# Chấm điểm và xếp hàng đợi

Ba bậc, mỗi bậc phải **thắng bậc trước trên cùng split test** mới được dùng (so bằng `qc-eval`):

1. `rule` — trung bình có trọng số các tín hiệu hình học.
2. `rule_model` — thêm tín hiệu bất đồng detector (và guideline nếu bật).
3. `gbm` — LightGBM học từ tín hiệu → có lỗi hay không.

## Bậc rule

```
risk_score = 100 * Σ(w_i * value_i) / Σ w_i
```

- Trọng số ở `configs/weights.yaml`, có comment giải thích vì sao mỗi trọng số như vậy.
- **Top 3 lý do** = 3 tín hiệu có `value × weight` lớn nhất và > 0; lấy `reason` của tín hiệu đó. Không hiện lý do có đóng góp ≈ 0.
- **Hoà điểm → xếp theo `image_id`** để kết quả xác định (deterministic) — nếu không, recall@20% dao động giữa các lần chạy.
- Ghi file theo quy ước `reports/ranked_queue_<model_version>.csv`, rồi chạy `check_contracts.py` (skill `qc2d-project`).

## Bậc GBM

- Nhãn học (target): ở giai đoạn phát triển = ảnh có lỗi tiêm (hoặc tổng trọng số lỗi, dùng `LGBMRegressor`/`lambdarank`); ở giai đoạn thật = verdict "Lỗi thật" của reviewer.
- Đặc trưng: `value` của mọi tín hiệu + đặc trưng phụ (n_boxes, tỉ lệ box nhỏ, timeofday…). Không đưa `image_id` hay thứ tự file vào.
- **Train trên split train, chọn tham số trên val, báo số trên test.** Mô hình nhỏ (num_leaves ≤ 31, early stopping) — chỉ có ~6k ảnh, 15% dương.
- Lý do hiển thị cho reviewer **vẫn lấy từ `reason` của tín hiệu** (bằng chứng cấp object). `pred_contrib=True` của LightGBM chỉ dùng để chọn tín hiệu nào được hiện và để phân tích — SHAP value không phải câu reviewer đọc được.
- Lưu model vào `models/gbm_<version>.txt` (không commit), `model_version` dạng `gbm-<ngày>-<hash config>`.

## Vòng học lại (bước 6)

Chỉ GBM học lại; rule và detector giữ nguyên.

- Học **theo đợt** (vd. mỗi 200 verdict), không học online sau từng click — tránh một reviewer làm lệch model trong vài phút.
- **Chèn ảnh audit**: ~5% hàng đợi là ảnh ngẫu nhiên dưới vạch cắt. Nếu chỉ học từ ảnh top, model chỉ thấy ảnh nó đã cho là rủi ro và không bao giờ học được loại lỗi nó đang bỏ sót.
- Verdict "Bot nhầm" là mẫu âm; "Bỏ qua" **không dùng** để học.
- **Cổng kiểm tra** trước khi thay model: model mới phải không tệ hơn model cũ trên một tập cố định (holdout + ảnh audit) theo recall@20% có trọng số; nếu tệ hơn → giữ model cũ và ghi log lý do.
- Mô phỏng vòng học ở Mốc 3 bằng cách dùng đáp án tiêm lỗi làm "reviewer giả", có thêm 5–10% verdict sai để mô phỏng người review nhầm.

## Bảng so sánh 5 phương pháp (Mốc 3)

random · thứ tự file · rule · rule + model · GBM — cùng split test, cùng `qc-eval`, một dòng mỗi phương pháp trong `reports/results.jsonl`.
