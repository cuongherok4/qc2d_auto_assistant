# Quy trình làm việc của team M13

Đọc file này trước khi viết dòng code đầu tiên. Mục tiêu: 4 người làm song song, không ai chờ ai, ghép code không conflict.

## 1. Luồng hệ thống và ai làm gì

```
 [1] Dữ liệu ──▶ [2] Tiêm lỗi ──▶ [3] Tín hiệu ──▶ [4] Chấm điểm ──▶ [5] Hàng đợi ──▶ [6] Reviewer ──▶ [7] Đánh giá
  bdd100k.py      inject.py        3a geometric +    rule.py            api/main.py      extension/       evaluate.py
                                      simple_signals gbm.py             cvat_sync.py     (CVAT local)     metrics.py
                                   3b detector +
                                      model_disagreement
                                   3c guideline_rules ◀── [0] guideline/extract.py
```

| Người | Việc | Chỉ sửa trong |
|---|---|---|
| **Cường** (lead) | Tiêm lỗi; 3 tín hiệu hình học khó (`size_outlier`, `dup_same_class`, `overlap_cross_class`); chấm điểm + file evidence; GBM, học lại; đánh giá; CLI, config; review + merge PR | `src/data/inject.py`, `src/features/geometric.py`, `src/scoring/`, `src/eval/`, `src/cli.py`, `configs/` (trừ `configs/guidelines/`) |
| **Sơn** | Tải BDD100K, chia qua Drive; chạy detector; 4 tín hiệu bất đồng; công cụ vẽ box cho kiểm tay; VLM (Mốc 4) | `src/features/detector.py`, `src/features/model_disagreement.py`, `src/features/vlm_check.py`, `src/viz/` |
| **Tú Anh** | CVAT local + `cvat-sync`; API (`/verdict`, `/image`, `/stats`), lưu verdict SQLite; Chrome extension; chạy pilot | `src/api/`, `extension/` |
| **Long** | 4 tín hiệu hình học dễ (`crowded`, `many_tiny`, `rare_class`, `edge_no_trunc`); LLM đọc guideline; rule engine; kiểm tay (kappa); báo cáo | `src/features/simple_signals.py`, `src/guideline/`, `src/features/guideline_rules.py`, `configs/guidelines/` |

CVAT chạy local trên từng máy, nên id task/job/frame khác nhau giữa các máy. Mỗi máy tự sinh bảng ánh xạ bằng `python -m src.cli cvat-sync` (lưu trong `data/`, không commit). Chỉ cần nạp vào CVAT các ảnh có trong hàng đợi, không cần đủ 10k ảnh.

Phần dùng chung (`src/contracts.py`, `src/features/base.py`, `src/data/bdd100k.py`, `src/config.py`) đã xong. Muốn sửa phải báo cả nhóm trước.

Việc của mỗi người đã có sẵn chỗ trong code: tìm `TODO(<tên mình>)`.

```bash
grep -rn "TODO(Sơn)" src/ extension/
```

## 2. Thứ tự làm

Việc gỡ chặn cho người khác làm trước; việc chạy lâu bắt đầu sớm và chạy nền.

**Sáng 12/10, làm đầu tiên:**

1. **Sơn:** tải BDD100K, chia qua Drive. Có dữ liệu thì cho detector chạy nền trên 10k ảnh ngay.
2. **Mọi người:** chưa có dữ liệu thật thì chạy `python -m src.cli samples` để có file mẫu đúng quy ước mà code trước.

| Mốc | Cường | Sơn | Tú Anh | Long |
|---|---|---|---|---|
| **1** (12–13/10) | Tiêm lỗi → 3 tín hiệu khó → đánh giá + gain curve | `detector.py` ra `yolo_preds.parquet` | Dựng CVAT local → `/verdict` + SQLite trên file mẫu → `cvat-sync` | 4 tín hiệu dễ → spec `bdd-default` + `load_spec` |
| **2** (14–15/10) | Hàng đợi rule + detector → file evidence | 4 tín hiệu bất đồng | Side panel hiển thị hàng đợi thật, mở đúng frame | Rule R1–R3 → LLM đọc guideline → R4 (sau khi Sơn xong khớp box) → kiểm tay nửa ngẫu nhiên |
| **3** (16–18/10) | GBM → mô phỏng học lại → bảng 5 phương pháp | Công cụ vẽ box cho kiểm tay → chuẩn bị VLM | `/stats`, ảnh audit, hoàn thiện extension | Kiểm tay nửa top hàng đợi, đo kappa |
| **4** (19–21/10) | Hỗ trợ, review | VLM xem lại top 30% (cắt nếu trễ) | Sửa lỗi giao diện | LLM viết báo cáo batch |
| **5** (22–23/10) | Pilot | Pilot | Chạy hệ thống cho pilot | Đo thời gian pilot |
| **6** (24–25/10) | README, video demo | Hỗ trợ | Hỗ trợ | Báo cáo cuối |

**Phụ thuộc cần theo dõi:**

- Tối 12/10 chưa có `yolo_preds.parquet` thì Mốc 2 trễ: Sơn báo tiến độ chạy detector ngay trong báo cáo 22:30.
- Rule R4 của Long cần phần khớp box của Sơn; kiểm tay nửa top cần hàng đợi của Cường.
- Cường review PR 2 lần mỗi ngày, lúc 12:00 và 21:00, để không ai chờ merge quá nửa ngày.

## 3. Ba quy ước ghép code

Đây là "hợp đồng" giữa các module. Mỗi người code theo đúng quy ước thì ghép vào là chạy, không cần chờ người khác xong.

1. **Tín hiệu** trả về `{image_id: SignalResult}` cho mọi ảnh (`src/features/base.py`).
   `value` trong [0, 1]; `reason` tiếng Việt, phải có con số: "Box car #12 cao 9px, nhỏ hơn 99% car khác". Mẫu có sẵn: `hard_condition` trong `src/features/geometric.py`.
2. **`data/yolo_preds.parquet`**: `image_id, x1, y1, x2, y2, category, conf`; category là tên class BDD, toạ độ pixel ảnh 1280×720.
3. **`reports/ranked_queue_<version>.csv`**: `image_id, risk_score, rank, top_reasons, model_version`; điểm 0–100, rank từ 1, tối đa 3 lý do nối bằng ` | `.

Kiểm file có đúng quy ước không:

```bash
python -m src.cli check --preds data/yolo_preds.parquet --queue reports/ranked_queue_rule-v0.csv
```

## 4. Cài đặt

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"          # thêm ,gbm  ,detector  ,guideline  khi cần
pytest -q && ruff check .
```

Dữ liệu BDD100K (ảnh val + `det_val.json`) đặt theo đường dẫn trong `configs/paths.yaml`, chia qua Drive, **không đưa vào git**.

## 5. Quy tắc nhánh git

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

## 6. Quy trình mỗi ngày

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

## 7. Nguyên tắc

- **Tham số để trong `configs/*.yaml`**, không hard-code (seed, trọng số, ngưỡng, đường dẫn).
- **Seed 42**, chia 6k/2k/2k theo ảnh. Một ảnh không bao giờ nằm ở 2 split.
- Mọi lệnh chạy đi qua `python -m src.cli`.
- Mỗi lần đánh giá ghi một dòng vào `reports/results.jsonl`. Không sửa dòng cũ.
- Lỗi tiêm chỉ là thước đo lúc phát triển. Thước đo cuối là tập kiểm tay lỗi thật.
- Không commit dữ liệu, ảnh, model, secrets (`.env`).

## 8. Định nghĩa "xong"

Một việc chỉ tính là xong khi đủ 3 điều sau:

- [ ] Code chạy được qua CLI hoặc API, đúng quy ước ở mục 3.
- [ ] Có test, `pytest -q && ruff check .` xanh.
- [ ] PR đã merge vào `develop`.
