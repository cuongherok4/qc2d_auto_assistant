---
name: qc2d-project
description: Bản đồ tổng của dự án M13 Reviewer Prioritization (hỗ trợ QC kiểm duyệt nhãn detection 2D trên BDD100K) — luồng 7 bước, 3 quy ước dữ liệu để ghép code, ai sửa thư mục nào, quy tắc git/test. Dùng skill này TRƯỚC khi viết hoặc sửa bất kỳ code nào trong repo M13 / qc-2d, khi tạo module mới, khi không chắc file nào đặt ở đâu, khi ghép code của các thành viên, hoặc khi người dùng nhắc tới hàng đợi review, ranked_queue, SignalResult, yolo_preds, mốc (milestone) hay chia việc — kể cả khi họ không nói rõ "dự án M13".
---

# M13 · Trợ lý ưu tiên review nhãn 2D

Mục tiêu sản phẩm: thay vì QC review đều 100% ảnh, tool xếp hạng ảnh theo **nguy cơ nhãn sai** và kèm **lý do tiếng Việt có con số** để reviewer biết nhìn vào đâu. Chỉ số chính: recall lỗi trong top 20% và thời gian review tiết kiệm được.

Bối cảnh đầy đủ (quyết định, mâu thuẫn chưa chốt) nằm ở `docs/tom-tat.md`. Đọc mục 4, 5 và 9 của file đó khi việc đang làm chạm tới một điểm chưa chốt (detector, công cụ review, LLM/VLM, số ảnh kiểm tay). Đừng tự chốt hộ nhóm: làm theo kế hoạch gốc, để lựa chọn thay thế sau một tham số config, và nói rõ với người dùng.

## Luồng 7 bước và skill tương ứng

| Bước | Nội dung | Skill chi tiết |
|---|---|---|
| 1 | Nạp BDD100K val (10k ảnh, detection 2D) | `bdd100k-data` |
| 2 | Tiêm lỗi có đáp án (15% ảnh, 1–3 lỗi/ảnh, 5 loại) | `error-injection` |
| 3a | Tín hiệu hình học / ngữ cảnh | `qc-signals` |
| 3b | Bất đồng với detector độc lập | `qc-signals` |
| 0 | LLM đọc guideline batch → spec YAML, người duyệt (chốt 11/10) | `guideline-rules` |
| 3c | Luật theo guideline từng batch (rule engine đọc spec đã duyệt) | `guideline-rules` |
| 4 | Chấm điểm: rule → rule + detector → GBM | `risk-scoring` |
| 5–6 | Hàng đợi → API → giao diện review → verdict | `review-queue` |
| 7 | recall@20%, time saved, gain curve | `qc-eval` |

## Ba quy ước để ghép code (không đổi khi chưa báo cả nhóm)

1. **Tín hiệu** trả về `SignalResult` trong `src/features/base.py`:
   `name: str`, `value: float` trong [0, 1], `reason: str` tiếng Việt có con số, có thể kèm `evidence` (box nào, model nói gì). Lý do không có con số ("box lạ") là vô dụng với reviewer — luôn viết dạng "Box car cao 9px, nhỏ hơn 99% car khác".
2. **`data/yolo_preds.parquet`** (tên giữ nguyên kể cả khi đổi sang RT-DETR): cột `image_id, x1, y1, x2, y2, category, conf`; `category` là **tên class BDD** đã map, toạ độ pixel ảnh gốc 1280×720.
3. **`reports/ranked_queue_*.csv`**: cột `image_id, risk_score, rank, top_reasons, model_version`; `risk_score` 0–100, `rank` bắt đầu từ 1, `top_reasons` là tối đa 3 lý do nối bằng ` | `.

Kiểm nhanh file có đúng quy ước không:

```bash
python .claude/skills/qc2d-project/scripts/check_contracts.py --preds data/yolo_preds.parquet --queue reports/ranked_queue_rule.csv
```

Khi chưa có dữ liệu thật, tạo file mẫu đúng schema để người khác code trước (`--make-samples <thư mục>`).

## Cấu trúc thư mục và người phụ trách (đã chốt, chi tiết ở `CONTRIBUTING.md`)

```
configs/              paths, weights, injection, learning, class_map, guidelines/
src/data/             loader, tiêm lỗi
src/features/         base.py, geometry.py, model_disagreement.py, guideline_rules.py
src/scoring/          rule, gbm, retrain
src/eval/             metrics, gain curve, results.jsonl
src/api/              FastAPI
extension/            Chrome extension MV3 (hoặc FiftyOne nếu nhóm chốt)
src/cli.py            điểm vào duy nhất
tests/
```

Khi sửa code ngoài thư mục của người đang làm, nhắc họ điều đó — mục đích là tránh conflict khi ghép.

## Nguyên tắc chung khi code

- **Tham số ở `configs/*.yaml`, không hard-code** (seed, trọng số, ngưỡng). Lý do: mọi thí nghiệm phải chạy lại được và so được trong `reports/results.jsonl`.
- **Seed 42**, chia 6k/2k/2k **theo ảnh**. Không bao giờ để cùng một ảnh nằm ở 2 split.
- **Python 3.11** (`uv venv --python 3.11`); máy dev có Python 3.14 hệ thống, đừng cài vào đó.
- **Không đưa dữ liệu/ảnh/model vào git** (`data/`, `models/`, `*.parquet`, `*.pt` nằm trong `.gitignore`); chia qua Drive.
- Lỗi tiêm chỉ là thước đo lúc phát triển. Thước đo cuối là tập kiểm tay lỗi thật — đừng tối ưu quá mức theo lỗi tiêm.
- Mọi CLI mới đi qua `src/cli.py` (vd. `python -m src.cli inject`, `score`, `eval`).

## Trước khi báo xong việc

```bash
pytest -q && ruff check .
```

Nhánh `<loại>/<tên>-<việc>` (vd. `feat/son-model-missing-label`) tạo từ `develop`, PR vào `develop`, không bao giờ push thẳng vào `develop`/`main`. Chỉ Cường merge vào `develop`, và đưa `develop` vào `main` khi dự án hoàn thành. PR nhỏ, merge trong ngày. Commit message tiếng Anh hoặc tiếng Việt đều được, nhưng mô tả **cái gì đổi và vì sao**.

Nếu người dùng cần báo cáo tiến độ, dùng mẫu 22:30:

```
Báo cáo [tên] · [ngày]
Done:      việc đã xong (link PR)
Doing:     đang làm, xong khoảng bao nhiêu %
Blocked:   đang chờ ai / chờ gì
Link:      PR, file, ảnh kết quả
Questions: câu hỏi cho nhóm
```
