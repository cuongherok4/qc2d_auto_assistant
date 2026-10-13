# M13 Reviewer Prioritization

Trợ lý ưu tiên review nhãn detection 2D trên BDD100K. Thay vì QC review đều 100% ảnh, hệ thống chấm điểm rủi ro sai nhãn cho từng ảnh và xếp hàng đợi review, mỗi ảnh kèm 3 lý do tiếng Việt.

- **Dữ liệu:** BDD100K tập val, 10k ảnh, nhãn detection 2D
- **Chỉ số chính:** recall lỗi trong top 20% ảnh; thời gian review tiết kiệm
- **Nhóm:** Hoàng Mạnh Cường (lead), Long (BA), Tú Anh (BE), Sơn (BE)

**Tiến độ (cập nhật 13/10 tối):** [ai đã xong gì, ai làm tiếp, kết quả hiện có](docs/tien-do.md).

**Dành cho cả người không chuyên kỹ thuật:** [Hướng dẫn 10 việc cần làm: ai làm, làm thế nào, giao gì và khi nào tính là xong](docs/huong-dan-cong-viec-de-hieu.md).

**Cập nhật 13/10:** [Phân tích đề tài, hiện trạng các nhánh và phân công tiếp theo](docs/phan-tich-va-phan-cong-13-10.md) — gồm 4 sơ đồ SVG để chia sẻ với nhóm; ghi nhận phần API, CVAT, extension và guideline tools Tú Anh đã viết.

**Xem hệ thống qua một ví dụ cụ thể:** [Ảnh + guideline → LLM trích luật → detector/rule kiểm nhãn → hàng đợi review](docs/vi-du-xuyen-suot.md), có hai hình minh họa đầu vào và kết quả từng bước.

## Bắt đầu

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q && ruff check .
```

Thành viên mới: đọc [CONTRIBUTING.md](CONTRIBUTING.md) để biết luồng, phân công, quy ước ghép code và quy trình hằng ngày.

## Chạy pipeline

```bash
python -m src.cli load                                    # 1. đọc nhãn BDD100K
python -m src.cli inject                                  # 2. tiêm lỗi có đáp án
python -m src.cli rank --version rule-v0                  # 3–4. queue + evidence + manifest (thêm --preds/--spec khi có)
python -m src.cli evaluate --queue reports/ranked_queue_rule-v0.csv   # 7. so file order/random, gain curve
uvicorn src.api.main:app --reload                         # 5. API cho giao diện review
```

## Cấu trúc

```
configs/          tham số: paths, injection, weights, learning, class_map, batches, guidelines/
src/data/         loader BDD100K, tiêm lỗi
src/features/     tín hiệu rủi ro (hình học, detector, guideline) + SignalResult
src/guideline/    LLM đọc guideline -> spec YAML
src/scoring/      chấm điểm rule, GBM, học lại
src/eval/         metric, ghi reports/results.jsonl
src/api/          FastAPI hàng đợi + verdict
src/cli.py        điểm vào duy nhất
extension/        Chrome extension (side panel trong CVAT)
tests/            test + fixtures nhỏ, chạy không cần dữ liệu thật
docs/             đề xuất, tóm tắt dự án
reports/          báo cáo tuần, kết quả đánh giá
```

Dữ liệu, ảnh và model không đưa vào git; chia sẻ qua Drive.
