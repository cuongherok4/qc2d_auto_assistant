# Báo cáo tuần 4: M13 Reviewer Prioritization

Cập nhật: 11/10/2026 · Người viết: Hoàng Mạnh Cường

## 1. Tóm tắt

Tuần 4 nhóm bắt đầu đề M13 (Reviewer Prioritization Assistant): đã chốt đề bài, luồng 7 bước, cách đánh giá và tài liệu quy trình, nhưng **Mốc 1 (hạn 10/10) đã trễ** vì chưa có dữ liệu, chưa có repo git và driver GPU trên máy dev đang lỗi.

| | |
|---|---|
| Đề | M13, ưu tiên ảnh có nguy cơ sai nhãn cao thay vì review đều 100% |
| Dữ liệu | BDD100K val, 10k ảnh, nhãn detection 2D |
| Đầu ra | Hàng đợi review xếp hạng, mỗi ảnh kèm 3 lý do tiếng Việt |
| Chỉ số | Recall lỗi trong top 20% ảnh; thời gian review tiết kiệm |
| Nhóm | Hoàng Mạnh Cường (lead), Long (BA), Tú Anh (BE), Sơn (BE) |

## 2. Việc đã làm

1. **Thiết kế luồng 7 bước:** dữ liệu → tiêm lỗi → tín hiệu rủi ro → chấm điểm → hàng đợi → reviewer → đánh giá, chia thành 5 mốc.
2. **Chốt cách đánh giá (07/10):** chia 6k/2k/2k theo ảnh, seed 42; tiêm lỗi 15% ảnh, 1–3 lỗi/ảnh, 5 loại (xoá nhãn, đổi class, box giả, dịch box, co/giãn box); recall@20% theo ảnh và theo lỗi có trọng số; so với baseline ngẫu nhiên và thứ tự file.
3. **Dựng khung dự án:** `CLAUDE.md`, `docs/PLAN.md`, 5 config YAML, CLI, khung FastAPI (`/health`, `/queue`), `SignalResult`, khung Chrome extension MV3, 1 test smoke.
4. **Viết thử code Mốc 1:** loader BDD100K, tiêm lỗi, tín hiệu hình học, chấm điểm rule, khung đo; 13 test pass; tiêm lỗi 1,5 giây và chấm điểm 30 giây trên 10k ảnh giả lập. Code này đã bị xoá, thiết kế được ghi lại để viết lại nhanh.
5. **Đề xuất chấm theo guideline từng batch:** guideline → spec YAML có version, rule engine dẫn chiếu rule ID (ví dụ "[R1] Thiếu car cao 22px, ngưỡng 15px"), lọc dự đoán detector theo spec trước khi so với nhãn.
6. **Tài liệu:** `M13_TOM_TAT.md` (bối cảnh, quyết định, việc còn chốt), `M13_QUY_TRINH.html` (luồng QC và lịch xây dựng), `M13_CONG_NGHE.html` (công nghệ).
7. **Thu thập yêu cầu:** lead trả lời 21 câu hỏi mở (công cụ review, detector, số ảnh kiểm tay, LLM/VLM…).
8. **Rút bài học từ 3 tuần gán nhãn:** review bằng mắt sót lỗi tên nhãn; guideline không rõ là nguồn lỗi lớn nhất; review trên CVAT không để lại dấu vết (0 issue).

## 3. Kết quả và số liệu

Chưa có số liệu đánh giá thật: chưa tải BDD100K nên chưa chạy được recall@20% hay gain curve. Số duy nhất đo được là tốc độ của bản code thử trên dữ liệu giả lập (mục 2.4).

| Chỉ số | Mục tiêu | Hiện tại |
|---|---|---|
| Recall lỗi trong top 20% ảnh | Cao hơn rõ baseline ngẫu nhiên (≈ 20%) | Chưa đo |
| Time saved | `1 − ảnh cần xem để đạt 80% recall / ảnh cần xem theo thứ tự ngẫu nhiên` | Chưa đo |
| Lỗi sót sau QC | ≤ 2% object | Chưa đo |

## 4. Khó khăn và rủi ro

- **Mốc 1 trễ:** hạn 10/10 chưa đạt, các mốc sau cần lùi lại.
- **Chưa có dữ liệu:** `data/` trống, cần tải BDD100K (ảnh val + Detection 2020 Labels).
- **Driver GPU lỗi:** `nvidia-smi` không kết nối được driver; chặn bước chạy detector (Mốc 2) và VLM.
- **Chưa có repo git chung:** chưa chia việc code được cho cả nhóm.
- **Môi trường:** Python hệ thống 3.14, dự án cần 3.11 (`uv venv --python 3.11`).
- **Mâu thuẫn chưa chốt** giữa kế hoạch gốc và câu trả lời 21 câu hỏi:

| Điểm | Kế hoạch gốc | Câu trả lời |
|---|---|---|
| Thời gian | 12 ngày × 4h | Khoảng 2 tuần |
| Công cụ review | CVAT + Chrome extension + FastAPI | FiftyOne |
| Detector | YOLOv8n (AGPL-3.0) | RT-DETR / mmdetection (Apache-2.0) |
| Kiểm tay | 50 ảnh | 500 ảnh × 2 người (≈ 25 giờ công) |
| LLM/VLM | Không có | LLM trích spec + Qwen2.5-VL |

- **Rủi ro đánh giá:** tiêm lỗi ưu tiên box nhỏ và ảnh đêm thì tín hiệu "đêm"/"box nhỏ" sẽ được lợi một phần; phải kiểm chứng trên tập kiểm tay lỗi thật.

## 5. Kế hoạch tuần 5

Lịch đề xuất 11/10 → 25/10, cần nhóm duyệt:

| Ngày | Việc | Mốc |
|---|---|---|
| 11–13/10 | Vòng 1: dữ liệu, tiêm lỗi, tín hiệu hình học, chấm điểm rule, gain curve | Mốc 1 |
| 14–15/10 | Vòng 2: chạy detector, tín hiệu bất đồng, luật guideline viết tay, bắt đầu kiểm tay | Mốc 2 |
| 16–18/10 | Vòng 3: GBM, mô phỏng học lại, bảng so sánh 5 phương pháp, xong kiểm tay | Mốc 3 |
| 19–21/10 | Vòng 4: VLM xem lại top 30% (cắt bớt nếu trễ); LLM đọc guideline đã chuyển lên Vòng 2 | Mốc 4 |
| 22–23/10 | Giao diện review + pilot đo thời gian thật | Mốc 5 |
| 24–25/10 | Báo cáo, README, video demo | Mốc 6 |

Việc làm ngay:

- [ ] Tải BDD100K val + nhãn Detection 2020 (Sơn)
- [ ] Sửa driver GPU (Cường)
- [ ] Tạo repo git private, chia nhánh `feat/...` (Cường)
- [ ] Chốt 4 điểm còn mở: thêm bước chấm theo guideline, ai code, lùi mốc, các mâu thuẫn ở mục 4
- [ ] Viết lại code Mốc 1 theo thiết kế đã ghi
- [ ] Báo cáo tiến độ 22:30 mỗi tối theo mẫu Done / Doing / Blocked / Link / Questions
