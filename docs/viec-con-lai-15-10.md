# Việc còn lại · 15/10

Lịch:

| Khi nào | Việc |
|---|---|
| Sáng 15/10 | Mọi người làm lượt 1, **mở PR vào `develop` trước 12:30** |
| Trưa 15/10 | Cường review, merge |
| Chiều 15/10 | Làm lượt 2 (nhánh mới từ `develop` đã merge) |
| Tối 15/10 | Cường review, merge. Sau buổi này đóng băng cấu hình và số liệu |
| Sáng 16/10 | Test lại toàn bộ lần cuối, chỉ sửa lỗi chặn demo |
| Chiều 16/10 | Cường deploy (việc deploy giao riêng sau) |

## Quy ước chung

- Trước khi làm: `git fetch && git checkout -b feat/<tên>-<việc> origin/develop`, rồi `uv pip install -e ".[dev]"`.
- **Tải lại bộ dữ liệu 14/10** (nhãn đã đổi sang BDD100K bản 2018): `m13-data-2018-14-10.zip` trên
  [Drive](https://drive.google.com/drive/folders/1JHSxrLOmYw1VAhiSNd4Ns-5T3iTMOiyQ), giải nén ở thư mục gốc repo.
  Kiểm tra: `sha256sum data/bdd100k/labels/det_20/det_val.json` phải bắt đầu bằng `f7cde1a3`.
- Trước khi mở PR: `pytest -q` và `ruff check .` đều qua. Mỗi việc một PR nhỏ, ghi trong mô tả PR: đã làm gì, chạy lệnh
  gì, kết quả bao nhiêu.
- Không commit dữ liệu, kết quả kiểm tay, file pilot hay mật khẩu. Những thứ đó gửi qua Drive.
- 12:30 mà chưa xong thì vẫn mở PR phần đã chạy được, ghi rõ phần còn thiếu. Không giữ code đến tối.
- Kẹt quá 30 phút thì nhắn nhóm, đừng ngồi một mình.

Kết quả hiện tại để so sánh (2000 ảnh test, nhãn 2018): rule-v1.2 **0.310**, gbm-v1 0.390, ngẫu nhiên 0.205 ± 0.024.
Chi tiết ở [tien-do.md](tien-do.md).

---

## Sơn · dữ liệu & detector

**Lượt 1 (trước 12:30)**

1. **Sửa 2 lỗi detector**, nhánh `feat/son-fix-disagreement`, làm theo
   [huong-dan-son-14-10.html](huong-dan-son-14-10.html):
   - `model_loose_box` bỏ sót box lệch nhiều (IoU dưới 0.5): thêm ngưỡng `loose_min_iou` (0.3).
   - Bỏ dự đoán trúng capo xe mình (đáy box ≥ 715px và rộng ≥ 640px).
   - Mỗi lỗi một test trong `tests/`.
   - Chạy `python -m src.cli rank --version rule-v1.3 --preds data/yolo_preds.parquet --signals` rồi `evaluate`, ghi số vào PR và so
     với 0.310. Thấp hơn cũng ghi đúng số, không chỉnh ngưỡng trên test.

**Lượt 2 (chiều)**

2. **Kiểm tay 150 ảnh** theo phiếu Long gửi, độc lập với Long. Không xem `manual-check-v1.key.json`, không trao đổi
   với Long trước khi cả hai xong. Dùng `src/viz/draw.py` để vẽ box. Nộp phiếu qua Drive.
3. Nếu còn thời gian thì hỗ trợ Long làm R4 (box bị bỏ sót, dựa trên kết quả ghép với detector).

## Tú Anh · review & pilot

**Lượt 1 (trước 12:30)**

1. **Chạy hàng đợi `rule-v1.2` trên máy mình qua CVAT và extension**:
   - Dùng bộ dữ liệu 14/10, sau đó `cvat-import` và `cvat-sync` để sinh lại mapping trên máy mình.
   - Mở 10 ảnh đầu hàng đợi, kiểm tra đúng frame, box nghi vấn tô đúng chỗ, lưu được verdict và bộ đếm thời gian.
   - Lỗi nào thì sửa luôn trong PR. Ghi vào PR ảnh nào đúng, ảnh nào sai.
2. Chỉnh cơ chế lấy mẫu kiểm phần cuối hàng đợi (audit) theo định nghĩa Long chốt. Hiện code đang chèn 1 ảnh nửa
   dưới sau mỗi 10 ảnh, khác kế hoạch "ngẫu nhiên 5% phần dưới top 20%". Hai bạn thống nhất trong sáng nay.

**Lượt 2 (chiều)**

3. **Pilot 30 ảnh**:
   - Cùng 30 ảnh, cùng nhãn ban đầu, hai task CVAT riêng.
   - Hai người review khác nhau: một người theo hàng đợi ưu tiên, một người theo thứ tự file. Tú Anh chọn người với
     Cường.
   - Mỗi người `pilot-register` trước khi bắt đầu. Xong thì `pilot-export --out data/...`, rồi `pilot-compare`.
   - Nộp file export qua Drive, ghi vào PR hoặc tin nhắn: số phút, số ảnh lỗi mỗi người tìm được.
4. Viết các bước dựng lại demo trên máy sạch (đã chạy lệnh nào, theo thứ tự nào) để sáng 16/10 cả nhóm test theo đó.

## Long · guideline & chất lượng

**Lượt 1 (trước 12:30)**

1. **R2 và R3** trong `src/features/guideline_rules.py`, đăng ký bằng `@check("class_not_allowed")` và
   `@check("missing_attribute")` giống R1. Spec `configs/guidelines/bdd-default.yaml` đã khai báo sẵn 2 rule này.
   - R2: box có `category` không nằm trong `classes` của spec.
   - R3: box thiếu một trong `required_attributes` (`occluded`, `truncated`).
   - Mỗi rule có test cho ca vi phạm và ca không vi phạm.
   - Lưu ý: trên nhãn 2018, 185526/185526 box đều có đủ 2 thuộc tính, nên R3 chỉ bắt được lỗi tiêm hoặc nhãn từ CVAT.
     Ghi điều này trong PR, đừng coi là lỗi code.
2. **Phiếu kiểm tay** cho 150 ảnh trong `data/manual_check/manual-check-v1.csv`:
   - Mỗi ảnh ghi: có lỗi / không lỗi / không chắc, loại lỗi, ghi chú.
   - Gửi nhóm trước 12:30 để Sơn kiểm được trong buổi chiều.
3. **Chốt định nghĩa mẫu audit** phần cuối hàng đợi với Tú Anh (xem việc 2 của Tú Anh).

**Lượt 2 (chiều)**

4. **Duyệt spec**:
   - Đọc lại `bdd-default.yaml` so với guideline BDD100K, sửa nếu sai.
   - Duyệt bằng `python -m src.cli guideline approve configs/guidelines/bdd-default.yaml --approved-by "Long" --confirm-reviewed`.
   - Chạy thử `python -m src.cli rank --version rule-v1.4-spec --spec <spec đã duyệt> --preds data/yolo_preds.parquet --signals` và `evaluate`.
     Ghi số vào PR.
5. **Kiểm tay 150 ảnh**, độc lập với Sơn. Xong cả hai mới đối chiếu: tính kappa trên có lỗi/không lỗi, để riêng các ảnh
   "không chắc".
6. Khung báo cáo: mục lục và chỗ điền số. Số lấy từ `reports/results.jsonl` và kết quả kiểm tay, không tự ghi số.
7. R4 cùng Sơn chỉ làm khi 1–6 đã xong.

## Cường

- [x] Merge `feat/cuong-gbm` (GBM, nhãn 2018) vào `develop` (14/10 tối)
- [ ] Review, merge lượt 1 (trưa) và lượt 2 (tối 15/10)
- [ ] Chốt có đưa GBM lên làm phương pháp chính trong báo cáo hay không
- [ ] Tổng hợp số liệu cuối sau khi có kiểm tay và pilot
- [ ] Deploy (chiều 16/10)
