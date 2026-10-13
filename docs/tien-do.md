# Tiến độ M13 · cập nhật 13/10 tối

Phần trăm = số việc đã xong / số việc được giao trong [bản phân công 13/10](phan-tich-va-phan-cong-13-10.md). Việc chỉ "đã viết" mà chưa chạy trên dữ liệu thật thì chưa tính là xong. Phần mở rộng (GBM, VLM, tự học lại) không tính vào.

```
Cả nhóm   ███████████░░░░░░░░░  20/36  56%
Cường     █████████████████░░░  10/12  83%
Tú Anh    █████████████░░░░░░░   5/8   63%
Sơn       █████████░░░░░░░░░░░   3/7   43%   (3 việc Cường làm thay)
Long      ████░░░░░░░░░░░░░░░░   2/9   22%
```

## Kết quả hiện có

Đo trên 2000 ảnh test, lỗi tiêm. Chỉ số: phần lỗi bắt được khi chỉ review 20% ảnh đầu hàng đợi (có trọng số theo loại lỗi).

| Hàng đợi | Tín hiệu | Kết quả |
|---|---|---|
| Ngẫu nhiên | — | 0.202 ± 0.024 |
| Theo thứ tự file | — | 0.228 |
| rule-v0.1 | 8 tín hiệu hình học | 0.200 |
| rule-v1 | 12 tín hiệu | 0.276 |
| **rule-v1.2** | **4 tín hiệu detector** | **0.348** |

Bộ tín hiệu chọn trên tập val; tập test chỉ dùng để đo. Đây là lỗi tiêm, chưa phải lỗi thật; số cuối cùng phải lấy từ kiểm tay 150 ảnh.

## Từng người

### Cường · tích hợp & đánh giá — 10/12

- [x] Ghép nhánh Tú Anh, Long vào develop
- [x] Tiêm lỗi (`inject`), 2964 lỗi trên 10k ảnh
- [x] Một lệnh ra queue + evidence + manifest (`rank`)
- [x] Đánh giá so baseline (`evaluate`), ghi `reports/results.jsonl`
- [x] Adapter kiểm tra lại cho API (`src.pipeline:recheck`); manifest dùng đường dẫn tương đối, chép sang máy khác vẫn chạy
- [x] Chạy RT-DETR trên 10k ảnh *(làm thay Sơn)*
- [x] 4 tín hiệu bất đồng với detector *(làm thay Sơn)*
- [x] 3 tín hiệu hình học *(làm thay Tú Anh)*
- [x] API đọc đúng queue/evidence `rule-v1.2` (đã chạy thử)
- [x] Danh sách 150 ảnh kiểm tay (`manual-sample`)
- [ ] Merge PR `feat/cuong-detector-signals`, chia dữ liệu qua Drive
- [ ] Tổng hợp số liệu cuối sau khi có kiểm tay và pilot (trước 15/10 20:00)

### Tú Anh · review & pilot — 5/8

- [x] API, SQLite, queue theo phiên bản, verdict
- [x] CVAT local + mapping frame
- [x] Extension Chrome
- [x] Công cụ đọc/sửa/duyệt guideline
- [x] Công cụ demo, pilot
- [ ] **Chạy queue `rule-v1.2` trên máy mình qua CVAT + extension, kiểm tô đúng box** ← việc tiếp theo
- [ ] Pilot 30 ảnh: 2 người, một theo ưu tiên, một theo thứ tự file
- [ ] Dựng máy demo (16/10)

### Sơn · dữ liệu & detector — 3/7

- [x] Tải BDD100K val 10k ảnh *(Cường làm thay, nguồn: bản sao HuggingFace)*
- [x] Detector chạy đủ 10k ảnh *(Cường làm thay)*
- [x] 4 tín hiệu bất đồng *(Cường làm thay)*
- [ ] **Đọc lại `src/features/detector.py`, `model_disagreement.py`** ← việc tiếp theo
- [ ] Vẽ box để kiểm tay (`src/viz/draw.py` còn trống)
- [ ] Kiểm tay 150 ảnh, độc lập với Long
- [ ] Hỗ trợ Long viết R4 (dùng kết quả so khớp detector)

### Long · guideline & chất lượng — 2/9

- [x] 4 tín hiệu cơ bản
- [x] Đọc spec, engine, R1 (box thấp hơn ngưỡng)
- [ ] **R2 class không có trong guideline** ← việc tiếp theo
- [ ] R3 thiếu thuộc tính
- [ ] Duyệt spec (`approved_by`) để `rank --spec` chạy được
- [ ] R4 (cùng Sơn)
- [ ] Phiếu kiểm tay + cách lấy mẫu kiểm phần cuối hàng đợi
- [ ] Kiểm tay 150 ảnh, độc lập với Sơn; tính kappa
- [ ] Báo cáo

## Mốc

| Mốc | Tình trạng |
|---|---|
| 13/10 · Ghép phần đã viết | Gần xong: code đã ghép, API đọc được queue thật; còn chạy qua CVAT + extension trên máy Tú Anh |
| 14/10 · Đủ luồng QC cốt lõi | Detector → queue ✅, baseline ✅; còn R2/R3, bắt đầu kiểm tay |
| 15/10 20:00 · Đóng băng | Chưa: cần kiểm tay + pilot |
| 16/10 · Bản nộp & video | Chưa |

## Kiểm tay 150 ảnh

Danh sách: `data/manual_check/manual-check-v1.csv` (lấy qua Drive). 75 ảnh ngẫu nhiên + 75 ảnh đầu hàng đợi `rule-v1.2-goc` (chấm trên **nhãn gốc**, không phải nhãn đã tiêm), đã trộn thứ tự, seed 42. Người kiểm **không** mở `manual-check-v1.key.json` (ghi ảnh nào thuộc nhóm nào) cho đến khi đối chiếu, để không bị thiên lệch. Sinh lại: `python -m src.cli manual-sample --queue reports/ranked_queue_rule-v1.2-goc.csv`.

## Dữ liệu chia qua Drive (không có trên git)

| Thư mục/file | Dùng để |
|---|---|
| `data/bdd100k/` | ảnh + nhãn gốc |
| `data/injected/` | nhãn đã tiêm lỗi + đáp án |
| `data/yolo_preds.parquet` | dự đoán RT-DETR; có file này thì không cần GPU |
| `reports/*rule-v1.2*` | queue + evidence + manifest để demo; hoặc tự sinh: `python -m src.cli rank --version rule-v1.2 --preds data/yolo_preds.parquet --signals` |
| `data/manual_check/` | danh sách kiểm tay |
