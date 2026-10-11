# Tiến độ Tú Anh

Phiên bắt đầu: 11/10/2026 16:35:22 Asia/Ho_Chi_Minh (09:35:22 UTC).
Hạn phiên: 11/10/2026 21:35:22 Asia/Ho_Chi_Minh (14:35:22 UTC).
Mục tiêu demo nhóm: tối 15/10/2026, trước thứ Sáu 16/10.

## Git và phạm vi

- Nhánh: `feat/tuanh-review-flow`, từ `origin/develop` (`a508ecc`).
- Đã fetch origin. `chore/cuong-phan-cong` đã nằm trong develop; cây file develop và main hiện giống nhau.
- Giữ nguyên `M13_DE_XUAT.html` chưa được Git theo dõi; không đưa file cá nhân này vào commit.
- Phạm vi nhận gồm API/CVAT/extension và LLM guideline theo yêu cầu người dùng.
- Không đổi contracts, detector, scoring, rule engine hoặc huấn luyện ML dùng chung.

## Checklist 18 việc

| # | Việc | Trạng thái | Bằng chứng / còn thiếu |
|---|---|---|---|
| 1 | Môi trường Python 3.11 và samples | Implemented | .venv Python 3.11.17; CLI samples đã tạo CSV/parquet; dữ liệu mẫu |
| 2 | CVAT local | Kiểm tra được 1 máy | Docker/Compose cài xong; CVAT v2.74.1 chạy, task #1 có 3 ảnh/3 box fixture |
| 3 | GET /queue | Implemented | Snapshot hash, batch, phân trang, reviewed/session, evidence, mapping; test fixture |
| 4 | GET /image/{id} và nội dung ảnh | Implemented | Metadata, predictions, nội dung ảnh; chặn traversal/symlink ra ngoài |
| 5 | POST /verdict + SQLite | Implemented | Append-only, UUID retry, stale context, restart/history/stats được test |
| 6 | cvat-sync | Kiểm tra API thật | 6 unit test và mapping 3 ảnh từ CVAT task #1; chưa BDD thật |
| 7 | Khảo sát V1 | Ghi chú đã viết | docs/tuanh-v1-note.md; không xác định source V1, backend Gemini mới |
| 8 | LLM guideline extract | Implemented | Gemini REST, schema/quote/cache/approval; 6 unit test, chưa gọi Gemini thật |
| 9 | CLI guideline extract và ba bản nháp | Implemented | 3 DOCX fixture -> PDF -> drafts; provider=fixture, approved_by trống |
| 10 | Extension MV3 | Kiểm tra Chrome thật | Queue, box, rule ID, pause, retry sau commit, cả 3 verdict; ZIP đã tạo |
| 11 | Review/frame/đồng hồ/phím tắt | Kiểm tra CVAT thật | Sửa occluded và Save qua CVAT UI, đọc lại nhãn; verdict và stats khớp |
| 12 | Stats và audit | Implemented | Một audit sau 10 ảnh top half, không trùng, cờ server; thống kê ảnh/lượt tách biệt |
| 13 | Retrain/model | Adapter implemented | Gate/rollback được test; backend GBM thật còn stub, /retrain trả 503 |
| 14 | Cài đặt/hoàn thiện 4 máy | Đã kiểm tra 1 máy | Hướng dẫn/ZIP có; còn 3 máy |
| 15 | Pilot đo thật | Chưa nghiệm thu | CLI export và quy trình có; thiếu batch thật/người review |
| 16 | Video <=3 phút | Kịch bản đã có | Chưa quay video; chưa luồng guideline/scoring thật đầy đủ |
| 17 | Test và PR | Test đạt, PR chưa mở | 46 passed, 2 skipped; Ruff sạch; docs/tuanh-pr.md; Git CLI thiếu credential |
| 18 | Báo cáo tiến độ | Đã soạn | docs/tuanh-report-2230.md; chưa gửi nhóm |

## Kế hoạch phiên

1. API/SQLite và tests, chạy samples.
2. CVAT REST sync và extension, kiểm tra luồng bằng fixtures được ghi rõ.
3. Guideline extract/provider/cache/approval và CLI.
4. Adapter model/retrain, docs/demo/pilot và kiểm tra cuối.

## Chênh lệch tham số

HTML: retrain sau 50 verdict mới, gate recall@20% giảm tối đa 0.005; một audit sau mỗi 10 ảnh từ nửa dưới.
`configs/learning.yaml`: batch_size=200, audit_rate=0.05, gate_metric=recall20_weighted.
Phần review sẽ dùng cấu hình riêng theo HTML; không tự sửa chính sách ML dùng chung.

## Quy tắc nghiệm thu

Phân biệt code/test fixture, tích hợp thật, cài máy, pilot, video, và PR merge. Test mock không được tính là demo QC trên dữ liệu thật. Thiếu upstream không được trả thành công giả.

## Mốc đã kiểm tra

- Kiểm tra nền: 12 passed, 1 skipped (thiếu BDD thật). TestClient treo trong sandbox; chạy ngoài sandbox 1.35s.
- API/SQLite mới: 14 passed; CVAT sync: 6 passed; guideline: 6 passed.
- Python 3.11 và uv đặt riêng, không đổi Python hệ thống.
- Người dùng xác nhận đầu vào Sơn/Cường/Long chưa có: tiếp tục fixtures, không yêu cầu họ cung cấp ngay.
- Người dùng chọn Gemini API. Chưa có GEMINI_API_KEY, chỉ kiểm REST bằng mock.
- SSD: Ubuntu còn ~44 GiB lúc kiểm tra, RAM ~11 GiB; CVAT source đã có trên cả Ubuntu và Windows.
- CVAT Ubuntu: ../cvat-lidar-autoqc/cvat-day2 (135 MB), image version v2.74.1.
- Windows Docker VHDX ~20.45 GiB; giữ nguyên, chưa chuyển/mount hoặc xoá dữ liệu.
- Docker Engine/Compose đã cài; CVAT source Ubuntu được dùng lại với override giảm worker còn 1 process và cổng loopback.

`Implemented` ở đây chỉ là code/test đã có; theo CONTRIBUTING chỉ gọi Done hoàn toàn khi PR được merge và nghiệm thu tương ứng.

## Checkpoint theo yêu cầu dừng

11/10/2026 khoảng 17:18 (Asia/Ho_Chi_Minh): người dùng yêu cầu dừng sau việc gần nhất do gần hết usage. Đã chốt kiểm tra CVAT UI thật và kiểm tra cuối; không bắt đầu pilot, video hay tích hợp upstream mới. Không dùng hết ngân sách 5 giờ.

- Ổ Ubuntu còn ~37 GiB sau cài/tải CVAT; máy này RAM ~11 GiB chạy được CVAT local.
- Mapping thật: data/samples/review/cvat_map.parquet. Task #1: 3 ảnh tổng hợp/3 box, không BDD thật.
- Chromium thật sửa/lưu occluded qua CVAT UI, rồi gửi verdict: 1 ảnh/1 lượt, session automated-cvat-fixture. Không tính thời gian tự động vào pilot.
- Bằng chứng local, không commit: data/cvat-runtime/integration-evidence.json, cvat-saved.png, extension-saved.png.
- Full pytest: 46 passed, 2 skipped (BDD thật và browser opt-in); Ruff sạch. Test MV3 opt-in riêng trước đó: 1 passed.
- Git identity local: tuanh404 / nguyentuanh88216@gmail.com. Browser đăng nhập không cung cấp credential cho Git CLI; dry-run HTTPS push thiếu Username. Chưa push/PR/merge.

Tiếp tục theo thứ tự:
1. Đăng nhập Git CLI trên Ubuntu, push nhánh và mở PR vào develop bằng docs/tuanh-pr.md; không tự merge.
2. Nhận ảnh/nhãn/preds/queue/evidence đúng contracts từ Sơn/Cường; cấu hình M13_*; nhập task CVAT mới, sync riêng từng máy.
3. Nghiệm thu sửa/lưu nhãn + 3 verdict + restart + stats trên batch thật.
4. Khi có guideline/key: gọi Gemini thật một lần/tài liệu, người duyệt đọc PDF/spec; ghép load_approved với rule engine của Long.
5. Khi có backend ML của Cường: tích hợp callable theo docs/demo, đo recall@20% trên val thật rồi mới nghiệm thu retrain/rollback.
6. Hỗ trợ 3 máy còn lại, chạy pilot người thật có đối trọng thứ tự, quay video <=3 phút.

Checkpoint đã lưu thành 3 commit local: API/CVAT; guideline; extension và bàn giao. Working tree phần code đã chốt; chỉ HTML cá nhân không được theo dõi. Nhánh chưa push, PR chưa mở/merge. API local :8000 và CVAT :8080 được để chạy để Tú Anh xem demo; không còn thao tác huấn luyện/download được bắt đầu mới.

## Đối chiếu 18 việc và Mốc A–E · phiên tiếp tục 11/10/2026

Bản kế hoạch mới giống bản ban đầu. Có **18 nhóm việc** trong mục E và **5 mốc A–E** trong mục G, không phải 18 giai đoạn tuần tự.

Mốc A đã kiểm tra đủ trên dữ liệu mẫu bằng HTTP thật và restart tiến trình thật: health/queue/phân trang, metadata/bytes ảnh, cả 3 verdict, retry/conflict/validation, lịch sử review lại, SQLite append-only. Sau restart: 4 lượt/3 ảnh, stats không đổi, remaining=0. DB kiểm tra riêng `data/milestone-a/api-smoke.db`, bằng chứng `data/milestone-a/verification.json`; không thay DB review của người dùng. 16 test API đạt. Thời gian fixture tự động không dùng cho pilot.

Cách tính phần trăm: số nhóm việc đã triển khai và kiểm tra được trong phạm vi độc lập / 18, không cộng điểm cho các phần mới có adapter. Sau khi chốt #11: 12/18 = 66.7%: #1, #2, #3, #4, #5, #6, #7, #9, #10, #11, #12, #18. Đây là tiến độ kỹ thuật local, không thay định nghĩa Done cần PR merge của CONTRIBUTING và không chứng minh chất lượng QC trên BDD thật.

| Nhóm | Trạng thái hiện tại |
|---|---|
| 1 | Đạt: Python 3.11 và fixtures đúng contracts |
| 2 | Đạt local: CVAT thật, account, task fixture và hướng dẫn |
| 3 | Đạt: queue, batch/phân trang/thiếu dữ liệu |
| 4 | Đạt: metadata và nội dung ảnh |
| 5 | Đạt: cả 3 verdict, SQLite/history/retry/restart |
| 6 | Đạt: mapping REST thực tế + tests |
| 7 | Đạt phần khảo sát/bàn giao: ghi rõ V1 chưa được cung cấp |
| 8 | Một phần: extract/schema/quote/cache; chờ Gemini thật và người duyệt |
| 9 | Đạt theo nhánh phát triển cho phép trong kế hoạch: 3 DOCX fixture ra draft chưa duyệt |
| 10 | Đạt: MV3 queue/evidence và trạng thái lỗi |
| 11 | Đạt: sửa regression đồng hồ frame mặc định, test Chrome và CVAT thật |
| 12 | Đạt: stats/audit phía server, tests fixture |
| 13 | Adapter/gate/rollback có; backend ML thật chưa có |
| 14 | Đã kiểm tra 1/4 máy, có package/hướng dẫn |
| 15 | Có export/quy trình; chưa pilot người thật |
| 16 | Có kịch bản; chưa video <=3 phút |
| 17 | Test/commit local đạt; chưa push/PR/merge |
| 18 | Đạt: checklist, bằng chứng, báo cáo soạn sẵn |

Theo mốc G: A đã đạt; B đã đạt trong phạm vi fixture, đồng hồ đã kiểm tra CVAT thật; C chưa đạt (queue/evidence pipeline thật); D chưa đạt (Gemini/người duyệt/rule engine thật, stats đã có); E chưa đạt (ML/các máy/pilot/video).

Việc di chuyển nhãn không tự làm điểm đổi vì API phục vụ queue snapshot. Tính lại lỗi từ nhãn CVAT đã lưu cần nối pipeline, thuộc phần ghép sau A/B. Không báo đã hoàn thành bước này. COCO8 đã tải thử trong lúc phạm vi chưa được xác nhận, chưa được đưa vào pipeline hay nghiệm thu; không thay BDD100K/upstream của nhóm.

Chốt phiên tiếp tục: Mốc A và B đạt yêu cầu chạy trên dữ liệu mẫu; không đánh đồng với nghiệm thu MVP BDD thật. Sửa đồng hồ nhận frame mặc định 0 khi CVAT xoá query frame=0, vẫn dừng khi frame sai/URL lỗi/mất focus. Test regression thất bại trước sửa và đạt sau sửa. Kiểm tra CVAT v2.74.1 thật ở frame 0: tăng thời gian, pause và resume đúng; không sửa annotations hoặc gửi verdict. Bằng chứng: `data/milestone-b/clock-verification.json`. Full pytest 46 passed/2 skipped, browser opt-in 1 passed, Ruff sạch. Extension ZIP đã đóng gói lại; người dùng cần Reload extension để nhận bản sửa. Chưa push/PR/merge.
