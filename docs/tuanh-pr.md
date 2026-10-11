# PR đề xuất: feat(tuanh): luồng review 2D local và guideline draft

Nhánh nguồn `feat/tuanh-review-flow`, nhánh đích `develop`. Chưa push/mở PR vì Git CLI Ubuntu chưa có credential; chưa merge. Dùng nội dung sau theo template:

## Đổi gì

Thêm luồng queue/evidence → Chrome MV3 → đúng frame CVAT → verdict append-only SQLite → stats. Retry sau mất phản hồi không tạo verdict trùng; giữ lịch sử review lại và snapshot/model/rank tại thời điểm review. Có cvat-sync/import task mới, fixtures, package và pilot export.

Thêm Gemini guideline draft với DOCX→PDF, schema/citation/cache và bước duyệt người thật. Adapter retrain/model/rollback kiểm gate, trả 503 khi ML chưa có. Chưa hoàn thành BDD100K/Gemini/ML/pilot thật.

## Vì sao

Tú Anh có thể phát triển và thử reviewer trước khi Sơn/Cường/Long giao đầu vào. Nhãn Save trong CVAT được kiểm riêng với verdict. Config reviewer theo HTML được tách khỏi learning.yaml để không thay chính sách ML của nhóm.

## Kiểm tra

- [x] Nhánh đích dự kiến `develop`, không push main/develop trực tiếp.
- [x] `pytest -q`: 46 passed, 2 skipped; `ruff check .`: sạch.
- [x] Test Chromium MV3 opt-in: 1 passed; CVAT v2.74.1 thật nhập/sync 3 ảnh, sửa/lưu occluded qua UI và đối chiếu SQLite/stats, dữ liệu fixture.
- [x] Phạm vi API/guideline/extension/tests/docs; CLI/config/dependencies sửa tối thiểu để gọi module mới. Guideline thuộc scope Tú Anh theo yêu cầu mở rộng của người dùng.
- [x] Không đổi contracts hoặc detector/scoring/rule engine/huấn luyện ML của nhóm.
- [x] Không commit ảnh/dữ liệu/model/DB/mapping/secrets hoặc HTML cá nhân.

Hướng dẫn/bằng chứng và các phụ thuộc còn thiếu: docs/tuanh-demo.md, docs/tuanh-progress.md, docs/tuanh-v1-note.md. Theo CONTRIBUTING, chỉ gọi Done hoàn toàn sau khi PR merge và nghiệm thu phần tương ứng.
