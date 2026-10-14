# Hướng dẫn kiểm tay · manual-check-v1

Mục đích: đo tỉ lệ **lỗi thật** trên nhãn gốc BDD100K (bản 2018) ở 150 ảnh, để so ảnh đầu hàng đợi với ảnh
ngẫu nhiên. Đây là thước đo cuối của dự án, nên hai người phải kiểm **độc lập** và theo **cùng một tiêu chí**.

## 1. Nguyên tắc

- Sơn kiểm đủ 150 ảnh trong `data/manual_check/manual-check-v1.csv` (đã xong 14/10). Long kiểm 75 ảnh trong
  `manual-check-v1.long.csv` (38 ngẫu nhiên + 37 đầu hàng đợi), là phần chung để tính kappa. Kiểm theo `check_order`.
- Không xem phiếu của nhau, không trao đổi về từng ảnh cho đến khi **cả hai** đã nộp phiếu.
- Không mở `manual-check-v1.key.json` (cho biết ảnh nào do tool chọn) trước khi đối chiếu xong.
- Chỉ xem **nhãn gốc**. Không vẽ dự đoán model hay box nghi vấn, không xem hàng đợi trong lúc kiểm.
- Chấm theo guideline gán nhãn BDD100K, ngưỡng nhỏ theo `docs/guideline-m13.docx` (vật cao dưới 10px không bắt buộc gán).

## 2. Vẽ box

Cần ảnh val của các ảnh cần kiểm trong `data/bdd100k/images/100k/val/`. Lệnh dưới vẽ nhãn gốc của các ảnh trong
`LIST` ra `reports/viz/kiem-tay/`, tên file có số `check_order` ở đầu để mở theo thứ tự; nhãn ghi `class chiều cao`,
thêm `O` nếu occluded, `T` nếu truncated:

```bash
LIST=data/manual_check/manual-check-v1.long.csv python -c "
import os
from pathlib import Path
import pandas as pd
from src.data import bdd100k
from src.viz.draw import draw_image
objects, _ = bdd100k.load()
flags = objects['occluded'].map({True: ' O', False: ''}) + objects['truncated'].map({True: ' T', False: ''})
objects = objects.assign(category=objects['category'] + flags)
out = Path('reports/viz/kiem-tay')
for r in pd.read_csv(os.environ['LIST'], dtype=str).itertuples():
    draw_image(r.image_id, objects, out_dir=out).rename(out / f'{int(r.check_order):03d}_{r.image_id}.jpg')
"
```

Chữ dày ở ảnh đông xe thì phóng to, hoặc mở ảnh gốc `data/bdd100k/images/100k/val/<image_id>.jpg` để so.

## 3. Phiếu

Mỗi người một file `data/manual_check/phieu-<ten>.csv` (phiếu trống trên Drive, đủ dòng theo danh sách của mình, chỉ điền 4 cột cuối):

| Cột | Giá trị |
|---|---|
| `ket_luan` | `loi` · `khong_loi` · `khong_chac` |
| `loai_loi` | `thieu_box` · `sai_class` · `box_lech` · `box_thua` · `thieu_thuoc_tinh` · `khac`; nhiều loại thì nối bằng `;` |
| `so_box_loi` | số box sai hoặc thiếu trong ảnh (`loi` thì ≥ 1, còn lại để trống) |
| `ghi_chu` | box nào, vì sao; bắt buộc khi chọn `khong_chac` hoặc `khac` |

## 4. Thế nào là lỗi

Ảnh là `loi` khi có **ít nhất một** lỗi chắc chắn dưới đây:

| Loại | Khi nào |
|---|---|
| `thieu_box` | Vật thuộc 10 class, cao từ 10px, nhìn rõ, nhưng không có box |
| `sai_class` | Box ghi sai class, vd. người đi xe máy ghi `pedestrian` thay vì `rider`, đèn đường ghi `traffic light` |
| `box_lech` | Box lệch rõ: một cạnh cắt mất hoặc chừa thừa hơn khoảng 20% chiều rộng/cao của vật |
| `box_thua` | Box không có vật, hai box cho cùng một vật, hoặc gán vật trong gương / trên biển quảng cáo |
| `thieu_thuoc_tinh` | Vật bị mép ảnh cắt mà không có `T`, hoặc bị che rõ mà không có `O` |

Ảnh là `khong_chac` khi chỗ nghi ngờ chỉ nằm ở vật:

- cao dưới 10px, hoặc bị che quá nửa;
- quá mờ, quá tối để biết là vật gì hay thuộc class nào;
- lệch box nhỏ, khó nói là quá 20%.

Ảnh có một lỗi chắc chắn **và** vài chỗ không chắc thì vẫn là `loi`; ghi chỗ không chắc vào `ghi_chu`.
Còn lại là `khong_loi`. Không chắc giữa `loi` và `khong_loi` thì chọn `khong_chac`, đừng đoán.

## 5. Sau khi cả hai nộp phiếu

1. Đối chiếu hai phiếu trên 75 ảnh chung, tính Cohen's kappa trên các ảnh cả hai cùng ghi `loi` hoặc `khong_loi`;
   báo riêng số ảnh có ít nhất một người ghi `khong_chac`. Kappa dưới 0.6 thì tiêu chí chưa rõ, bàn lại trước khi dùng số.
2. Hai người thống nhất kết luận cho các ảnh lệch nhau, ghi lý do.
3. Mở `manual-check-v1.key.json`, tách tỉ lệ lỗi theo nhóm ảnh ngẫu nhiên và nhóm đầu hàng đợi trên đủ 150 ảnh
   (75 ảnh chung lấy kết luận đã thống nhất, 75 ảnh còn lại lấy phiếu Sơn).
4. Phiếu và kết quả gửi qua Drive, không commit.
