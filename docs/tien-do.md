# Tiến độ M13 · cập nhật 14/10 chiều (sau review lượt 1)

> **Checkpoint Tú Anh · 14/10, chưa merge:** nhánh bàn giao `feat/tuanh-review-that`
> từ develop `4af8938`. Runtime Python 3.11.17 đã phục hồi; bộ Cường đã tải vào
> `data/downloads/`, giải nén cô lập ở `data/m13-input-2018`, checksum nhãn và hash
> hai bộ queue/evidence/labels/features/predictions đều khớp. Công cụ chuẩn bị batch
> và pilot đã kiểm bằng fixture; recheck bị chặn trong DB pilot để giữ snapshot.
> Kiểm mới: **159 passed, 5 skipped; Chromium 3 passed; Ruff sạch**. CVAT HTTP 200.
> **Còn chờ:** ảnh để kiểm 10 ảnh BDD thật, audit do Long chốt, hai reviewer và pilot
> thật. Hướng dẫn: [demo-chay-lai.md](demo-chay-lai.md). Chưa tăng số việc nghiệm thu
> trong bảng dưới; test/chuẩn bị không thay nghiệm thu người thật hoặc PR merge.

Việc còn lại cho 15/10: [viec-con-lai-15-10.md](viec-con-lai-15-10.md).

Phần trăm = số việc đã xong / số việc được giao trong [bản phân công 13/10](phan-tich-va-phan-cong-13-10.md). Việc chỉ "đã viết" mà chưa chạy trên dữ liệu thật thì chưa tính là xong. Phần mở rộng (GBM, VLM, tự học lại) không tính vào.

```
Cả nhóm   ███████████████░░░░░  27/37  73%
Cường     ██████████████████░░  11/12  92%
Tú Anh    █████████████░░░░░░░   5/8   63%
Sơn       ██████████████████░░   7/8   88%   (3 việc Cường làm thay)
Long      █████████░░░░░░░░░░░   4/9   44%
```

## Kết quả hiện có

**14/10: đổi bộ nhãn sang BDD100K bản 2018** (nhãn gốc từ Drive của Sơn, bỏ 52 box suy biến; nguồn và checksum ở
`data/bdd100k/PROVENANCE.json`). Đã tiêm lại lỗi (2981 lỗi, seed 42) và chạy lại toàn bộ hàng đợi. Bản det_20 cũ và kết
quả cũ cất ở `data/_det20/`, `reports/_det20/`; `results.jsonl` giữ cả hai, phân biệt bằng `source_sha256`.

Đo trên 2000 ảnh test, lỗi tiêm (601 lỗi / 300 ảnh). Chỉ số: phần lỗi bắt được khi chỉ review 20% ảnh đầu hàng đợi
(có trọng số theo loại lỗi).

| Hàng đợi | Tín hiệu | Nhãn 2018 (đang dùng) | det_20 (13/10, cũ) |
|---|---|---|---|
| Ngẫu nhiên | — | 0.205 ± 0.024 | 0.202 ± 0.024 |
| Theo thứ tự file | — | 0.223 | 0.228 |
| rule-v0 | 5 tín hiệu hình học | 0.188 | 0.169 |
| rule-v0.1 | 8 tín hiệu hình học | 0.201 | 0.200 |
| rule-v1 | 12 tín hiệu | 0.267 | 0.276 |
| **rule-v1.2** ← **hàng đợi demo** | **4 tín hiệu detector** | **0.310** | 0.348 |
| gbm-v1 (mở rộng) | 12 tín hiệu + 8 đặc trưng phụ, LightGBM tự học trọng số | **0.390** | 0.367 |

Thứ tự các phương pháp không đổi. rule-v1.2 giảm 0.038, chủ yếu ở lỗi sai class (0.35 → 0.28) và thiếu box
(0.43 → 0.38). GBM giờ hơn rule-v1.2 rõ hơn (0.390 so với 0.310, cách hơn 3 lần độ dao động ±0.024 của random).
**Demo vẫn dùng rule-v1.2** vì GBM cần đáp án để học (chạy thật phải học từ verdict của reviewer) và nút kiểm tra lại
hiện chỉ hỗ trợ rule; **Cường cần chốt lại** có đưa GBM lên làm phương pháp chính trong báo cáo hay không.
Bộ tín hiệu và cấu hình GBM chọn trên val (chọn trên det_20, chưa chọn lại trên nhãn 2018); test chỉ dùng để đo.
Đây là lỗi tiêm, chưa phải lỗi thật; số cuối cùng phải lấy từ kiểm tay 150 ảnh.

## Từng người

### Cường · tích hợp & đánh giá — 11/12

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
- [x] Merge PR `feat/cuong-detector-signals`, `feat/cuong-gbm`; chia dữ liệu qua Drive
- [x] Review, merge lượt 1 (14/10): 3 nhánh Long, sửa detector của Sơn; CI chạy mọi nhánh + kiểm file commit
- [ ] Tổng hợp số liệu cuối sau khi có kiểm tay và pilot (trước 15/10 20:00)
- [x] *(mở rộng, không tính %)* GBM `gbm-v1`: `python -m src.cli train-gbm --version gbm-v1 --preds data/yolo_preds.parquet`

### Tú Anh · review & pilot — 5/8

- [x] API, SQLite, queue theo phiên bản, verdict
- [x] CVAT local + mapping frame
- [x] Extension Chrome
- [x] Công cụ đọc/sửa/duyệt guideline
- [x] Công cụ demo, pilot
- [ ] **Chạy queue trên 10 ảnh BDD thật qua CVAT + extension** ← chờ ảnh từ Sơn. Nhánh `feat/tuanh-review-that` (bảng QC nổi trong CVAT, `review-unpack`) chưa merge: CI đỏ do đường dẫn máy cá nhân
- [ ] Pilot 30 ảnh: 2 người, một theo ưu tiên, một theo thứ tự file
- [ ] Dựng máy demo (16/10)

### Sơn · dữ liệu & detector — 5/8

- [x] Tải BDD100K val 10k ảnh *(Cường làm thay, nguồn: bản sao HuggingFace)*
- [x] Detector chạy đủ 10k ảnh *(Cường làm thay)*
- [x] 4 tín hiệu bất đồng *(Cường làm thay)*
- [x] Đọc lại `src/features/detector.py`, `model_disagreement.py`: tìm ra 2 lỗi (box lệch nhiều, capo xe mình)
- [x] Vẽ box để kiểm tay (`src/viz/draw.py`, đã merge 13/10)
- [x] Sửa 2 lỗi detector (`loose_min_iou`, capo xe mình), đã merge 14/10; số `rule-v1.3` Cường chạy lại
- [x] Kiểm tay 150 ảnh (`phieu-son.csv` trên Drive, 14/10)
- [ ] **R4 làm chính** (dùng kết quả so khớp detector) ← việc tiếp theo; gửi ảnh val cho Tú Anh

### Long · guideline & chất lượng — 2/9

- [x] 4 tín hiệu cơ bản
- [x] Đọc spec, engine, R1 (box thấp hơn ngưỡng)
- [x] R2 class không có trong guideline (đã merge 14/10)
- [x] R3 thiếu thuộc tính (đã merge 14/10; nhãn 2018 không có vi phạm)
- [ ] Duyệt spec để `rank --spec` chạy được (đã có `guideline-m13.docx` + đáp án, còn extract → approve)
- [ ] R4 (Sơn làm chính)
- [ ] Phiếu kiểm tay ✅ (`huong-dan-kiem-tay.md`) + **định nghĩa audit** ← việc tiếp theo, gửi Tú Anh trước 12:30
- [ ] Kiểm tay 75 ảnh (`manual-check-v1.long.csv`); tính kappa với phiếu Sơn
- [ ] Báo cáo

## Mốc

| Mốc | Tình trạng |
|---|---|
| 13/10 · Ghép phần đã viết | Gần xong: code đã ghép, API đọc được queue thật; còn chạy qua CVAT + extension trên máy Tú Anh |
| 14/10 · Đủ luồng QC cốt lõi | Detector → queue ✅, baseline ✅, R1–R3 ✅, kiểm tay Sơn ✅; còn chạy trên CVAT với ảnh thật |
| 15/10 20:00 · Đóng băng | Chưa: cần kiểm tay + pilot |
| 16/10 · Bản nộp & video | Chưa |

## Kiểm tay 150 ảnh

Danh sách: `data/manual_check/manual-check-v1.csv` (lấy qua Drive; **sinh lại 14/10 trên nhãn 2018**, 131/150 ảnh trùng danh sách cũ, ai đã tải bản 13/10 thì tải lại). 75 ảnh ngẫu nhiên + 75 ảnh đầu hàng đợi `rule-v1.2-goc` (chấm trên **nhãn gốc**, không phải nhãn đã tiêm), đã trộn thứ tự, seed 42. Người kiểm **không** mở `manual-check-v1.key.json` (ghi ảnh nào thuộc nhóm nào) cho đến khi đối chiếu, để không bị thiên lệch. Sinh lại: `python -m src.cli manual-sample --queue reports/ranked_queue_rule-v1.2-goc.csv`.

**Chia việc (chốt 14/10):** Sơn đã kiểm đủ 150 ảnh. Long kiểm 75 ảnh trong `manual-check-v1.long.csv`
(38 ngẫu nhiên + 37 đầu hàng đợi, chia xen kẽ trong từng nhóm theo `check_order`), phiếu trống `phieu-long.csv` trên
Drive. Kappa tính trên 75 ảnh chung; tỉ lệ lỗi theo nhóm tính trên đủ 150 ảnh.

## Dữ liệu chia qua Drive (không có trên git)

### Kiểm giao diện local 14/10 — không đổi tỷ lệ nghiệm thu 5/8

**Bổ sung giao diện:** Chrome extension 0.3.0 dùng bảng QC cố định trong trang
CVAT, icon QC bật/tắt, không còn Chrome side panel. Click canvas/Save/chuyển frame
không đóng bảng; đóng không chặn chuột, reload giữ trạng thái. Một nút QC đọc nhãn
đã Save rồi recheck; giữ snapshot/verdict/retry, tọa độ đầu vào và thống kê.
Timer loại thời gian focus bảng, phím verdict không chiếm phím ngoài bảng.
Logo QC và đủ icon được đóng gói; không sửa source/stack CVAT.

Đã kiểm CVAT thật trên **task 7/job 7, API 8003**, ảnh tổng hợp và rule
`edge_no_trunc`: nhãn chưa Save được bỏ qua; Save → QC 100→0→100, điều hướng/reload
và verdict. Task 6/API 8002 giữ nguyên. Test Chrome dùng mock REST còn kiểm mất
phản hồi và mở/đóng/reload giữa lúc QC đang chờ không gửi trùng. Bằng chứng mới ở
`data/cvat-overlay-validation/`; cách thử trong `docs/demo-chay-lai.md`.
Máy khác vẫn nạp Chrome extension và cấu hình API/mapping riêng; chưa kiểm máy thứ
hai, BDD/pilot người thật vẫn chờ. Không commit/push.

Đã chạy 5 bước độc lập trên task CVAT mới 6/job 6 và API 8002, DB
`data/cvat-ui-validation/demo/review.db`: import 3 ảnh fixture/mapping thật;
Chrome extension/ảnh/evidence/timer/verdict; kéo box trong CVAT → Save → đọc
nhãn mới → pipeline rule `edge_no_trunc` chấm 100→0→100; restart API giữ queue
và verdict; chuẩn bị lại/import lại không ghi đè annotations hoặc mapping.
Bằng chứng `data/cvat-ui-validation/live-verification.json` và ảnh chụp cùng
thư mục. Giao diện/lệnh thử có trong `docs/demo-chay-lai.md`.

Ảnh tổng hợp và một verdict tự động development; không có detector/Gemini/ML
trong luồng này và không phải pilot người thật. Mục chạy queue `rule-v1.2` trên
ảnh BDD vẫn chờ ảnh; pilot cần hai người; máy demo sạch chưa kiểm. Không
commit/push. Công cụ prepare đã sửa đọc manifest có đường dẫn tương đối repo,
vẫn buộc artifact nằm trong bundle và khớp hash.

**Bộ dữ liệu chung 14/10:** [`m13-data-2018-14-10.zip`](https://drive.google.com/drive/folders/1JHSxrLOmYw1VAhiSNd4Ns-5T3iTMOiyQ) (38MB, sha256 `115136f31cff8658…`). Giải nén ở thư mục gốc repo là các file vào đúng chỗ. Gồm nhãn 2018 đã chuyển, `injected/`, `manual_check/`, `yolo_preds.parquet`, hàng đợi `rule-v1.2` và `rule-v1.2-goc`. Ảnh không có trong zip: lấy `bdd100k_dataset_for_yolo.zip` trên [Drive của Sơn](https://drive.google.com/drive/folders/1l6m-NQaUovVrjoU2VNubIm7743qUlAST).

| Thư mục/file | Dùng để |
|---|---|
| `data/bdd100k/` | ảnh + nhãn gốc. Nhãn: `labels/det_20/det_val.json` bản 2018 đã chuyển, sha256 `f7cde1a3…` (giữ tên file cũ để không phải sửa config) |
| `data/injected/` | nhãn đã tiêm lỗi + đáp án |
| `data/yolo_preds.parquet` | dự đoán RT-DETR; có file này thì không cần GPU |
| `reports/*rule-v1.2*` | queue + evidence + manifest để demo; hoặc tự sinh: `python -m src.cli rank --version rule-v1.2 --preds data/yolo_preds.parquet --signals` |
| `data/manual_check/` | danh sách kiểm tay |
