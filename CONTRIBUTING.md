# Quy trình làm việc của team M13

Đọc file này trước khi viết dòng code đầu tiên. Mục tiêu: 4 người làm song song, không ai chờ ai, ghép code không conflict.

## 1. Luồng hệ thống và ai làm gì

```
 [1] Dữ liệu ──▶ [2] Tiêm lỗi ──▶ [3] Tín hiệu ──▶ [4] Chấm điểm ──▶ [5] Hàng đợi ──▶ [6] Reviewer ──▶ [7] Đánh giá
  bdd100k.py      inject.py        3a geometric      rule.py            api/main.py      extension/       evaluate.py
                                   3b detector +     gbm.py                                               metrics.py
                                      model_disagreement
                                   3c guideline_rules ◀── [0] guideline/extract.py
```

| Người | Phụ trách | Chỉ sửa trong |
|---|---|---|
| **Cường** (lead) | Tiêm lỗi, tín hiệu hình học, chấm điểm, GBM, đánh giá, CLI, config; review + merge | `src/data/inject.py`, `src/features/geometric.py`, `src/scoring/`, `src/eval/`, `src/cli.py`, `configs/` |
| **Sơn** | Tải BDD100K, chạy detector, tín hiệu bất đồng | `src/features/detector.py`, `src/features/model_disagreement.py` |
| **Tú Anh** | API, lưu verdict, Chrome extension | `src/api/`, `extension/` |
| **Long** | Đọc guideline, spec, rule engine, kiểm tay, pilot | `src/guideline/`, `src/features/guideline_rules.py`, `configs/guidelines/` |

Phần dùng chung (`src/contracts.py`, `src/features/base.py`, `src/data/bdd100k.py`, `src/config.py`) đã xong. Muốn sửa phải báo cả nhóm trước.

Việc của mỗi người đã có sẵn chỗ trong code: tìm `TODO(<tên mình>)`.

```bash
grep -rn "TODO(Sơn)" src/ extension/
```

## 2. Ba quy ước ghép code

Đây là "hợp đồng" giữa các module. Mỗi người code theo đúng quy ước thì ghép vào là chạy, không cần chờ người khác xong.

1. **Tín hiệu** trả về `{image_id: SignalResult}` cho mọi ảnh (`src/features/base.py`).
   `value` trong [0, 1]; `reason` tiếng Việt, phải có con số: "Box car #12 cao 9px, nhỏ hơn 99% car khác". Mẫu có sẵn: `hard_condition` trong `src/features/geometric.py`.
2. **`data/yolo_preds.parquet`**: `image_id, x1, y1, x2, y2, category, conf`; category là tên class BDD, toạ độ pixel ảnh 1280×720.
3. **`reports/ranked_queue_<version>.csv`**: `image_id, risk_score, rank, top_reasons, model_version`; điểm 0–100, rank từ 1, tối đa 3 lý do nối bằng ` | `.

Kiểm file có đúng quy ước không:

```bash
python -m src.cli check --preds data/yolo_preds.parquet --queue reports/ranked_queue_rule-v0.csv
```

## 3. Cài đặt

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"          # thêm ,gbm  ,detector  ,guideline  khi cần
pytest -q && ruff check .
```

Dữ liệu BDD100K (ảnh val + `det_val.json`) đặt theo đường dẫn trong `configs/paths.yaml`, chia qua Drive, **không đưa vào git**.

## 4. Quy tắc nhánh git

```
 feat/son-model-missing-label ─┐
 feat/tuanh-verdict-api ───────┼──PR──▶ develop ──(Cường, khi dự án hoàn thành)──▶ main
 fix/cuong-rank-tie-break ─────┘
```

| Nhánh | Dùng để | Ai được đưa code vào |
|---|---|---|
| `main` | Bản hoàn chỉnh, chỉ cập nhật ở bước cuối dự án | Chỉ Cường, merge từ `develop` |
| `develop` | Nhánh tổng hợp code của cả nhóm | Chỉ Cường, merge PR từ nhánh việc |
| `<loại>/<tên>-<việc>` | Mỗi việc một nhánh riêng | Người làm việc đó |

**Không ai push thẳng vào `develop` hoặc `main`.** Mọi thay đổi đi qua nhánh việc rồi mở PR vào `develop`.

**Tên nhánh phải ghi rõ ai làm và làm gì:** `<loại>/<tên>-<việc>`, viết thường, không dấu, nối bằng `-`.

| Loại | Khi nào | Ví dụ |
|---|---|---|
| `feat` | Thêm chức năng | `feat/son-model-missing-label` |
| `fix` | Sửa lỗi | `fix/cuong-rank-tie-break` |
| `test` | Chỉ thêm/sửa test | `test/long-guideline-near-threshold` |
| `docs` | Tài liệu, báo cáo | `docs/long-bao-cao-tuan-5` |
| `chore` | Config, CI, dọn dẹp | `chore/cuong-update-weights` |

Tên dở: `son`, `test1`, `update`, `fix-bug`: đọc tên không biết làm gì.

**Commit message** ghi rõ đổi gì: `feat(features): thêm tín hiệu model_missing_label`, `fix(scoring): hoà điểm xếp theo image_id`.

## 5. Quy trình mỗi ngày

1. Sáng: lấy code mới nhất từ `develop`, rồi tạo nhánh cho việc hôm nay:

   ```bash
   git checkout develop && git pull --rebase
   git checkout -b feat/son-model-missing-label
   ```

2. Code trong thư mục của mình. Mỗi hàm mới có ít nhất 1 test trong `tests/`, chạy trên dữ liệu nhỏ ở `tests/fixtures/`.
3. Trước khi push: `pytest -q && ruff check .` phải xanh.
4. Push nhánh lên GitHub và mở PR **vào `develop`** (không phải `main`), điền đủ template PR:

   ```bash
   git push -u origin feat/son-model-missing-label
   ```

5. Cường review và merge vào `develop`. PR nhỏ, merge trong ngày; nhánh đã merge thì xoá.
6. **22:30** gửi báo cáo vào nhóm:

```
Báo cáo [tên] · [ngày]
Done:      việc đã xong (link PR)
Doing:     đang làm, xong khoảng bao nhiêu %
Blocked:   đang chờ ai / chờ gì
Link:      PR, file, ảnh kết quả
Questions: câu hỏi cho nhóm
```

## 6. Nguyên tắc

- **Tham số để trong `configs/*.yaml`**, không hard-code (seed, trọng số, ngưỡng, đường dẫn).
- **Seed 42**, chia 6k/2k/2k theo ảnh. Một ảnh không bao giờ nằm ở 2 split.
- Mọi lệnh chạy đi qua `python -m src.cli`.
- Mỗi lần đánh giá ghi một dòng vào `reports/results.jsonl`. Không sửa dòng cũ.
- Lỗi tiêm chỉ là thước đo lúc phát triển. Thước đo cuối là tập kiểm tay lỗi thật.
- Không commit dữ liệu, ảnh, model, secrets (`.env`).

## 7. Định nghĩa "xong"

Một việc chỉ tính là xong khi đủ 3 điều sau:

- [ ] Code chạy được qua CLI hoặc API, đúng quy ước ở mục 2.
- [ ] Có test, `pytest -q && ruff check .` xanh.
- [ ] PR đã merge vào `develop`.
