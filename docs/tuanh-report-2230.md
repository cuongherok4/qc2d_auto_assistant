# Bản soạn để Tú Anh gửi nhóm lúc 22:30 · 11/10/2026

Done: Chưa có mục Done theo định nghĩa PR đã merge của CONTRIBUTING. Đã triển khai và kiểm tra local API/SQLite, cvat-sync, extension, stats/audit, guideline draft và adapter retrain/model.

Doing: CVAT thật trên một máy đã nhập/sync 3 ảnh mẫu, sửa/lưu nhãn qua UI, lưu verdict/stat. Full test 46 passed, 2 skipped; Ruff sạch; test Chrome MV3 riêng 1 passed. Chưa nghiệm thu QC bằng BDD thật.

Blocked: Chưa có đầu vào Sơn/Cường/Long theo thứ tự kế hoạch; ML/rule engine còn stub; Gemini chưa có key/tài liệu thật/người duyệt. Git CLI Ubuntu chưa có credential để push/PR. Chưa chạy 3 máy còn lại, pilot người thật hay quay video.

Link: Nhánh local feat/tuanh-review-flow; docs/tuanh-progress.md; docs/tuanh-demo.md; docs/tuanh-v1-note.md; docs/tuanh-pr.md. Ảnh/JSON bằng chứng nằm local data/cvat-runtime/, không commit.

Questions: Khi upstream sẵn sàng, thống nhất evidence JSONL và giao diện callable ML với adapter; người duyệt guideline nhận phần duyệt nguồn/spec. Không cần cung cấp dữ liệu sớm hơn kế hoạch để Tú Anh tiếp tục code.

Phiên dừng theo yêu cầu của Tú Anh vì gần hết usage, không tiếp tục việc mới. Báo cáo này chưa được agent gửi cho bất kỳ ai.

Cập nhật phiên tiếp tục: đã chốt Mốc A bằng HTTP thật và restart API thật (4 lượt/3 ảnh giữ nguyên); đã sửa lỗi đồng hồ frame mặc định và kiểm tra pause/resume với Chrome + CVAT thật. Mốc B đạt trên fixture, tiến độ kỹ thuật local 12/18 nhóm (66.7%). Mốc C/D/E còn các phụ thuộc như trên; chưa PR merge. Kiểm tra cuối 46 passed/2 skipped, browser opt-in 1 passed, Ruff sạch.
