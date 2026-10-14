# Định nghĩa mẫu audit phần cuối hàng đợi

Mục đích: reviewer chỉ xem top 20% hàng đợi, nên cần ước lượng **còn bao nhiêu lỗi bị bỏ sót** ở 80% không xem.
Cách làm: lấy ngẫu nhiên một ít ảnh ở phần không review, trộn vào lúc review, xem có lỗi thật hay không.

Thay cho cách đang chạy trong `src/api/service.py` (chèn 1 ảnh nửa dưới sau mỗi 10 ảnh nửa trên), vì cách đó lấy
mẫu từ nửa dưới chứ không phải từ đúng phần không review, và tỉ lệ phụ thuộc kích thước nửa trên.

## 1. Chọn mẫu

Với hàng đợi `N` ảnh, đã sắp theo `rank`:

| Đại lượng | Định nghĩa |
|---|---|
| Vùng review | `n_top = ceil(0.2 × N)` ảnh đầu (rank 1 … n_top) |
| Phần đuôi | các ảnh còn lại, `n_tail = N − n_top` |
| Số ảnh audit | `n_audit = ceil(0.05 × n_tail)` |
| Cách lấy | ngẫu nhiên đều, không lặp, trong phần đuôi: `random.Random(42).sample(tail_ids, n_audit)` với `tail_ids` theo thứ tự rank |

Tham số để trong config thay cho `audit_every`: `audit_top_frac: 0.2`, `audit_rate: 0.05`, `audit_seed: 42`.

## 2. Trộn vào hàng đợi

- Chèn đều trong vùng review: `k = max(1, n_top // n_audit)`, sau mỗi `k` ảnh vùng review chèn 1 ảnh audit,
  theo thứ tự đã lấy mẫu. Hết ảnh audit thì phần còn lại của vùng review giữ nguyên.
- Ảnh audit bị bỏ khỏi vị trí cũ ở phần đuôi; phần đuôi còn lại giữ thứ tự rank, nằm sau vùng review.
- Giao diện không cho reviewer biết ảnh nào là audit (giữ như hiện tại: schema không trả `is_audit`).
- Chỉ tính verdict audit khi review theo hàng đợi ưu tiên (`review_order == "priority"`), như code hiện tại.

Ví dụ hàng đợi test 2000 ảnh: `n_top = 400`, `n_tail = 1600`, `n_audit = 80`, `k = 5`, tức sau mỗi 5 ảnh chèn 1 ảnh
audit, reviewer xem 480 ảnh. Với 10000 ảnh: 2000 + 400 audit.

## 3. Tính kết quả

- **Mẫu số**: số ảnh audit có verdict `Lỗi thật` hoặc `Bot nhầm`. Ảnh `Bỏ qua` không vào mẫu số, báo riêng số lượng.
- **Tỉ lệ lỗi sót** `p = số Lỗi thật / mẫu số`, kèm khoảng tin cậy Wilson 95%.
- **Số ảnh lỗi ước lượng ở phần đuôi** `= p × n_tail` (cận dưới, cận trên nhân tương tự từ khoảng tin cậy).
- Mẫu số dưới 30 thì ghi kết quả là "chưa đủ mẫu", không kết luận.

## 4. Báo cáo

- Báo **riêng**, không gộp với 150 ảnh kiểm tay (`manual-check-v1`) và không dùng để tính recall@20% của hàng đợi.
- Ghi kèm `N`, `n_top`, `n_tail`, `n_audit`, seed, `model_version` và `queue_id` của hàng đợi đã dùng.
- Verdict audit được dùng để học lại GBM như verdict thường, nhưng giữ cột `is_audit` để tách khi phân tích.
