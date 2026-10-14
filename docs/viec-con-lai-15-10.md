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

## Kết quả review lượt 1 (14/10)

Đã merge vào `develop`: R2/R3, guideline DOCX + đáp án, hướng dẫn kiểm tay (Long); sửa 2 lỗi detector `31642d0` (Sơn,
bỏ 2 dòng `results.jsonl` chạy trên máy Sơn, Cường chạy lại). CI mới chạy trên mọi nhánh: ruff, pytest, test trình
duyệt và kiểm file commit (chặn dữ liệu, phiếu, secret, đường dẫn `/home/...`). **Trước khi mở PR: `git merge
origin/develop` vào nhánh của mình và đợi CI xanh.**

Chưa merge: `feat/tuanh-review-that` (CI đỏ vì đường dẫn máy cá nhân, xem việc của Tú Anh).

---

## Sơn · dữ liệu & detector

- [x] Sửa 2 lỗi detector (đã merge).
- [x] Kiểm tay đủ 150 ảnh, `phieu-son.csv` trên Drive. Không sửa phiếu nữa, không trao đổi với Long về từng ảnh cho đến
  khi Long nộp phiếu.

**Lượt 2 (chiều)**

1. **Gửi ảnh val cho Tú Anh ngay**: link/zip `bdd100k_dataset_for_yolo.zip`. Việc 1 của Tú Anh và pilot đang chờ ảnh.
2. **Báo cáo** `reports/bao-cao-son-15-10.md`: bỏ bảng kết quả kiểm tay ở mục 2 cho đến khi Long nộp phiếu, ghi rõ
   nguồn gốc phiếu trong mô tả PR (commit `6b76310` đang ghi "có nguồn gốc AI"). Mở PR sau khi Long nộp phiếu.
3. **R4 làm chính** (box bị bỏ sót theo guideline, dựa trên kết quả ghép với detector): `@check("model_object_missing")`
   trong `src/features/guideline_rules.py`, đáp án ở `docs/guideline-m13.dap-an.yaml`. Có test, ghi số vào PR.

## Tú Anh · review & pilot

Hướng dẫn chi tiết: [huong-dan-tuanh-15-10.html](huong-dan-tuanh-15-10.html).

**Sửa nhánh `feat/tuanh-review-that` để merge được**

1. `docs/demo-chay-lai.md`: bỏ đường dẫn `/home/nguyen-tu-anh/...`, số task/cổng riêng của máy bạn. Tách thành phần
   chung (mọi máy làm theo được) và phần ghi chép riêng (để trong mô tả PR).
2. Bỏ phần thêm vào `docs/tien-do.md`, chuyển sang mô tả PR. `git merge origin/develop`, đợi CI xanh.

**Lượt 2 (chiều)**

3. **Chạy hàng đợi trên 10 ảnh BDD thật qua CVAT và extension** (khi có ảnh từ Sơn): `cvat-import`, `cvat-sync`, kiểm
   đúng frame, box nghi vấn, verdict, bộ đếm thời gian. Ghi vào PR ảnh nào đúng, ảnh nào sai.
4. **Audit**: sửa code theo định nghĩa Long chốt (Long gửi trước 12:30).
5. **Pilot 30 ảnh**:
   - Cùng 30 ảnh, cùng nhãn ban đầu, hai task CVAT riêng.
   - Hai người review khác nhau: một người theo hàng đợi ưu tiên, một người theo thứ tự file. Tú Anh chọn người với
     Cường; tránh người đã xem nhãn của chính các ảnh đó (Sơn đã xem 150 ảnh kiểm tay).
   - Mỗi người `pilot-register` trước khi bắt đầu. Xong thì `pilot-export --out data/...`, rồi `pilot-compare`.
   - Nộp file export qua Drive, ghi vào PR hoặc tin nhắn: số phút, số ảnh lỗi mỗi người tìm được.
6. Hướng dẫn dựng lại demo trên máy sạch (từ việc 1) để sáng 16/10 cả nhóm test theo đó.

## Long · guideline & chất lượng

Hướng dẫn chi tiết: [huong-dan-long-15-10.html](huong-dan-long-15-10.html).

- [x] R2 và R3 (đã merge; trên nhãn 2018 không có vi phạm, không làm tăng số đo trên lỗi tiêm).
- [x] Hướng dẫn kiểm tay `docs/huong-dan-kiem-tay.md` (đã merge, Cường sửa theo cách chia 150 + 75).
- [x] Guideline DOCX `docs/guideline-m13.docx` và đáp án `docs/guideline-m13.dap-an.yaml`.

**Việc tiếp**

1. **Chốt định nghĩa audit** phần cuối hàng đợi, gửi Tú Anh **trước 12:30**. Hiện code chèn 1 ảnh nửa dưới sau mỗi 10
   ảnh, khác kế hoạch "ngẫu nhiên 5% phần dưới top 20%". Ghi rõ tỉ lệ, mẫu số, cách trộn vào hàng đợi.
2. **Kiểm tay 75 ảnh** trong `manual-check-v1.long.csv`, chấm vào `phieu-long.csv` (cả hai trên Drive), theo
   `docs/huong-dan-kiem-tay.md`. Không xem phiếu, báo cáo của Sơn hay `key.json` trước khi nộp. Xong thì tính kappa
   trên 75 ảnh chung, thống nhất ảnh lệch, tách tỉ lệ lỗi theo nhóm trên đủ 150 ảnh.
3. **Spec đã duyệt**: `guideline extract` từ `docs/guideline-m13.docx` (Tú Anh hỗ trợ Gemini key), đối chiếu với
   `guideline-m13.dap-an.yaml`, sửa bằng `guideline ui`, `guideline approve`. Chạy
   `python -m src.cli rank --version rule-v1.4-spec --spec <spec đã duyệt> --preds data/yolo_preds.parquet --signals`
   và `evaluate`, ghi số vào PR.
4. **Khung báo cáo**: mục lục và chỗ điền số. Số lấy từ `reports/results.jsonl` và kết quả kiểm tay, không tự ghi số.

## Cường

- [x] Merge `feat/cuong-gbm` (GBM, nhãn 2018) vào `develop` (14/10 tối)
- [x] CI chạy trên mọi nhánh + kiểm file commit (14/10)
- [x] Chia kiểm tay: Sơn 150 ảnh, Long 75 ảnh chung (14/10)
- [x] Review, merge lượt 1: Long 3 nhánh, Sơn `31642d0` (14/10)
- [ ] Gửi `manual-check-v1.long.csv`, `phieu-long.csv` lên Drive
- [ ] Chạy lại `rank --version rule-v1.3` + `evaluate` trên `develop`, chốt hàng đợi chính (rule-v1.2 hay rule-v1.3;
  `model_loose_box` bật ở 66% ảnh)
- [ ] Chốt có đưa GBM lên làm phương pháp chính trong báo cáo hay không (sau khi có kiểm tay)
- [ ] Cùng Tú Anh chọn người review thứ hai cho pilot
- [ ] Merge lượt 2 (tối 15/10), đóng băng cấu hình và số liệu
- [ ] Tổng hợp số liệu cuối: recall@20% lỗi tiêm, tỉ lệ lỗi thật theo nhóm (150 ảnh) + kappa (75 ảnh), thời gian pilot
- [ ] Viết kế hoạch deploy (tối 15/10), deploy (chiều 16/10)
