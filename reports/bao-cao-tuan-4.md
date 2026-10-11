# Báo cáo tuần 4: M13 Reviewer Prioritization

**Thời gian:** 05/10 – 11/10/2026 · **Cập nhật:** 11/10/2026 · **Người viết:** Hoàng Mạnh Cường

## 1. Tóm tắt

- Tuần này nhóm **xác định lại bài toán M13**: chốt đầu vào, đầu ra, luồng 7 bước và cách đánh giá.
- Đã **chia việc theo module** cho 4 người và thống nhất quy ước để ghép code.
- Đã lên **kế hoạch 2 tuần tới (12/10 – 25/10)** để hoàn thành M13.
- Bản V1 (Guideline Assistant) đã chạy được trên CVAT, có video demo 44 giây.

## 2. Đã hoàn thành

### 2.1 Xác định lại bài toán

Mục tiêu là ưu tiên những ảnh có nguy cơ sai nhãn cao để QC xem trước, thay vì review đều 100% ảnh.

| | |
|---|---|
| Dữ liệu | BDD100K tập val, 10k ảnh, nhãn detection 2D |
| Đầu ra | Hàng đợi review xếp hạng, điểm rủi ro 0–100, mỗi ảnh kèm 3 lý do tiếng Việt |
| Chỉ số chính | Recall lỗi trong top 20% ảnh; thời gian review tiết kiệm |
| Mức lỗi sót chấp nhận | ≤ 2% object |

**Luồng 7 bước:**

```
[1] Dữ liệu    BDD100K val: 10k ảnh + nhãn detection
[2] Tiêm lỗi   15% ảnh, 1–3 lỗi/ảnh, 5 loại → biết trước ảnh nào sai
[3] Tín hiệu   hình học/ngữ cảnh + bất đồng với detector
[4] Chấm điểm  rule → rule + detector → GBM; điểm 0–100 + 3 lý do
[5] Hàng đợi   ranked_queue → API → giao diện review
[6] Reviewer   Lỗi thật / Bot nhầm / Bỏ qua → học lại theo đợt
[7] Đánh giá   recall@20%, time saved, gain curve; so với random và thứ tự file
```

**Quyết định đã chốt (07/10):**

- Chia 6k/2k/2k theo ảnh, seed 42.
- 5 loại lỗi tiêm: xoá nhãn, đổi class, box giả, dịch box, co/giãn box.
- Recall báo theo cả ảnh và lỗi có trọng số. "Top 20%" báo theo cả số ảnh và thời gian review.
- Kiểm ngẫu nhiên 5% số ảnh dưới vạch cắt để ước lượng lỗi còn sót.
- Đề xuất thêm: chấm điểm theo guideline của từng batch (spec YAML có version, lý do dẫn chiếu rule ID, ví dụ "[R1] Thiếu car cao 22px, ngưỡng 15px").

**Bài học từ 3 tuần gán nhãn được đưa vào thiết kế:**

- Review bằng mắt bỏ sót lỗi tên nhãn, vì vậy cần kiểm theo luật tự động.
- Guideline không rõ là nguồn lỗi lớn nhất, vì vậy chấm điểm theo guideline.
- Review trên CVAT không để lại dấu vết, vì vậy hàng đợi phải lưu verdict và thời gian xem.

### 2.2 Khung dự án M13

| Hạng mục | Kết quả |
|---|---|
| Cấu trúc repo | `src/` gồm data, synth, features, scoring, eval, api; có tests, configs |
| Cấu hình | 5 file YAML: paths, weights, injection, learning, class_map |
| CLI | `python -m src.cli` có 5 lệnh: inject, rank, evaluate, retrain, simulate (mới có tham số) |
| API + extension | Khung FastAPI (`/health`, `/queue`), khung Chrome extension MV3 |
| Code thử | Loader, tiêm lỗi, tín hiệu hình học, chấm điểm rule; 13 test pass trên dữ liệu giả lập. Đã ghi lại thiết kế để viết lại trên dữ liệu thật |

## 3. Phân chia công việc

Mỗi người phụ trách một module và chỉ sửa thư mục của mình, để làm song song mà không phải chờ nhau.

| Thành viên | Vai trò | Phụ trách | Thư mục |
|---|---|---|---|
| Hoàng Mạnh Cường | Trưởng nhóm, ML | Tiêm lỗi, tín hiệu hình học, chấm điểm, GBM, đánh giá, CLI; review và merge code | `src/data/inject.py`, `src/features/geometric.py`, `src/scoring/`, `src/eval/`, `src/cli.py`, `configs/` |
| Sơn | BE, dữ liệu | Tải BDD100K, chạy detector, so dự đoán với nhãn | `src/features/detector.py`, `src/features/model_disagreement.py` |
| Tú Anh | BE, API + giao diện | API, lưu verdict, side panel, mở đúng frame để review | `src/api/`, `extension/` |
| Long | BA | Đọc guideline thành spec, rule engine, kiểm tay, pilot đo thời gian | `src/guideline/`, `src/features/guideline_rules.py`, `configs/guidelines/` |

**Quy ước để ghép code:**

1. Mỗi tín hiệu trả về `SignalResult(name, value 0–1, reason tiếng Việt có con số)`.
2. Dự đoán detector lưu ở `data/yolo_preds.parquet`: `image_id, x1, y1, x2, y2, category, conf`.
3. Hàng đợi lưu ở `reports/ranked_queue_*.csv`: `image_id, risk_score, rank, top_reasons, model_version`.

**Cách làm việc:** mỗi việc một nhánh riêng, tên ghi rõ ai làm và làm gì (`feat/son-model-missing-label`), mở PR vào `develop`. Lead review và merge vào `develop`; khi dự án hoàn thành mới đưa `develop` vào `main`. Mỗi tối 22:30 từng người báo cáo theo mẫu Done / Doing / Blocked / Link / Questions.

## 4. Vướng mắc và rủi ro

| Vấn đề | Ảnh hưởng | Biện pháp |
|---|---|---|
| Lỗi tiêm giả lập ưu tiên box nhỏ và ảnh đêm | Kết quả có thể đẹp hơn thực tế | Kiểm chứng thêm trên tập kiểm tay lỗi thật |
| Nhãn gốc BDD100K vốn đã có lỗi | Lỗi thật bị tính nhầm là "bot nhầm", làm sai số liệu | Đo tỉ lệ lỗi gốc trên tập kiểm tay rồi hiệu chỉnh |
| Detector train trên nhãn có lỗi sẽ học luôn lỗi đó | Tín hiệu bất đồng không bắt được lỗi có hệ thống | Dùng detector pretrained độc lập (COCO), không train trên nhãn đang kiểm |

## 5. Kế hoạch 2 tuần tới (12/10 – 25/10)

| Ngày | Việc | Mốc |
|---|---|---|
| 12–13/10 | Dữ liệu, tiêm lỗi, tín hiệu hình học, chấm điểm rule, gain curve so với random | Mốc 1 |
| 14–15/10 | Chạy detector, tín hiệu bất đồng, luật guideline, bắt đầu kiểm tay | Mốc 2 |
| 16–18/10 | GBM, mô phỏng học lại, bảng so sánh 5 phương pháp, xong kiểm tay | Mốc 3 |
| 19–21/10 | LLM đọc guideline, VLM xem lại top hàng đợi (phần mở rộng) | Mốc 4 |
| 22–23/10 | Giao diện review, pilot đo thời gian review thật | Mốc 5 |
| 24–25/10 | Báo cáo cuối, README, video demo | Mốc 6 |

## Link

- Repo: _(điền link GitHub)_
- Video demo V1: https://drive.google.com/file/d/1uT6OfSbkwQrv0LvhwTCl4fkYypl-KEuY/view
