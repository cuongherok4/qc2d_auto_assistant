---
name: qc-eval
description: Đánh giá hàng đợi ưu tiên review nhãn — recall lỗi trong top 20% (theo ảnh và theo lỗi có trọng số), precision, NDCG, time saved, gain curve, so với baseline random/thứ tự file, recall theo loại lỗi, kiểm ngẫu nhiên phần đuôi, Cohen's kappa của tập kiểm tay. Dùng khi code src/eval/, khi báo số liệu/viết báo cáo, vẽ gain curve, so sánh phương pháp, ghi reports/results.jsonl, hoặc khi người dùng hỏi "hệ thống tốt cỡ nào", "tiết kiệm bao nhiêu thời gian".
---

# Đánh giá hàng đợi review

Các hàm metric chuẩn đã viết sẵn và test ở `scripts/metrics.py` của skill này — chép sang `src/eval/metrics.py` rồi dùng, đừng viết lại công thức (dễ lệch định nghĩa giữa các thành viên).

## Định nghĩa (đã chốt 07/10, cập nhật theo Q5–Q6)

- **Đơn vị chính: lỗi có trọng số** (Q5): `missing 1.0, wrong_class 1.0, spurious 0.6, shift 0.3, resize 0.3`. Báo thêm recall theo **ảnh** (ảnh có ≥ 1 lỗi).
- **recall@k%**: phần (trọng số) lỗi nằm trong k% ảnh đầu hàng đợi. Báo k = 20% theo **số ảnh** và theo **thời gian review** (Q6) — ảnh rủi ro cao thường đông object nên review lâu; khi chưa đo thời gian thật, xấp xỉ `t = a + b × n_boxes` với a, b ghi trong config.
- **time saved** = `1 − n_queue / n_random`, trong đó n_x là số ảnh phải xem theo thứ tự x để đạt **80% recall**. `n_random` = trung bình trên **20 seed** xáo trộn.
- Baseline: random (20 seed, báo mean ± std) và **thứ tự file** (`image_order` trong file đáp án).
- Phụ: precision@20%, NDCG, recall theo từng loại lỗi, gain curve (trục x: % ảnh hoặc % thời gian đã xem; trục y: % lỗi có trọng số đã bắt; vẽ cả đường random và đường lý tưởng).

## Cách nói kết quả

Không viết "bắt 80% lỗi trong 20% ảnh = tiết kiệm 80% thời gian" — sai vì ảnh đầu hàng đợi review lâu hơn, và vì phần còn lại vẫn có lỗi. Viết dạng:

> Với ngân sách 2 giờ review (≈ 20% thời gian), tỉ lệ lỗi sót giảm từ 80% (xem ngẫu nhiên) xuống 35% (hàng đợi GBM).

Luôn kèm **split, seed, số ảnh, model_version**. Kết quả trên lỗi tiêm phải ghi rõ "lỗi giả lập" và nêu hạn chế rò rỉ (xem `error-injection`).

## Ghi kết quả

Mỗi lần chạy append một dòng JSON vào `reports/results.jsonl`:

```json
{"ts": "2026-10-12T21:05:00", "commit": "abc1234", "method": "rule_model", "model_version": "rule-v2",
 "split": "test", "seed": 42, "guideline": "bdd-default@1.0.0", "n_images": 2000,
 "recall20_img": 0.61, "recall20_weighted": 0.66, "recall20_time": 0.55,
 "time_saved": 0.43, "random_recall20_mean": 0.20, "per_type": {"missing": 0.7}}
```

Không sửa dòng cũ; muốn so thì đọc file và lọc. Commit lấy từ `git rev-parse --short HEAD` (ghi `"nogit"` nếu chưa có repo).

## Lỗi thật (thước đo cuối)

- **Tập kiểm tay**: một nửa từ top hàng đợi, một nửa ngẫu nhiên (để còn ước lượng tỉ lệ lỗi chung). Q10 muốn 500 ảnh × 2 người (≈ 25 giờ công) — vượt thời gian còn lại; khuyến nghị 150–200 ảnh, làm 100 ảnh ngẫu nhiên trước.
- 2 người kiểm độc lập, đo **Cohen's kappa** (`sklearn.metrics.cohen_kappa_score`) ở mức ảnh. Kappa < 0.6 → guideline kiểm tay chưa rõ, sửa trước khi tin số liệu.
- Nhãn gốc BDD100K vốn có lỗi: ước lượng tỉ lệ lỗi gốc trên nửa ngẫu nhiên, dùng để hiệu chỉnh precision (một số "báo nhầm" thật ra là lỗi gốc đúng).
- **Kiểm ngẫu nhiên 5% số ảnh dưới vạch cắt** (Q19) để ước lượng lỗi còn sót; mục tiêu ≤ 2% object (Q20). Báo kèm khoảng tin cậy (Wilson) vì mẫu nhỏ.
