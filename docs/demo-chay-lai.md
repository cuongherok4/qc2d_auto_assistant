# Chạy lại demo review M13

Nhánh bàn giao: `feat/tuanh-review-that`, dựa trên develop `4af8938`.
Code đã được kiểm để nộp qua nhánh riêng; chưa merge vào `develop`/`main`.

**Đã thực hiện:** tải và kiểm hash gói Cường, giải nén cô lập, khôi phục Python
3.11.17 ở `data/runtime/python311-stable`, giữ thư viện của `.venv`, kiểm các artifact
của hai queue `rule-v1.2` và `rule-v1.2-goc` (10.000 ảnh). File ảnh chưa có;
người dùng đã yêu cầu bỏ ZIP ảnh Sơn. CVAT đã trả HTTP 200 tại `localhost:8080`.
Import, mapping và review thật bên dưới còn
chờ thư mục ảnh tương ứng. Không coi bước hướng dẫn là nghiệm thu runtime.

## Giao diện mới: bảng QC bật/tắt trong CVAT

Vẫn là Chrome extension: không cài thêm hoặc sửa source CVAT. Nạp/Reload extension,
reload trang CVAT, ghim biểu tượng QC trên thanh công cụ Chrome. Bấm biểu tượng để
mở bảng, bấm lại để đóng; có nút QC nổi trong job và nút đóng trong bảng. Click
ngoài, kéo box, Save và chuyển frame không làm bảng tự đóng. Bảng rộng mặc định
390px, kéo cạnh trái để thay đổi; đóng bảng không che chuột CVAT. Reload trang giữ
trạng thái của tab. Timer dừng khi thao tác trong bảng, đổi frame hoặc mất focus;
phím 1/2/3 chỉ ghi verdict khi focus bên trong bảng.

Demo mới, task/DB riêng: http://localhost:8080/tasks/7/jobs/7, API cổng **8003**.
Task 6 và API 8002 trước đó được giữ nguyên. Ba ảnh tổng hợp; pipeline chạy thật
luật `edge_no_trunc`, không có detector/Gemini/ML và không phải pilot người thật.

Thử ngay:

1. `chrome://extensions` → Reload M13 Review Queue (nếu chưa có: Load unpacked →
   chọn thư mục `extension/`). **Reload cả trang CVAT** để nạp content script mới.
2. Mở job 7 ở trên, ghim icon QC trên Chrome rồi bấm. Có thể bấm nút QC nổi trong
   job nếu chưa ghim. Ngoài job CVAT, extension không mở bảng.
3. Bảng → ⚙: API `http://127.0.0.1:8003`, reviewer `Tú Anh`, phiên
   `tuanh-overlay-01`, batch trống, priority → Lưu cài đặt.
4. Chọn `fixture-ui-01`: 100 điểm. Kéo cả box sang phải để rời mép trái. Khi chưa
   Save, bấm QC vẫn kiểm nhãn cũ. Bấm Save trong CVAT, rồi nút **Kiểm tra nhãn đã
   lưu**: phải thấy 100→0 và phiên bản mới. Không cần bấm hai nút riêng.
5. Mở Tọa độ và chi tiết để xem Box 1/car, chọn evidence hoặc nhập ghi chú nếu cần.
   Chọn Xác nhận lỗi/Cảnh báo nhầm/Bỏ qua và mở Thống kê phiên.
6. Bấm icon QC lần nữa hoặc ✕ để đóng. Click canvas khi bảng đóng phải thao tác
   được. Mở lại, chuyển frame hoặc reload: trạng thái/selection phải được khôi phục.

API đang chạy. Nếu đã tắt, mở terminal mới và chạy (mỗi DB chỉ một process):

```bash
cd /home/nguyen-tu-anh/Documents/qc2d_auto_assistant
set -a
source data/cvat-runtime/account.env
source data/cvat-overlay-validation/demo/runtime.env
set +a
.venv/bin/python -m src.cli serve --port 8003
```

Gói extension: `data/cvat-overlay-validation/extension.zip` gồm 11 file, đủ logo,
icon PNG và content script; không có env/DB/credentials. Máy khác nạp extension
như bình thường, cấu hình API/CVAT riêng và sinh lại mapping bằng ID của máy đó.
Chưa nghiệm thu cài trên máy thứ hai.

Kiểm cuối: **159 passed, 5 skipped; Ruff sạch**. Bộ kiểm phần sửa có **12 passed**,
gồm 3 test Chromium. Kết quả ở `data/cvat-overlay-validation/verification.json`.

Bằng chứng CVAT thật: `data/cvat-overlay-validation/live-verification.json`,
`overlay-before.png`, `overlay-after.png`. Test Chrome bổ sung kiểm backend chưa
sẵn sàng, retry/mất phản hồi, đóng/mở/reload giữa lúc chờ QC không tạo request trùng,
focus/timer và phím CVAT bên ngoài bảng; transport CVAT trong các test này là mock.
Thay giao diện không tăng tỷ lệ nghiệm thu 5/8, không thay thuật toán hoặc contracts.

## Luồng đã kiểm trước khi đổi giao diện (ảnh fixture)

Task riêng: http://localhost:8080/tasks/6/jobs/6. API riêng: cổng 8002.
Ba ảnh tổng hợp 1280×720, không có detector predictions, không phải ảnh BDD.
Đã kiểm bằng Chromium + extension thật: mapping 3 frame, ảnh/evidence, đọc nhãn
đã Save, kéo box bằng chuột trong CVAT, Save bằng nút giao diện, rule
`edge_no_trunc` chấm **100 → 0 → 100** với snapshot/version mới, verdict/timer
và restart API giữ nguyên model/verdict. Trước Save vẫn đọc nhãn cũ; sau Save
điểm vẫn 100 cho tới khi chủ động chấm lại. Chạy lại prepare/connect giữ nguyên
task, annotations đã sửa và mapping. Verdict tự động thuộc development, không
được dùng làm pilot. Dữ liệu của các task trước được giữ nguyên.

Bằng chứng: `data/cvat-ui-validation/live-verification.json`,
`panel-before.png`, `cvat-after-save.png`, `panel-after-recheck.png`.
Ảnh đầu đã được kéo về sát mép và chấm lại 100 để người dùng thử từ đầu.

1. Mở Chrome, đăng nhập CVAT, mở job trên.
2. `chrome://extensions` → Reload M13. Nếu chưa có extension: Developer mode →
   Load unpacked → chọn thư mục `extension/` của repo.
3. Mở panel M13 → Cài đặt: API `http://127.0.0.1:8002`, reviewer `Tú Anh`, phiên
   `tuanh-ui-test-01` (lần thử khác dùng tên phiên mới), batch trống, priority.
4. Chọn `fixture-ui-01`: 100 điểm, box xanh kéo dài đến mép trái. Kéo **cả box**
   sang phải khoảng 150 pixel ảnh để không chạm mép. Bấm Save trong CVAT.
5. Panel → Đọc nhãn đã Save → Box 1/car có x1 lớn hơn 2 → Kiểm tra lại lỗi:
   phải thấy `100.0 → 0.0 điểm`. Luật demo chỉ kiểm chạm mép không truncated;
   không chứng minh box đã ôm sát vật thể.
6. Chọn verdict, mở Thống kê phiên. API root `/` không có giao diện;
   `http://127.0.0.1:8002/docs` là màn hình kiểm API.

API đã được để chạy. Nếu sau này API tắt, mở terminal mới và chạy:

```bash
cd /home/nguyen-tu-anh/Documents/qc2d_auto_assistant
set -a
source data/cvat-runtime/account.env
source data/cvat-ui-validation/demo/runtime.env
set +a
.venv/bin/python -m src.cli serve --port 8002
```

Chỉ chạy một API cho DB này. Để tự kiểm restart, Ctrl+C ở đúng terminal trên,
chạy lại cùng lệnh, Reload panel: model, snapshot và verdict phải còn.
BDD 10 ảnh, pilot người thật và dựng máy sạch vẫn chưa nghiệm thu.

**1. Môi trường và bộ dữ liệu**

```bash
cd /home/nguyen-tu-anh/Documents/qc2d_auto_assistant
source .venv/bin/activate
python --version
```

Python phải là 3.11/3.12 đúng `pyproject.toml`. Phiên này phục hồi 3.11.17; không
thay Python hệ thống và không xoá `.venv` hoặc `.env`. Runtime lưu trong repo/data
để không phụ thuộc interpreter trong `/tmp`.

ZIP đã tải: `data/downloads/m13-data-2018-14-10.zip`.
SHA256: `115136f31cff8658e1617fbb9835854f0c7fbeb88958dbf53350c932f7359da6`.

Nếu chưa giải nén, chạy một lần:

```bash
python -m src.cli review-unpack data/downloads/m13-data-2018-14-10.zip \
  --out data/m13-input-2018
sha256sum data/m13-input-2018/data/bdd100k/labels/det_20/det_val.json
```

Checksum nhãn phải là
`f7cde1a3bc064b2cbd2ffbcf58b29889e7396f4a4176fd17e3d93e08dfb4ff00`.
`review-unpack` từ chối thư mục đã có, path traversal, symlink, entry trùng và
file private. Thư mục `data/m13-input-2018` đã có trên máy này: không giải nén lại.

**2. Chuẩn bị batch review khi có ảnh**

Đặt `M13_INPUT_IMAGES` là thư mục chứa các file ảnh gốc theo image_id của BDD.
Không đổi tên ảnh khác để ghép vào queue. Chuẩn bị 50 ảnh đầu của `rule-v1.2`:

```bash
M13_INPUT_IMAGES=/duong/dan/toi/thu-muc-anh-val
python -m src.cli review-prepare --bundle data/m13-input-2018 \
  --images "$M13_INPUT_IMAGES" --out data/review-real-50 --purpose real
```

Công cụ kiểm hash source, checksum nhãn gốc, đúng số ảnh, kích thước 1280×720 và
khớp queue/evidence/features. Nó lấy **labels snapshot từ manifest**, giữ nguyên
điểm/lý do và ghi rõ `scores_recomputed: false`. `annotation_kind` phân biệt snapshot
gốc với nhãn đã thay đổi/tiêm lỗi. Queue demo này có thể dùng lỗi tiêm; số review đó
không tự trở thành đánh giá lỗi thật của nhãn gốc.

Batch có ảnh, labels, features, predictions, evidence, manifest và extension.zip;
`runtime.env` chỉ chứa cấu hình, không chứa credentials. DB/mapping nằm riêng trong
batch. Chạy lại giữ nguyên dữ liệu, từ chối artifact/cấu hình đã đổi và nguồn khác.

**3. Bật CVAT hiện có, import và mapping riêng**

Bật lại stack CVAT theo bộ Compose đã ghim phiên bản/project trên máy đó, mở
`http://localhost:8080`. Bước bật stack chưa kiểm trong phiên này; không tạo lại
volumes hoặc dùng `down -v`. Xem các lệnh `cvat-restore-source`, `cvat-preflight`
và cấu hình `configs/cvat-install.yaml` nếu source Compose đã mất.

Thiết lập `CVAT_USER`, `CVAT_PASSWORD` trong terminal bằng cấu hình riêng của máy;
không đưa vào lệnh chụp màn hình, Git hoặc package. Khi CVAT và credentials sẵn sàng:

```bash
python -m src.cli review-connect data/review-real-50 \
  --name m13-bdd2018-review-top50
source data/review-real-50/runtime.env
python -m src.cli doctor --verify-cvat
python -m src.cli serve --port 8002
```

Task mới được lưu trong `review.json` trước bước sync. Retry sau lỗi sync dùng lại
task này, không ghi lại annotations. Nếu mapping đọc lại khác thì từ chối ghi đè.
DB mới là `data/review-real-50/review.db`; các DB/task demo cũ được giữ nguyên.
Đổi cổng bằng `review-prepare --url ...` và dùng cùng URL ở `review-connect --url ...`.

**4. Extension, Save, recheck và stats**

Giải nén extension.zip vào thư mục mới hoặc nạp `extension/` bằng Chrome
`chrome://extensions` → Developer mode → Load unpacked. Reload extension khi code
đổi. Trong panel, đặt API `http://127.0.0.1:8002`, reviewer thật, session riêng,
batch trống, thứ tự priority.

Kiểm 10 ảnh đầu và ghi vào bảng: image_id, đúng frame, đúng box evidence, đọc được
lý do, verdict lưu, timer, Save/recheck. Bảng trong
`data/tuanh-review-validation/ten-image-checklist.csv` là **mẫu chưa kiểm**, không
phải kết quả nghiệm thu.

Sau khi sửa và Save trong CVAT: bấm Đọc nhãn đã Save, đối chiếu tọa độ, rồi Kiểm tra
lại lỗi. Phải có version/queue mới; điểm có thể giữ nguyên nếu phép kiểm cho cùng
kết quả. API giữ source queue, snapshot và verdict lịch sử. Thiếu manifest hoặc
nguồn bị sửa thì từ chối chấm lại. Verdict không thay thao tác Save nhãn.

Ba nút: Lỗi thật / Bot nhầm / Bỏ qua; phím 1/2/3. Timer dừng khi mất focus hoặc đổi
frame. Xem thống kê trong panel hoặc `http://127.0.0.1:8002/stats`. Stats mặc định
thuộc queue hiện tại; dùng `?queue_id=<id-cu>` để xem thống kê snapshot lịch sử.

Restart: dừng **API riêng này**, source lại cùng runtime.env và chạy lại cùng lệnh
serve. Không xoá DB. Phiên bản đang phục vụ được phục hồi từ DB, không quay về queue
ban đầu. Giữ API một process cho mỗi DB.

**5. Pilot 30 ảnh: hai task, hai người**

Để kiểm nhãn gốc, chuẩn bị hai batch từ `rule-v1.2-goc` với `--pilot`:

```bash
python -m src.cli review-prepare --bundle data/m13-input-2018 \
  --images "$M13_INPUT_IMAGES" --out data/pilot-a --pilot --purpose real
python -m src.cli review-prepare --bundle data/m13-input-2018 \
  --images "$M13_INPUT_IMAGES" --out data/pilot-b --pilot --purpose real
python -m src.cli review-connect data/pilot-a --name m13-pilot-priority
python -m src.cli review-connect data/pilot-b --name m13-pilot-file
```

Hai batch lấy cùng 30 ảnh đầu của queue nhãn gốc, cùng CSV/nhãn ban đầu, nhưng DB,
mapping và task riêng. `--pilot` không đăng ký người hoặc xác nhận human_pilot.
Nếu nhóm chọn batch khác, truyền queue nhãn gốc phù hợp; ghi đúng cách chọn batch.

Chỉ khi người dùng và Cường đã chọn hai reviewer khác nhau mới tạo plan JSON cho
từng người với: reviewer, session_id, comparison_id và order (`priority` hoặc
`file`). Hai plan cùng comparison_id. Thứ tự file trong API là thứ tự image_id.

Ở terminal A, source runtime.env của pilot-a, đăng ký người A rồi chạy API cổng 8002;
ở terminal B làm tương tự với pilot-b, người B, cổng 8003. Nếu cổng đã dùng thì
chọn cổng khác. Mỗi reviewer đặt API/session/order đúng với plan trong panel.

```bash
source data/pilot-a/runtime.env
python -m src.cli pilot-register --plan data/pilot/plan-a.json --confirm-human
python -m src.cli serve --port 8002
```

Người dùng chủ động chạy `--confirm-human`; agent không chạy thay. Không review
batch hai lần bằng cùng một người. Sau đăng ký giữ nguyên queue; recheck bị chặn
trong DB pilot để bảo toàn snapshot. Việc chấm lại sau đó dùng DB review riêng.

Sau review, export theo từng DB/session (thay SESSION_A/B bằng session đã đăng ký):

```bash
source data/pilot-a/runtime.env
python -m src.cli pilot-export --out data/pilot/export-a.csv --session-id SESSION_A
source data/pilot-b/runtime.env
python -m src.cli pilot-export --out data/pilot/export-b.csv --session-id SESSION_B
python -m src.cli pilot-compare --out data/pilot/compare.json \
  data/pilot/export-a.summary.json data/pilot/export-b.summary.json
```

Export ghi CSV **kèm summary JSON**; compare đọc summary, không đọc CSV. Báo số
phút, ảnh lỗi và skip; skip không tính là nhãn đúng. Chỉ phiên đã đăng ký human_pilot
được đưa vào export mặc định. 30 ảnh/tốc độ hai người chỉ cho kết quả mô tả.
Gửi dữ liệu qua Drive, không commit. Không có phiên người thật nào được đo bởi agent.

**6. Kiểm tra code và phần còn chờ**

```bash
python -m pytest -q
.venv/bin/ruff check .
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/runtime/browsers" M13_BROWSER_TESTS=1 \
  python -m pytest -q tests/test_extension_browser.py tests/test_guideline_editor_browser.py
```

Phiên này: pytest **159 passed, 5 skipped** trong 21.76 giây; Chromium **3 passed**
trong 27,24 giây; Ruff và diff check sạch. Kết quả/thời gian test mới được ghi trong
`data/tuanh-review-validation/verification.json`.
Thời gian tải/khôi phục chưa được đo riêng. Bộ test browser riêng dùng transport mock; luồng giao diện bổ sung phía trên đã
chạy với CVAT thật và ảnh tổng hợp. Chưa kiểm 10 ảnh BDD trên CVAT thật.

Audit giữ nguyên vì Long chưa chốt tỷ lệ/mẫu số/cách trộn. Chưa có ảnh, import batch
BDD, pilot người thật hoặc nghiệm thu dựng máy sạch. Tài liệu này ghi các lệnh đã
kiểm cú pháp/CLI và quy trình dự kiến; các bước runtime cần được chạy và ghi bổ sung.
