# M13 Reviewer Prioritization: tóm tắt dự án

Cập nhật: 11/10/2026. Bối cảnh, hiện trạng, các quyết định đã bàn và việc còn phải chốt của dự án.

---

## 1. Đề bài

| | |
|---|---|
| Mã đề | M13, Reviewer Prioritization Assistant (Annotation & QC, mức Nâng cao) |
| Dữ liệu | BDD100K, tập val 10k ảnh + nhãn detection 2D |
| Mô tả | Ưu tiên ảnh/frame có nguy cơ sai cao thay vì review đều 100% |
| Đầu ra | Hàng đợi review xếp hạng ưu tiên, kèm lý do chấm điểm |
| Chỉ số | Recall lỗi trong top 20%; thời gian review tiết kiệm được |
| Thời gian | 12 ngày, 07/10 → 18/10/2026, 4h/ngày (≈ 48h) |

**Nhóm:** Hoàng Mạnh Cường (lead, dev chính), Long (BA), Tú Anh (BE), Sơn (BE).

**Bối cảnh nhóm:** repo GitHub `AI20K-Build-Phase-Cohort-4A/P-033` là sổ làm việc 3 tuần gán nhãn trên CVAT (tuần 1: bbox/polygon/seg kiểu BDD; tuần 2: keypoint mặt; tuần 3: cuboid 3D). Tuần 4 bắt đầu M13. Nhóm đã có **V1 Guideline Assistant**: Chrome extension trong CVAT, đọc guideline DOCX/PDF bằng AI và gợi ý theo từng label (có video demo 44 giây).

## 2. Hiện trạng ngày 11/10

- Repo `qc-2d` đã có base để cả nhóm làm song song: 3 quy ước ghép code, loader BDD100K, chấm điểm rule, metric đánh giá, CLI, khung API và extension, test và CI. Quy trình làm việc ở `CONTRIBUTING.md`.
- Việc còn lại của từng người được đánh dấu `TODO(<tên>)` trong code.
- Python 3.11 (`uv venv --python 3.11`); máy dev có Python 3.14 hệ thống.

## 3. Luồng dự án

```
[1] Dữ liệu      BDD100K val: 10k ảnh + nhãn detection
[2] Tiêm lỗi     15% ảnh, 1–3 lỗi/ảnh, 5 loại → biết trước ảnh nào sai
[3] Tín hiệu     a. Hình học/ngữ cảnh  b. Bất đồng với YOLO
[4] Chấm điểm    rule → rule + YOLO → GBM; điểm 0–100 + 3 lý do tiếng Việt
[5] Hàng đợi     ranked_queue.csv → FastAPI → Chrome extension → mở frame CVAT
[6] Reviewer     Lỗi thật / Bot nhầm / Bỏ qua → học lại GBM theo đợt (có cổng kiểm tra)
[7] Đánh giá     recall@20%, time saved, gain curve; so với random và thứ tự file
```

| Mốc | Nội dung | Hạn gốc |
|---|---|---|
| 1 | [1] [2] [3a] [4 rule] [7], gain curve rule vs random | 10/10 |
| 2 | [3b] [4 rule + YOLO], kiểm tay 50 ảnh | 12/10 |
| 3 | GBM, vòng học mô phỏng, bảng 5 phương pháp | 14/10 |
| 4 | API + extension + CVAT, pilot, time saved | 16/10 |
| 5 | Báo cáo, README, video demo | 18/10 |

**Quyết định gốc đã chốt (07/10):** chia 6k/2k/2k theo ảnh, seed 42; co/giãn box và box giả chỉ có ở tập test; recall@20% theo ảnh; time saved = `1 − (số ảnh cần xem theo hàng đợi để đạt 80% recall) / (số ảnh cần xem theo thứ tự ngẫu nhiên)`; YOLOv8n pretrained COCO, bỏ `rider` và `traffic sign` khỏi tín hiệu bất đồng; chỉ GBM học lại, theo đợt, có chèn ảnh audit.

## 4. Các đề xuất đã bàn (chưa chốt chính thức)

### 4.1 Chấm điểm theo guideline của từng batch
Mỗi batch có guideline khác nhau (ví dụ ngưỡng kích thước tối thiểu). Cùng một box 18px có thể đúng với guideline A nhưng là box thừa với guideline B. Căn cứ thực tế: P-001 tuần 01 trong backlog (không có ngưỡng bỏ qua vật xa/nhỏ/mờ, mỗi người làm một kiểu).

- Guideline → spec YAML có version (ngưỡng chiều cao px, danh sách class, class gộp, quy tắc che khuất). Người phụ trách duyệt spec.
- Rule engine kiểm phần đo được: box dưới ngưỡng, class không có trong guideline, thiếu attribute.
- **Lọc dự đoán YOLO theo spec trước khi so với nhãn**, tránh báo "thiếu box" cho object không bắt buộc gán.
- Ca sát ngưỡng (± vài px) chỉ tăng điểm rủi ro, không kết luận là lỗi.
- Lý do dẫn chiếu rule ID, ví dụ "[R1] Thiếu car cao 22px, ngưỡng 15px".
- Thí nghiệm: 3 guideline giả lập trên BDD100K (gốc BDD; ngưỡng 30px + gộp truck/bus; bỏ traffic sign). So bản biết guideline với bản không biết.
- Bước đọc guideline có thể dùng lại backend V1.

### 4.2 Tiêm lỗi theo phân phối thực tế
Xoá nhãn ưu tiên object nhỏ (< 30px), bị che, ảnh đêm. Đổi class theo cặp hay nhầm: car↔truck, bus↔truck, pedestrian↔rider, bicycle↔motorcycle, traffic light↔traffic sign.
**Cảnh báo:** tín hiệu "đêm" và "box nhỏ" sẽ được lợi một phần do chính cách tiêm. Phải ghi là hạn chế và kiểm chứng trên lỗi thật.

### 4.3 Đánh giá
- Báo recall theo **ảnh** và theo **lỗi có trọng số**. Trọng số đề xuất: xoá nhãn 1.0, đổi class 1.0, box giả 0.6, dịch box 0.3, co/giãn 0.3.
- "Top 20%" báo theo cả **số ảnh** và **thời gian review** (ảnh rủi ro cao thường đông object nên review lâu hơn).
- Không nói "bắt 80% lỗi trong 20% ảnh = tiết kiệm 80% thời gian". Nói theo dạng "với ngân sách X giờ, tỉ lệ lỗi sót giảm từ A% xuống B%".
- **Kiểm ngẫu nhiên 5% số ảnh dưới vạch cắt** để ước lượng lỗi còn sót và tránh dữ liệu học bị lệch.
- **Tập kiểm tay lỗi thật:** 150–200 ảnh (một nửa top hàng đợi, một nửa ngẫu nhiên), 2 người cùng kiểm, đo Cohen's kappa. Đây là thước đo cuối cùng; lỗi tiêm chỉ dùng lúc phát triển.
- Nhãn gốc BDD100K vốn có lỗi: đo tỉ lệ lỗi gốc trên tập kiểm tay rồi hiệu chỉnh.

### 4.4 Kỹ thuật
- Lõi ML + rule là xương sống. Agent/VLM chỉ là phần mở rộng, giữ lại nếu tăng được chỉ số.
- Detector train trên nhãn có lỗi sẽ học luôn lỗi có hệ thống → nên có ý kiến từ một model độc lập (pretrained COCO).
- **License:** YOLO Ultralytics là AGPL-3.0 (ổn cho bản nộp, vướng nếu dùng thương mại); thay thế: RT-DETR / mmdetection (Apache-2.0). Điều khoản của BDD100K cũng cần đọc nếu dùng thật.
- Lý do hiển thị cho reviewer lấy từ bằng chứng cấp object (box nào, model nói gì). `pred_contrib` của GBM chỉ dùng để phân tích.
- Chưa kiểm chứng: nhãn BDD 2018 so với `det_20` có dùng làm lỗi thật được không.

## 5. Câu trả lời của Cường cho 21 câu hỏi mở

| # | Câu hỏi | Trả lời |
|---|---|---|
| Q1 | Đồ án hay tool dùng thật | Tool nội bộ dùng thật |
| Q2 | Thời hạn | Dưới 4 tuần (ghi chú: 2 tuần) |
| Q3 | GPU | 1 GPU ≥ 12GB (máy tao), Colab |
| Q4 | Phạm vi dữ liệu | Detection 2D, tập 10k |
| Q5 | Đơn vị recall | Cả hai, object có trọng số làm chính |
| Q6 | Top 20% theo gì | Báo cả số ảnh và thời gian |
| Q7 | Trọng số severity | Claude đề xuất, Cường duyệt |
| Q8 | Ngưỡng IoU box lệch | Theo guideline, mặc định 0.7 |
| Q9 | Ai kiểm tay | 2 người, đo đồng thuận |
| Q10 | Số ảnh kiểm tay | 500 |
| Q11 | Lỗi gốc của BDD | Đo trên tập kiểm tay rồi hiệu chỉnh |
| Q12 | Guideline thật | Không có, tự viết biến thể |
| Q13 | Đơn vị ngưỡng | Pixel chiều cao trên ảnh gốc |
| Q14 | Spec rule | LLM trích ngay từ đầu |
| Q15 | Detector | RT-DETR / mmdetection (Apache-2.0) |
| Q16 | VLM | Local (Qwen2.5-VL) |
| Q17 | Công cụ review | FiftyOne |
| Q18 | Ngôn ngữ | Tiếng Việt |
| Q19 | Kiểm ngẫu nhiên phần đuôi | 5% |
| Q20 | Mức lỗi sót chấp nhận | Tự đặt, ≤ 2% object |
| Q21 | Reviewer làm gì | Chỉ đánh dấu đúng/sai |

**Mâu thuẫn giữa các câu trả lời này và kế hoạch gốc (cần chốt lại):**

| Điểm | Kế hoạch gốc | Câu trả lời |
|---|---|---|
| Thời gian | 12 ngày × 4h, còn khoảng 7 ngày | "2 tuần" |
| Công cụ review | CVAT + Chrome extension + FastAPI | FiftyOne |
| Detector | YOLOv8n | RT-DETR |
| Kiểm tay | 50 ảnh | 500 ảnh × 2 người (≈ 25 giờ công, không vừa thời gian) |
| Phạm vi | Không có LLM/VLM | LLM trích spec + Qwen2.5-VL |
| Ai code | Chỉ lead code | Đã chốt: chia theo module cho cả 4 người |

Gợi ý khi thời gian ngắn: giữ kế hoạch gốc, thêm phần cốt lõi của 4.1 (spec viết tay, lọc theo spec, rule ID), kiểm tay 150–200 ảnh, bỏ VLM và LLM trích spec (ghi là hướng phát triển).

**Đã chốt 11/10:** LLM đọc guideline → spec YAML (mỗi luật kèm câu trích + trang) → người duyệt → rule engine (phép C) chạy 100% ảnh; luật phải nhìn ảnh giao cho VLM trên top 30%. Bước LLM làm ở Vòng 2 / Mốc 2; VLM vẫn ở Vòng 4, cắt nếu trễ. Chi tiết: mục 3 của `de-xuat.html`.

## 6. Bài học từ 3 tuần gán nhãn (dùng cho M13)

- **Review bằng mắt bỏ sót lỗi tên nhãn** (tuần 2: điểm đặt đúng nhưng tên trái/phải bị đảo). Kiểm theo luật tự động bắt được ngay → luận cứ cho rule engine.
- **Guideline không ghi rõ là nguồn lỗi lớn nhất** (P-001 tuần 1: ngưỡng vật xa/nhỏ/mờ; đèn giao thông lẫn nguồn sáng; box khi vừa occluded vừa truncated; car hay truck) → luận cứ cho chấm theo guideline.
- **Review không để lại dấu vết** trên CVAT (0 issue) → hàng đợi cần ghi lại verdict và thời gian xem.
- Số liệu thô: khoảng 30 phút gán mỗi frame, review khoảng 1 giờ mỗi job.

## 7. Chia việc (đã chốt, chi tiết ở `CONTRIBUTING.md`)

Chia theo module, mỗi người chỉ sửa thư mục của mình:

| Người | Vai | Việc | Chỉ sửa trong |
|---|---|---|---|
| Cường | ML lead, ghép code | Chấm điểm, GBM, học lại, đánh giá, CLI | `src/scoring/`, `src/eval/`, `src/cli.py`, `configs/` |
| Sơn | BE: dữ liệu | Tải dữ liệu, chạy YOLO, so YOLO với nhãn, hàm vẽ box | `src/features/model_disagreement.py` |
| Tú Anh | BE: API + extension | API, review DB, side panel, nút review, mở frame CVAT | `src/api/`, `extension/` |
| Long | BA | Spec guideline, kiểm tay (cùng Sơn), pilot, báo cáo | `configs/guidelines/`, `src/features/guideline_rules.py` |

**3 quy ước để ghép code:**
1. Tín hiệu trả về `SignalResult(name, value 0–1, reason tiếng Việt có con số)`.
2. `data/yolo_preds.parquet`: `image_id, x1, y1, x2, y2, category (tên class BDD), conf`.
3. `reports/ranked_queue_*.csv`: `image_id, risk_score, rank, top_reasons, model_version`.

**Thứ tự để không ai phải chờ:** Sơn tải dữ liệu trước tiên; Cường tạo sẵn file mẫu cho 2 quy ước trên để Sơn và Tú Anh code trước khi có dữ liệu thật; YOLO chạy nền trong lúc viết phần so khớp; kiểm tay 100 ảnh ngẫu nhiên làm trước, 100 ảnh top hàng đợi làm sau.

**Git:** repo private chung; mỗi việc một nhánh `<loại>/<tên>-<việc>` tạo từ `develop`, PR vào `develop`; chỉ Cường merge, `develop` vào `main` khi dự án hoàn thành; `git pull --rebase` mỗi sáng; PR nhỏ, merge trong ngày; `pytest -q && ruff check .` trước khi mở PR; Cường review và merge; không đưa dữ liệu/ảnh/model vào git (chia qua Drive).

**Báo cáo tiến độ: 22:30 mỗi tối**, mẫu:
```
Báo cáo [tên] · [ngày]
Done:      việc đã xong (link PR)
Doing:     đang làm, xong khoảng bao nhiêu %
Blocked:   đang chờ ai / chờ gì
Link:      PR, file, ảnh kết quả
Questions: câu hỏi cho nhóm
```

## 8. Ghi chú kỹ thuật Mốc 1

Thiết kế đã thống nhất cho Mốc 1 (loader, chấm điểm rule và metric đã có trong base; tiêm lỗi và tín hiệu hình học làm tiếp theo thiết kế này):

- **Loader:** đọc JSON danh sách frame của BDD100K (`name`, `attributes.weather/scene/timeofday`, `labels[].box2d/category/attributes.occluded/truncated`). Bỏ nhãn không có `box2d`. Chuẩn hoá tên class: `person→pedestrian`, `motor→motorcycle`, `bike→bicycle`. Giữ cả ảnh không có object. Ảnh 1280×720.
- **Tiêm lỗi:** làm trên JSON gốc để giữ định dạng; chỉ chọn ảnh có ít nhất 1 box; mỗi object chỉ bị 1 lỗi; clip box vào khung ảnh. File đáp án `injected_errors.json` gồm `meta` (seed, trọng số), `image_order` (cho baseline thứ tự file), `splits` (image_id → split), `errors` (image_id, split, type, obj_id, category, box trước/sau).
- **Tín hiệu hình học:** z-score của log diện tích và log tỉ lệ khung theo từng class (median/MAD, tính trên chính file nhãn); box chạm mép mà không có truncated; hai box cùng class trùng IoU > 0.5; hai box khác class trùng IoU > 0.7; class hiếm (< 1%); ảnh đông (theo bách phân vị 75–99); nhiều box nhỏ < 20px; điều kiện khó (đêm, mưa, tuyết, sương).
- **Chấm điểm:** trung bình có trọng số các tín hiệu × 100; top 3 lý do theo `value × weight`; hoà điểm thì xếp theo `image_id`.
- **Đánh giá:** recall theo ảnh và theo lỗi có trọng số, Precision, NDCG, time saved (random trung bình 20 seed), recall theo loại lỗi, gain curve; mỗi lần chạy ghi một dòng vào `reports/results.jsonl` kèm commit, seed, split.
- **Tốc độ tham khảo** (bản thử trên 10k ảnh giả lập): tiêm lỗi 1,5 giây, chấm điểm 30 giây.

## 9. Việc còn phải chốt

1. Công cụ review: CVAT + Chrome extension (kế hoạch gốc) hay FiftyOne.
2. Detector: YOLOv8n (AGPL-3.0) hay RT-DETR / mmdetection (Apache-2.0).
3. Số ảnh kiểm tay: đề xuất 150–200 ảnh × 2 người.

Đã chốt: thêm bước chấm theo guideline (11/10); chia code theo module cho cả 4 người.
