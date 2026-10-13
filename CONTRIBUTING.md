# Quy trình làm việc của team M13

> **Cập nhật 13/10/2026:** xem [phân tích và phân công mới](docs/phan-tich-va-phan-cong-13-10.md) trước khi nhận việc. Phần hiện trạng/lịch ở mục 1–2 bên dưới là kế hoạch ngày 12/10; Tú Anh đã có API, CVAT, extension, guideline tools và công cụ demo/pilot trên nhánh riêng; Long đã có 4 tín hiệu, load spec và R1. Không dùng TODO ở nhánh base để kết luận các phần này chưa được viết. Giữ các quy ước làm việc bên dưới; dùng bản cập nhật để xác định việc còn lại.

Đọc file này trước khi viết dòng code đầu tiên. Mục tiêu: 4 người làm song song, không ai chờ ai, ghép code không conflict.

## 1. Luồng hệ thống và ai làm gì

```
 guideline của job ─▶ LLM đọc ─▶ spec YAML (mỗi luật có câu trích + trang) ─▶ NGƯỜI DUYỆT
   src/guideline/extract.py                                                     │
                                                                                ▼
 [1] Dữ liệu ─▶ [2] Tiêm lỗi ─▶ [3] Tín hiệu, chạy 100% ảnh ───────────────────────────────┐
  bdd100k.py     inject.py       3a hình học: geometric.py + simple_signals.py              │
                                 3b detector so với nhãn: detector.py + model_disagreement  │
                                 3c luật theo spec: guideline_rules.py                       │
                                                                                            ▼
 [4] Chấm điểm (rule.py, gbm.py) ─▶ ranked_queue + evidence ─▶ 3d VLM xem lại top 30% (vlm_check.py)
                                                                                            │
 [7] Đánh giá ◀── verdict ◀── [6] Reviewer bấm trong CVAT ◀── [5] API + extension ◀──── hàng đợi cuối
  evaluate.py                      extension/                   api/
```

Rule và VLM chỉ kiểm được box **đã có**. Object bị bỏ sót chỉ detector bắt được, nên 3b chạy song song với 3c chứ không thay thế. Kết quả VLM là một tín hiệu cộng vào điểm, quyết định cuối cùng vẫn là reviewer.

**Bốn file ghép nối.** Chưa có file thật thì chạy `python -m src.cli samples` để có file mẫu đúng định dạng mà code trước:

| File | Ai làm ra | Ai dùng |
|---|---|---|
| `data/yolo_preds.parquet` | Sơn | Sơn (bất đồng), Long (R4), Tú Anh (vẽ box) |
| `reports/ranked_queue_*.csv` | Cường | Tú Anh (API), Cường (VLM, đánh giá), Long (kiểm tay) |
| file evidence | Cường | Tú Anh (side panel) |
| `data/cvat_map.parquet` | Tú Anh (mỗi máy tự sinh) | API, extension |

| Người | Việc | Chỉ sửa trong |
|---|---|---|
| **Cường** (lead) | Phần khó: tiêm lỗi; chấm điểm + file evidence; đánh giá; GBM; **VLM (Qwen2.5-VL chạy local trên GPU)**; CLI, config; review + merge PR; dẫn video | `src/data/inject.py`, `src/scoring/`, `src/eval/`, `src/features/vlm_check.py`, `src/cli.py`, `configs/` (trừ `configs/guidelines/`) |
| **Sơn** | Tải BDD100K, chia qua Drive; chạy detector; 4 tín hiệu bất đồng (lọc dự đoán theo spec); kiểm tay cùng Long | `src/features/detector.py`, `src/features/model_disagreement.py` |
| **Tú Anh** | CVAT local + `cvat-sync`; API, SQLite; Chrome extension; **3 tín hiệu hình học** (`size_outlier`, `dup_same_class`, `overlap_cross_class`, dùng hàm có sẵn trong `geometry.py`); **công cụ vẽ box cho kiểm tay**; pilot; dựng máy demo | `src/api/`, `extension/`, `src/features/geometric.py`, `src/viz/` |
| **Long** | 4 tín hiệu hình học dễ (`crowded`, `many_tiny`, `rare_class`, `edge_no_trunc`); **nhận lại phần LLM đọc guideline Tú Anh đã viết**; viết 2 guideline biến thể; rule engine; kiểm tay (kappa); báo cáo | `src/features/simple_signals.py`, `src/guideline/`, `src/features/guideline_rules.py`, `configs/guidelines/` |

CVAT chạy local trên từng máy, nên id task/job/frame khác nhau giữa các máy. Mỗi máy tự sinh bảng ánh xạ bằng `python -m src.cli cvat-sync` (lưu trong `data/`, không commit). Chỉ cần nạp vào CVAT các ảnh có trong hàng đợi, không cần đủ 10k ảnh.

Phần dùng chung (`src/contracts.py`, `src/features/base.py`, `src/data/bdd100k.py`, `src/config.py`) đã xong. Muốn sửa phải báo cả nhóm trước.

Việc của mỗi người đã có sẵn chỗ trong code: tìm `TODO(<tên mình>)`.

```bash
grep -rn "TODO(Sơn)" src/ extension/
```

## 2. Lịch 4 ngày (cập nhật 12/10)

3 ngày code (13–15/10), ngày 16/10 deploy và quay video. **20:00 ngày 15/10 đóng băng code**, sau giờ đó chỉ sửa lỗi chặn demo.

| Ngày | Cường | Sơn | Tú Anh | Long |
|---|---|---|---|---|
| **13/10**: có hàng đợi đầu tiên | `inject.py` → `rule.py` + evidence → `rank` ra `ranked_queue_rule-v0` trên dữ liệu thật → recall@20% so với random. Detector chậm thì cho chạy trên GPU của mình | Sáng cho detector chạy nền 10k ảnh → **`yolo_preds.parquet` lên Drive trước 18:00** → tín hiệu thiếu box, sai class | Sửa 4 lỗi nặng trong review → tách nhánh guideline ra → **PR API + extension trước 12:00** → **3 tín hiệu hình học, PR trước 18:00** (Cường cần để ra `rule-v0`) | 4 tín hiệu dễ (PR trước 12:00) → nhận code guideline của Tú Anh, đọc cùng Tú Anh 30 phút → viết 2 guideline biến thể (VD ngưỡng 30px + gộp truck/bus; bỏ traffic sign) |
| **14/10**: đủ tín hiệu | Ghép tín hiệu Sơn + Long → hàng đợi `rule-det-v1` → gain curve → `vlm_check.py`: Qwen2.5-VL chạy top 30% của `rule-v0` (chạy nền) → GBM một lần (train trên đáp án tiêm, val riêng) | 2 tín hiệu bất đồng còn lại + lọc dự đoán theo spec | `viz/draw.py` cho kiểm tay (sáng, Long cần) → side panel nạp hàng đợi thật, `cvat-sync` 300 ảnh top → lỗi nhóm B | LLM đọc 3 guideline → spec → duyệt → `guideline_rules` R1–R4 → kiểm tay 50 ảnh ngẫu nhiên |
| **15/10**: chốt số | Hàng đợi cuối (rule + detector + guideline + VLM) → bảng so sánh phương pháp → merge hết vào `develop` → `main` | Kiểm tay 50 ảnh top hàng đợi cùng Long (2 người → kappa) → chạy lại toàn pipeline trên máy GPU | Pilot nhỏ: 2 người, 30 ảnh theo hàng đợi + 30 ảnh theo thứ tự file, đo thời gian → lỗi nhóm C → script dựng demo 1 lệnh | Kiểm tay 50 ảnh top + kappa → viết báo cáo (số do Cường đưa) |
| **16/10**: deploy, video | Sáng: chạy thử kịch bản video. Chiều: quay video 3–5 phút (bài toán → guideline → spec → hàng đợi → review trong CVAT → số liệu), README | Hỗ trợ dựng máy demo, chuẩn bị số/ảnh cho video | Sáng: dựng máy demo từ `main` sạch theo README (CVAT + API + extension). Chiều: thao tác demo khi quay | Chốt báo cáo + slide |

**Đã cắt để vừa 3 ngày:** vòng học lại online (chỉ train GBM một lần, học lại ghi là hướng phát triển); kiểm tay còn 150 ảnh thay vì 500; VLM chỉ chạy top 30%. Trưa 15/10 nếu VLM không tăng recall thì bỏ khỏi hàng đợi cuối, chỉ giữ để demo.

**Phụ thuộc cần theo dõi:**

- Cường giữ đường găng (tiêm lỗi → hàng đợi → đánh giá). VLM và GBM là việc cắt đầu tiên nếu Cường trễ.
- 18:00 ngày 13/10 chưa có `yolo_preds.parquet` thì Sơn báo ngay, Cường cho chạy detector trên máy GPU của mình.
- Tối 13/10 Cường phải có `ranked_queue_rule-v0`: Tú Anh (side panel) và Long (kiểm tay top) cần nó sáng 14/10.
- Rule R4 của Long cần phần khớp box của Sơn.
- Cường review PR 2 lần mỗi ngày, lúc 12:00 và 21:00, để không ai chờ merge quá nửa ngày.
- Báo cáo 22:30 mỗi tối theo mẫu, ghi rõ đang chặn ai / bị ai chặn.

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
