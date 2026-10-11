---
name: bdd100k-data
description: Cách đọc, chuẩn hoá và chia tập dữ liệu BDD100K detection 2D (det_20 JSON, ảnh 1280×720) cho dự án QC nhãn. Dùng khi viết hoặc sửa loader, map tên class, chia train/val/test, đọc thuộc tính weather/timeofday/occluded/truncated, chuyển nhãn sang DataFrame, vẽ box lên ảnh, hoặc khi gặp lỗi lạ do định dạng nhãn BDD (box2d thiếu, tên class cũ person/bike/motor, poly2d).
---

# BDD100K detection 2D

## Tải gì

- **100K Images** → chỉ cần phần `val` (10.000 ảnh `.jpg`, 1280×720).
- **Detection 2020 Labels** (`det_20`) → `det_val.json`.
- Nguồn: https://bdd-data.berkeley.edu (cần đăng ký). Đọc điều khoản sử dụng trước khi dùng cho mục đích ngoài nghiên cứu.
- Đường dẫn khai báo ở `configs/paths.yaml`, không hard-code.

## Định dạng một frame

```json
{
  "name": "b1c66a42-6f7d68ca.jpg",
  "attributes": {"weather": "clear", "timeofday": "night", "scene": "city street"},
  "labels": [
    {"id": "1", "category": "car",
     "attributes": {"occluded": true, "truncated": false, "trafficLightColor": "NA"},
     "box2d": {"x1": 100.2, "y1": 300.1, "x2": 260.0, "y2": 420.5}}
  ]
}
```

Những chỗ dễ sai:

- **`labels` có thể thiếu hoặc là `null`** → coi là ảnh không có object, nhưng **vẫn giữ ảnh** (ảnh trống bị bỏ sót nhãn cũng là lỗi cần bắt).
- Nhãn không có `box2d` (bản 2018 có `poly2d` cho lane/drivable area) → bỏ.
- Tên class bản cũ: `person→pedestrian`, `motor→motorcycle`, `bike→bicycle`. Map qua `configs/class_map.yaml`, áp dụng **ngay khi load** để mọi module phía sau chỉ thấy 10 class chuẩn: pedestrian, rider, car, truck, bus, train, motorcycle, bicycle, traffic light, traffic sign.
- `image_id` = `name` bỏ `.jpg`. Dùng thống nhất ở mọi file.
- Toạ độ là float pixel trên ảnh gốc; một số box chạm/vượt mép nhẹ → clip vào [0, 1280]×[0, 720] khi tính hình học, nhưng **không ghi đè file nhãn gốc**.
- `weather`/`timeofday` có giá trị `undefined` → giữ nguyên làm một nhóm riêng, đừng ép về clear/daytime.

## Dạng bảng nên dùng

Một DataFrame object-level (mỗi dòng một box), đủ cho hầu hết tín hiệu:

```
image_id, obj_id, category, x1, y1, x2, y2, w, h, area,
occluded, truncated, weather, timeofday, scene
```

Và một bảng image-level (`image_id, weather, timeofday, scene, n_boxes`) để không mất ảnh trống. Lưu cache bằng parquet trong `data/cache/` để các bước sau không parse lại JSON (~10k frame mất vài giây, nhưng lặp lại nhiều lần sẽ tốn).

Giữ `obj_id` ổn định (vị trí trong mảng `labels` gốc hoặc trường `id`) vì file đáp án tiêm lỗi tham chiếu tới nó.

## Chia tập

- 6k / 2k / 2k **theo ảnh**, seed 42, sinh một lần rồi lưu vào file đáp án tiêm lỗi (`splits`). Mọi module đọc split từ đó, không tự chia lại.
- Nếu cần cân bằng, stratify theo `timeofday` (ảnh đêm ít hơn và khó hơn).

## Vẽ box để kiểm tay

Dùng `PIL.ImageDraw` hoặc OpenCV; tô màu theo nguồn (nhãn gốc / dự đoán model / box bị nghi). Ghi rõ class + chiều cao px cạnh box, vì reviewer phán đoán theo ngưỡng kích thước. Ảnh xuất ra `reports/viz/` (không commit).

## Test tối thiểu

- Ảnh không có `labels` vẫn xuất hiện trong bảng image-level.
- `person` được map thành `pedestrian`.
- Nhãn không có `box2d` bị bỏ.
- Số ảnh val = 10.000 (test đánh dấu `@pytest.mark.data`, bỏ qua khi chưa có dữ liệu).

Dùng một JSON nhỏ 3–5 frame trong `tests/fixtures/` để test chạy không cần dữ liệu thật.
