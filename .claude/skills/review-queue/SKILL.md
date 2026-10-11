---
name: review-queue
description: Phần người QC dùng trực tiếp — FastAPI phục vụ hàng đợi review đã xếp hạng, lưu verdict (Lỗi thật / Bot nhầm / Bỏ qua) và thời gian xem, Chrome extension MV3 side panel mở đúng frame trong CVAT, hoặc phương án FiftyOne. Dùng khi code src/api/, extension/, endpoint /queue /verdict, DB review, tích hợp CVAT/FiftyOne, hiển thị lý do và box nghi vấn cho reviewer, hoặc chạy pilot đo thời gian review thật.
---

# Hàng đợi review cho người QC

Người dùng cuối là reviewer đang mở CVAT. Mọi thiết kế ở đây phục vụ một việc: **reviewer biết ngay nhìn vào box nào và bấm một nút để ghi kết quả**. Bài học 3 tuần trước: review trên CVAT không để lại dấu vết (0 issue) — nên hệ thống phải tự ghi verdict và thời gian.

Công cụ review chưa chốt: kế hoạch gốc là **CVAT + Chrome extension + FastAPI**, Q17 nói **FiftyOne**. Giữ API là lõi chung; giao diện là lớp mỏng để đổi được. Nếu nhóm chưa chốt, làm theo kế hoạch gốc (đã có khung, và nhóm đã có extension V1 trong CVAT).

## API (`src/api/`)

| Endpoint | Việc |
|---|---|
| `GET /health` | trạng thái + `model_version` đang phục vụ |
| `GET /queue?batch=&limit=&offset=` | đọc `reports/ranked_queue_*.csv` mới nhất, trả `image_id, rank, risk_score, top_reasons, evidence, cvat_url`, bỏ ảnh đã có verdict |
| `GET /image/{image_id}` | chi tiết: mọi lý do, box nghi vấn (từ `evidence`), dự đoán model khớp được |
| `POST /verdict` | `{image_id, verdict: "error"|"false_alarm"|"skip", reviewer, seconds_spent, note?, obj_ids?}` |
| `GET /stats` | số đã review, tỉ lệ lỗi thật theo khoảng rank, thời gian trung bình |

- Lưu verdict bằng SQLite (`data/review.db`) — đủ cho một nhóm nhỏ, không cần server DB. Bảng `verdicts` **chỉ thêm, không sửa**; verdict mới cho cùng ảnh là một dòng mới (giữ lịch sử để đo đồng thuận).
- Ghi kèm `model_version` và `rank` lúc reviewer thấy ảnh — để sau này biết verdict đến từ hàng đợi nào.
- Ảnh audit (5% ngẫu nhiên, xem `risk-scoring`) trộn vào hàng đợi nhưng **không đánh dấu khác biệt trên giao diện**, nếu không reviewer sẽ xem lướt chúng. Cờ `is_audit` chỉ lưu ở server.
- CORS chỉ mở cho origin CVAT đang dùng và `chrome-extension://<id>`.
- Pydantic model cho request/response; test bằng `fastapi.testclient.TestClient` với DB tạm (`tmp_path`).

## Chrome extension (`extension/`, MV3)

- Side panel: danh sách hàng đợi, mỗi dòng gồm rank, điểm, 3 lý do; bấm → mở frame tương ứng trong tab CVAT (`/tasks/<task>/jobs/<job>?frame=<n>` — giữ bảng `image_id → task/job/frame` ở server, sinh lúc import vào CVAT).
- Ba nút lớn: **Lỗi thật / Bot nhầm / Bỏ qua**, có phím tắt (1/2/3). Q21: reviewer chỉ đánh dấu đúng/sai — không bắt họ điền form.
- Đồng hồ: bắt đầu khi frame mở, dừng khi bấm verdict → `seconds_spent`. Dừng đếm khi tab mất focus.
- Lý do hiển thị nguyên văn tiếng Việt, rule ID in đậm nếu có (`[R4] …`).
- Không gọi API từ content script trực tiếp; đi qua service worker (tránh vướng CORS/CSP của CVAT).
- Có thể tái dùng khung extension V1 Guideline Assistant (đã chạy trong CVAT).

## Nếu chọn FiftyOne

Nạp ảnh + nhãn + dự đoán model thành dataset; thêm field `risk_score`, `reasons`, `rank`; sort view theo `rank`; tag `error`/`false_alarm` thay cho nút. Xuất tag ra cùng bảng `verdicts` để phần học lại và đánh giá không phải đổi.

## Pilot (Mốc 4)

- Hai cách xem trên cùng số ảnh: theo hàng đợi vs ngẫu nhiên, cùng reviewer, đổi thứ tự để khử hiệu ứng học.
- Báo: lỗi thật / giờ review, thời gian trung bình mỗi ảnh theo khoảng rank, phản hồi của reviewer về lý do (lý do nào vô ích).
- Số liệu thô đã có: ~1 giờ review mỗi job CVAT trước đây — dùng làm mốc so sánh.
