# Chạy demo và tiếp tục phần Tú Anh

Checkpoint 11/10/2026: API, SQLite và Chrome extension chạy với CVAT v2.74.1 thật trên **1 máy Ubuntu**. Ảnh, nhãn, predictions và queue hiện là fixture; chưa nghiệm thu QC trên BDD100K, Gemini thật, ML thật hoặc pilot. Ba DOCX đã render PDF/trích draft bằng response fixture, chưa được người duyệt.

## Chạy ngay trên máy này

```bash
cd /home/nguyen-tu-anh/Documents/qc2d_auto_assistant
source .venv/bin/activate
source data/samples/review/demo.env
source data/cvat-runtime/account.env
python -m src.cli doctor
python -m src.cli serve
```

API tại http://127.0.0.1:8000/docs, CVAT tại http://localhost:8080. Nếu API đang chạy sẵn, không khởi động bản thứ hai. Tài khoản CVAT nằm trong `data/cvat-runtime/account.env` (quyền 0600, không commit); mật khẩu CVAT khác mật khẩu sudo. Không gửi nội dung file này vào nhóm.

Chrome → `chrome://extensions` → Developer mode → Load unpacked → chọn thư mục `extension/`. Hoặc giải nén `data/packages/m13-review-extension.zip` rồi load thư mục đó. Mở side panel, đặt reviewer, API local, session mới, thứ tự ưu tiên và để batch trống. Chọn ảnh → mở frame CVAT → sửa/lưu nhãn bằng **Save trong CVAT** → gửi Lỗi thật/Bot nhầm/Bỏ qua. Phím 1/2/3 chỉ dùng trong panel, không khi nhập ghi chú. Stats và verdict không thay việc lưu nhãn CVAT.

Session `automated-cvat-fixture` chứa một verdict kiểm tra tự động, không phải pilot. Dùng session khác cho lượt thao tác của bạn; không xoá DB để chạy lại demo.

## Khởi động lại CVAT

Dùng source Ubuntu có sẵn, không cần chép Windows Docker VHDX:

```bash
sudo docker compose -p m13_qc2d \
  -f /home/nguyen-tu-anh/Documents/cvat-lidar-autoqc/cvat-day2/docker-compose.yml \
  -f /home/nguyen-tu-anh/Documents/qc2d_auto_assistant/configs/cvat-local.override.yaml up -d
```

Override cần Docker Compose >=2.24.4 để hiểu `!override`; phiên này đã cài Compose 2.40.3. Cổng chỉ bind loopback. Host routing dùng `localhost`, không đổi CVAT URL sang 127.0.0.1 khi source chưa đổi routing. Sau khi tải Docker images ổ còn khoảng 37 GiB; không mount/xoá VHDX Windows. Khi không dùng có thể chạy cùng lệnh với `stop` thay `up -d`; không dùng `down -v` vì sẽ xoá dữ liệu.

## Fixtures và mapping

```bash
python -m src.cli samples
python -m src.cli review-fixtures
python -m src.cli cvat-sync --url http://localhost:8080 --task-id 1 \
  --queue data/samples/review/ranked_queue_fixture-review-v1.csv \
  --out data/samples/review/cvat_map.parquet
python -m src.cli extension-pack
```

Task #1 đã có trên máy này, không import lại cùng tên. Trên máy khác hoặc batch mới:

```bash
python -m src.cli cvat-import --name 'M13 demo batch mới' \
  --queue data/samples/review/ranked_queue_fixture-review-v1.csv \
  --images data/samples/review/images --labels data/samples/review/labels.json \
  --url http://localhost:8080
```

Sau import, dùng task ID trả về để sync. Mỗi máy có task/job/frame riêng. Tên trùng/mapping mơ hồ phải sửa hoặc giới hạn `--task-id`, không đoán frame. Import chỉ tạo task mới và xác minh nhãn đọc lại; không ghi đè task cùng tên.

Khi Sơn/Cường có đầu vào thật, đặt `M13_IMAGES`, `M13_PREDICTIONS`, `M13_QUEUE_FILE`, `M13_EVIDENCE_FILE`, `M13_MAPPING`, `M13_DATABASE`; không source `demo.env` sau đó. Nạp nhãn vào task mới và sync đúng queue. CSV/parquet giữ nguyên contracts. Evidence JSONL riêng có `{image_id, boxes:[{obj_id, box:[x1,y1,x2,y2], note, signal}]}`. Có thể cấu hình `queue_batches` trong `configs/review.yaml`.

## Chính sách API và backend ML

`/queue` mặc định bỏ ảnh đã review theo queue hash, reviewer, session và thứ tự. Queue hash thay đổi thì là snapshot mới; verdict cũ vẫn còn trong lịch sử. `include_reviewed=true` để xem lại; gửi review lại dùng request_id mới. Retry cùng nội dung/request_id không thêm record; snapshot cũ bị từ chối 409.

`/image/{id}` trả metadata; `/image/{id}/file` trả bytes. Evidence/mapping thiếu chỉ cảnh báo; queue hỏng trả 503. Đồng hồ chỉ đo tab/frame CVAT đang được focus, không tính thời gian sửa ở tab khác. Stats tách số lượt/lịch sử với số ảnh/verdict mới nhất; skip không vào mẫu số tỷ lệ lỗi.

`configs/review.yaml` theo HTML: 50 verdict mới không tính skip/retry, gate recall@20% val giảm tối đa 0.005, audit seed 42 sau mỗi 10 ảnh ưu tiên lấy từ nửa dưới. Audit không có dấu hiệu riêng trong panel. Không sửa `configs/learning.yaml` của nhóm. Thứ tự file cho pilot không chèn audit.

`retrain_backend: package.module:function` phải là callable nhận `verdicts, current_model, seed, validation_split, top_fraction`; trả `model_version, queue_file, validation_split='val', metric='recall@20%', recall_before, recall_after`. Backend chịu trách nhiệm split theo ảnh, training/validation thật và ghi artifact/queue mới bất biến. Adapter không huấn luyện GBM thay Cường. `/retrain` trả 503 khi chưa có backend, `/model` cho biết tình trạng; `/model/rollback` nhận `{model_version: ...}` và chỉ chọn version đã được ghi nhận.

## Guideline

```bash
python -m src.cli guideline samples
python -m src.cli guideline extract data/samples/guidelines/fixture-guideline-1.docx \
  --fixture-response data/samples/guidelines/fixture-guideline-1.response.json
```

Lặp tương tự cho 2 và 3. LibreOffice phải có để DOCX → PDF; PDF scan không text cần xử lý riêng. Draft và PDF nguồn/hash được lưu để người duyệt đối chiếu. Response fixture được đánh dấu, không phải Gemini thật. Với tài liệu thật, đặt `GEMINI_API_KEY` trong môi trường local rồi chạy extract không có `--fixture-response`. Model/schema mode ở `configs/guideline_extract.yaml`. Key không vào cache/log/Git.

Người duyệt đọc đúng PDF đã render, kiểm classes/merge/ngưỡng/quote/page và unclear; sau đó mới chạy:

```bash
python -m src.cli guideline approve configs/guidelines/drafts/FILE.yaml \
  --approved-by 'Tên người đã kiểm tra' --confirm-reviewed
```

Agent chưa duyệt thay người. `src.guideline.extract.load_approved` chặn draft; cần ghép vào rule engine của Long, hiện còn stub. Không tuyên bố pipeline guideline/scoring thật đã hoàn tất.

## Pilot và video còn lại

Pilot cần người thật và batch thật. Đặt session riêng, review cả `priority` và `file` trên cùng batch. Đối trọng giữa reviewer (A ưu tiên trước, B file trước), giữ snapshot/budget thời gian cố định, có khoảng nghỉ và báo ảnh hưởng nhớ ảnh. Để so sánh việc sửa nhãn, dùng hai task ban đầu giống nhau; không dùng task đã sửa của lượt trước làm đầu vào lượt sau. So sánh lỗi xác nhận/giờ, số ảnh, tổng thời gian và false alarm; không trộn session tự động vào số liệu.

```bash
python -m src.cli pilot-export --reviewer 'Tú Anh' --session-id pilot-a \
  --out data/pilot/pilot-a.csv
```

CSV giữ mọi sự kiện đo được; `.summary.json` tách session/order. Export không tự chứng minh pilot đạt nghiệm thu.

Kịch bản video tối đa 3 phút: 0:00–0:35 nguồn guideline/PDF → draft → người duyệt; 0:35–1:00 scoring thật → queue/evidence; 1:00–2:20 extension → đúng frame → sửa box/Save CVAT → verdict; 2:20–3:00 stats/restart/version. Hiện chưa quay video vì chưa đủ upstream thật. Nếu quay bản thử, phải ghi rõ fixture và những bước chưa tích hợp.

## Kiểm tra và bằng chứng

```bash
pytest -q
ruff check .
M13_BROWSER_TESTS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/m13-browsers pytest -q tests/test_extension_browser.py
```

Browser test cần extra `browser` và Chromium Playwright; đường dẫn /tmp trên chỉ áp dụng máy này. Unit test dùng DB tạm/mock. Nếu TestClient/Chrome không chạy trong sandbox Codex thì chạy với quyền socket phù hợp; không sửa sản phẩm để né sandbox.

Kết quả chốt: 46 passed/2 skipped, Ruff sạch; browser opt-in trước đó 1 passed. Kiểm tra Chrome + CVAT thật bằng fixture: sửa/lưu occluded qua UI, đọc lại nhãn và lưu verdict/stat. Bằng chứng không commit: `data/cvat-runtime/integration-evidence.json`, `cvat-saved.png`, `extension-saved.png`. Chỉ kiểm tra một máy, chưa pilot/video hay nghiệm thu dữ liệu thật.
