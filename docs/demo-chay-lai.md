# Dựng lại demo review M13

Chạy lệnh từ gốc repo. Hướng dẫn dùng cấu hình và ID của máy đang cài; không chép
DB, credentials hay mapping từ máy khác. Bằng chứng của từng phiên thuộc mô tả PR
và dữ liệu local, không thuộc tiến độ chung. Việc chưa merge chưa được tính Done.

## 1. Môi trường và cấu hình máy

Trên máy mới có Python 3.11 hoặc 3.12 và uv:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,demo,guideline,browser]"
```

Máy đã có môi trường hoạt động chỉ activate/cập nhật dependency; không tạo lại
`.venv`. Chạy kiểm tra theo mục 8. Docker Engine và Compose chỉ cần cho CVAT.

Đặt URL/cổng theo máy của bạn. Các giá trị dưới là mặc định local dùng chung,
không phải ID/cổng của phiên nghiệm thu. Nếu bị chiếm, chọn cổng khác.

```bash
export M13_CVAT_URL=http://localhost:8080
export M13_API_PORT=8000
```

Extension chỉ hỗ trợ HTTP localhost/127.0.0.1. CVAT thường định tuyến theo hostname
`localhost`; dùng đúng hostname được cấu hình. API và CVAT là hai dịch vụ riêng.

Tài khoản CVAT đặt trong môi trường terminal chạy import/API. Có thể dùng file
riêng không nằm trong Git chứa `CVAT_USER` và `CVAT_PASSWORD`, rồi source file đó
với `set -a`/`set +a`. Không đưa mật khẩu vào lệnh, ảnh chụp hoặc package. Gemini
không cần cho demo fixture; key phục vụ guideline đọc từ môi trường riêng.

## 2. CVAT hiện có hoặc máy mới

Nếu đã có CVAT, giữ nguyên stack/volumes và đăng nhập ở `$M13_CVAT_URL`; bỏ bước dựng
mới. Nếu source bind mount đã mất, chỉ dùng `cvat-restore-source --out <source-dir>`
sau khi kiểm đúng đường dẫn nguồn; công cụ không ghi đè nội dung khác.

Trên máy mới, chuẩn bị bộ Compose ghim phiên bản từ `configs/cvat-install.yaml`.
Chọn project và cổng mới, khác stack đang dùng:

```bash
python -m src.cli cvat-prepare --out data/cvat-install
python -m src.cli cvat-preflight data/cvat-install --out data/cvat-preflight.json
docker compose -f data/cvat-install/docker-compose.yml config --quiet
```

Đọc `install.json` để lấy project/cổng thật. Chỉ khi quyền Docker, tài nguyên và
cổng cho phép mới chạy:

```bash
docker compose -f data/cvat-install/docker-compose.yml up -d
docker compose -f data/cvat-install/docker-compose.yml exec cvat_server \
  python manage.py createsuperuser
```

Sau đó đặt lại `$M13_CVAT_URL` theo cổng của bộ cài. Tài khoản tạo tương tác, không
lưu mật khẩu trong hướng dẫn. Không dùng `down -v`. Kiểm Compose không đồng nghĩa
đã dựng mới thành công. Bộ cài không phục hồi dashboard analytics đã mất.

## 3. Fixture: chạy UI và phép kiểm thật khi chưa có ảnh BDD

Chọn thư mục mới. Lệnh sau tạo 3 ảnh tổng hợp, nhãn, queue/evidence/manifest và gói
extension; không tạo detector predictions:

```bash
python -m src.cli review-fixtures --scored --out data/demo-qc --url "$M13_CVAT_URL"
python -m src.cli review-connect data/demo-qc/review \
  --url "$M13_CVAT_URL" --name m13-qc-fixture
```

Task mới và ID thật được ghi trong `data/demo-qc/review/review.json`. Tên task phải
chưa tồn tại; retry dùng cùng tên/task đã đăng ký, không ghi lại annotations.
Chạy lại `review-fixtures --scored` giữ DB/mapping/queue và từ chối nguồn đã sửa.

```bash
source data/demo-qc/review/runtime.env
python -m src.cli doctor --verify-cvat --out data/demo-qc/doctor.json
python -m src.cli serve --port "$M13_API_PORT"
```

Chỉ rule `edge_no_trunc` chạy trên ảnh tổng hợp, dùng tham số của config. Nó kiểm
chạm mép nhưng thiếu truncated; không kiểm box ôm sát hình chiếc xe. Ảnh đầu có
điểm dương. Sau khi kéo box rời mép, Save và QC lại thì điểm về 0. Đây không phải
nghiệm thu detector, guideline, BDD hoặc pilot.

`demo-prepare --image <JPEG/PNG>` là lựa chọn ảnh chưa có nhãn: queue
manual-unscored, không có điểm QC. `review-fixtures` không có `--scored` là fixture
UI cũ có predictions tổng hợp được đánh dấu; không dùng chúng làm detector thật.

## 4. 10 ảnh BDD khi đã có dữ liệu tương ứng

Lấy bundle nhóm đã chốt và thư mục ảnh BDD2018 tương ứng từ Sơn. Không thay bằng
ảnh khác hoặc đổi tên ảnh. Giải nén bundle vào thư mục mới:

```bash
python -m src.cli review-unpack <bundle.zip> --out data/input
sha256sum data/input/data/bdd100k/labels/det_20/det_val.json
```

Checksum nhãn phải là
`f7cde1a3bc064b2cbd2ffbcf58b29889e7396f4a4176fd17e3d93e08dfb4ff00`.
Đặt `M13_INPUT_IMAGES` đến thư mục ảnh trên máy; đường dẫn này chỉ nằm trong cấu
hình local. Queue mặc định `rule-v1.2` ở `configs/review_acceptance.yaml`. Nếu
Cường chốt queue khác, dùng `--queue` trỏ CSV cùng manifest và artifact tương ứng.

```bash
python -m src.cli review-prepare --bundle data/input --images "$M13_INPUT_IMAGES" \
  --out data/review-10 --limit 10 --purpose real --url "$M13_CVAT_URL"
python -m src.cli review-connect data/review-10 --url "$M13_CVAT_URL" --name m13-bdd-review
source data/review-10/runtime.env
python -m src.cli doctor --verify-cvat --out data/review-10/doctor.json
python -m src.cli serve --port "$M13_API_PORT"
```

Công cụ kiểm hash, ảnh 1280×720, đúng tập ID, evidence/features và labels snapshot.
Không tự tính lại điểm khi chuẩn bị; không thay snapshot bằng nhãn khác. Snapshot
đã tiêm lỗi được nhận diện khác nhãn gốc. Queue không có manifest không thể recheck.
Ghi bảng từng ảnh: image_id, frame/ảnh đúng, evidence đúng box, verdict lưu, timer,
Save/recheck, lỗi tích hợp. Chưa có ảnh thì bảng phải để chưa kiểm.

## 5. Chrome extension, QC và restart

Nạp thư mục `extension/` hoặc giải nén gói extension của batch. Trong
`chrome://extensions`: Developer mode → Load unpacked. Khi code đổi: Reload
extension **và reload trang CVAT**. Ghim icon QC trên thanh Chrome.

Mở job theo task/ID trong `review.json`. Bấm icon QC hoặc nút QC nổi để mở bảng;
bấm icon lần nữa hoặc nút đóng để đóng. Click ngoài, kéo box, Save/chuyển frame
không đóng bảng. Kéo cạnh trái bảng để đổi chiều rộng.

Bảng → ⚙: API `http://127.0.0.1:<M13_API_PORT>`, reviewer thật, session riêng, batch
trống, priority → Lưu. Chọn ảnh từ hàng đợi. Sửa → **Save trong CVAT** → **Kiểm tra
nhãn đã lưu**. Nút QC đọc tọa độ đã Save rồi chấm lại bằng backend; tạo version và
snapshot mới. Nhãn chưa Save bị bỏ qua. Backend thiếu/bị chặn thì báo lý do và giữ
điểm cũ. Điểm 0 chỉ là chưa phát hiện lỗi qua phép kiểm đang bật.

Ba verdict: Xác nhận lỗi/error, Cảnh báo nhầm/false_alarm, Bỏ qua/skip. Có chọn box
và ghi chú trong phần chi tiết. Phím 1/2/3 chỉ hoạt động khi focus trong bảng;
timer dừng khi focus bảng, sai frame hoặc mất focus cửa sổ/tab. Verdict không thay
Save nhãn, điều hướng ảnh không tự ghi verdict. Thống kê có trong bảng; API root
không phải giao diện, dùng `/docs` để kiểm API.

Restart bằng Ctrl+C trong đúng terminal API này rồi source lại cùng runtime.env
và chạy cùng lệnh serve. Không xoá DB và không chạy hai API cho cùng DB. Queue
active, version, snapshot và verdict phải còn sau restart. Với queue đã đổi, dùng
`/stats?queue_id=<snapshot-id>` để xem thống kê lịch sử.

## 6. Audit còn chờ Long

Code hiện chèn một ảnh nửa dưới sau mỗi 10 ảnh ưu tiên, seed từ config. Đây chưa
phải định nghĩa cuối. Cần Long chốt vùng lấy mẫu, tỷ lệ/mẫu số và cách trộn trước
khi sửa policy. Không tự chọn tỷ lệ hoặc đánh dấu ảnh audit trên giao diện.

## 7. Pilot 30 ảnh: chỉ người thật mới đăng ký

Chuẩn bị từ queue nhãn gốc `rule-v1.2-goc`, cùng 30 ảnh, hai task/DB riêng:

```bash
python -m src.cli review-prepare --bundle data/input --images "$M13_INPUT_IMAGES" \
  --out data/pilot-a --pilot --purpose real --url "$M13_CVAT_URL"
python -m src.cli review-prepare --bundle data/input --images "$M13_INPUT_IMAGES" \
  --out data/pilot-b --pilot --purpose real --url "$M13_CVAT_URL"
python -m src.cli review-connect data/pilot-a --url "$M13_CVAT_URL" --name m13-pilot-priority
python -m src.cli review-connect data/pilot-b --url "$M13_CVAT_URL" --name m13-pilot-file
```

Cường và Tú Anh chọn hai người khác nhau, chưa xem chính batch đó. Mỗi người tạo
plan JSON local có reviewer, session_id, comparison_id, order (`priority` hoặc
`file`); cùng comparison_id. File order là thứ tự image_id. Không review cùng
batch hai lần bằng cùng người. Mỗi terminal source runtime.env của đúng arm.
Chỉ người dùng chủ động xác nhận trước khi đo:

```bash
source data/pilot-a/runtime.env
python -m src.cli pilot-register --plan data/pilot/plan-a.json --confirm-human
python -m src.cli serve --port "$M13_API_PORT"
```

Arm B dùng runtime.env/plan-b và cổng API khác. Đặt reviewer/session/order đúng
plan trong bảng. Queue pilot đóng băng; recheck bị chặn để giữ snapshot. Các phiên
fixture/development không được đăng ký thành human_pilot. Sau khi review:

```bash
source data/pilot-a/runtime.env
python -m src.cli pilot-export --out data/pilot/export-a.csv --session-id <session-a>
source data/pilot-b/runtime.env
python -m src.cli pilot-export --out data/pilot/export-b.csv --session-id <session-b>
python -m src.cli pilot-compare data/pilot/export-a.summary.json \
  data/pilot/export-b.summary.json --out data/pilot/compare.json
```

Export tạo CSV **và summary JSON**; compare đọc summary. Gửi export/summary/compare
qua Drive và số phút, số ảnh lỗi, skip trong PR; không commit. Retry không tạo
verdict trùng, skip không tính là nhãn đúng. Hai người có tốc độ khác nhau, kết
quả nhỏ này chỉ mô tả. Agent không đăng ký hoặc tạo số liệu pilot người thật.

## 8. Kiểm tra trước bàn giao

```bash
python .github/scripts/check_repo.py
ruff check .
pytest -q
playwright install chromium
M13_BROWSER_TESTS=1 pytest -q -rs tests/test_extension_browser.py tests/test_guideline_editor_browser.py
python -m src.cli extension-pack --out data/extension.zip
```

Browser tests dùng transport CVAT mock; muốn nghiệm thu runtime phải kiểm task
fixture mới hoặc batch BDD thực tế và ghi bằng chứng riêng. Thời gian cài, import
và review chưa được đo trên máy của người đọc. Không coi hướng dẫn là nghiệm thu
máy sạch; không coi môi trường cô lập trên cùng máy là máy thứ hai.
