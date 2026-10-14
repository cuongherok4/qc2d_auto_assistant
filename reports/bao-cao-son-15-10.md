# Báo cáo Sơn · 15/10/2026

**Nhánh:** `feat/son-fix-disagreement` → PR #7 vào `develop`

```
Done:      Sửa 2 lỗi detector (rule-v1.3: recall@20% có trọng số 0.310 → 0.374); kiểm tay xong 150 ảnh (phiếu trên Drive)
Doing:     Chờ Long xong việc 1–6 để làm R4 cùng
Blocked:   Chờ Cường review/merge PR #7; chờ phiếu của Long để tính kappa
Link:      PR #7 feat/son-fix-disagreement; Drive: phieu-son.csv
Questions: Xem mục 3
```

## 1. Sửa 2 lỗi detector (`src/features/model_disagreement.py`)

Dữ liệu chung 14/10 (`det_val.json` sha256 `f7cde1a3…`), RT-DETR. Kiểm khớp trước khi sửa: `rule-v1.2-son` ra 0.310, đúng bảng tiến độ.

| | rule-v1.2 | rule-v1.3 |
|---|---|---|
| recall@20% có trọng số | 0.310 | **0.374** |
| recall@20% theo ảnh | 0.277 | 0.333 |
| recall lỗi dịch box / co-giãn | 0.252 / 0.291 | 0.360 / 0.409 |
| time saved (proxy số ảnh) | 0.211 | 0.237 |

- `loose_min_iou` 0.3: `model_loose_box` bắt đúng object bị dịch 15.3% → 31.6%.
- Lọc capo xe mình (y2 ≥ 715, rộng ≥ 640): báo nhầm "thiếu box" do capo 2807/6142 box (46%) → 0.
- Đổi lại: `model_loose_box` kích hoạt ở 66% ảnh, tín hiệu nhiễu. Ngưỡng theo hướng dẫn, không chỉnh trên test.
- Số trong `reports/results.jsonl` (2 dòng `rule-v1.2-son`, `rule-v1.3`).

## 2. Kiểm tay 150 ảnh (manual-check-v1)

Phiếu `phieu-son.csv` nộp qua Drive (không commit theo quy định nhóm.

| ket_luan | Số ảnh |
|---|---|
| khong_loi | 119 |
| loi | 24 (sai_class 16, box_thua 7, thieu_box 2) |
| khong_chac | 7 |

Lỗi hay gặp: xe buýt trường học/đưa đón ghi `car`/`truck`, xe tải giao hàng ghi `bus`, người đi bộ ghi `car`, biển hiệu cửa hàng/bãi đỗ ghi `traffic sign`, box 10–12px không có vật.

## 3. Câu hỏi cho nhóm

1. Long có chấm lại `thieu_thuoc_tinh` (O/T) không? Phiếu này gần như bỏ qua hạng mục đó.
2. Van, xe cứu thương, rơ-moóc theo quy ước BDD là `car` hay `truck`? Cần thống nhất trước khi đối chiếu phiếu.
3. `.venv/bin/pytest -q` (lệnh CI) lỗi collect `tests/test_gbm.py` (`No module named 'tests'`) có sẵn trên `develop`; `python -m pytest -q` chạy được.
