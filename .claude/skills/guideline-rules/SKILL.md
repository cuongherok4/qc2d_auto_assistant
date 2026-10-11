---
name: guideline-rules
description: Cho LLM đọc guideline gán nhãn (DOCX/PDF) của từng batch thành spec YAML có version, người duyệt, rồi rule engine kiểm nhãn 2D theo spec (ngưỡng chiều cao tối thiểu, class được phép, class gộp, attribute bắt buộc), lý do dẫn chiếu rule ID. Dùng khi viết src/guideline/extract.py, configs/guidelines/*.yaml, src/features/guideline_rules.py, luật nhìn ảnh cho VLM, khi chấm điểm phụ thuộc guideline, khi lọc dự đoán detector theo spec, hoặc khi người dùng nói "guideline", "spec", "ngưỡng box nhỏ", "rule ID", "batch khác nhau quy định khác nhau".
---

# Chấm theo guideline của từng batch

Lý do tồn tại: cùng một box car cao 18px có thể **đúng** với guideline A (ngưỡng 15px) nhưng là **box thừa** với guideline B (ngưỡng 30px). Bài học tuần 1 (P-001): guideline không ghi rõ ngưỡng vật xa/nhỏ/mờ là nguồn lỗi lớn nhất. Nhóm đã đồng ý đưa vào (11/10): LLM đọc guideline ở Vòng 2 / Mốc 2 (theo Q14). Vẫn code sao cho tắt được bằng config (`guideline: null` → hệ thống chạy như không có guideline).

## Luồng

```
DOCX/PDF ─▶ ① LLM đọc (src/guideline/extract.py) ─▶ configs/guidelines/drafts/<id>.yaml
         ─▶ ② người duyệt (điền approved_by)       ─▶ configs/guidelines/<id>.yaml
         ─▶ rules        → ③ rule engine = phép C, 100% ảnh (src/features/guideline_rules.py)
            visual_rules → ④ VLM = phép D, chỉ top 30% (src/features/vlm_check.py, Vòng 4)
            unclear      → báo trưởng nhóm trước khi gán (bài học P-001)
```

Gắn batch với guideline trong `configs/batches.yaml` (`batch_01: bdd_v1@1.0.0`). LLM **chỉ đọc guideline**, không so từng ảnh: so từng ảnh bằng LLM vừa tốn vừa không tái lập được.

## Spec YAML (`configs/guidelines/<tên>.yaml`)

```yaml
id: bdd-default
version: 1.0.0            # tăng khi đổi luật; ghi vào model_version của hàng đợi
approved_by: ""           # người phụ trách duyệt; spec chưa duyệt thì cảnh báo khi chạy
source: {file: guidelines/batch_01.docx, sha256: "..."}   # cache câu trả lời LLM theo hash này
classes: [pedestrian, rider, car, truck, bus, train, motorcycle, bicycle, traffic light, traffic sign]
merge: {}                 # vd {bus: truck} nếu batch gộp bus vào truck
min_height_px:            # theo pixel chiều cao trên ảnh gốc (Q13)
  default: 0
  traffic light: 0
near_threshold_px: 3      # ± bao nhiêu px thì coi là "sát ngưỡng"
iou_loose: 0.7            # ngưỡng box lệch (Q8)
required_attributes: [occluded, truncated]
rules:
  - id: R1
    check: below_min_height
    severity: 0.6
    page: 3                     # mọi luật LLM trích đều có page + quote để người duyệt đối chiếu
    quote: "Không cần gán xe ở xa có chiều cao dưới 15 pixel"
    message: "Box {category} cao {h:.0f}px, dưới ngưỡng {thr}px của guideline"
  - id: R2
    check: class_not_allowed
    severity: 1.0
    message: "Class {category} không có trong guideline {gid}"
  - id: R3
    check: missing_attribute
    severity: 0.3
    message: "Box {category} #{obj_id} thiếu thuộc tính {attr}"
  - id: R4
    check: model_object_missing   # dùng kết quả khớp detector đã lọc theo spec
    severity: 1.0
    message: "Thiếu {category} cao {h:.0f}px (model conf {conf:.2f}), ngưỡng {thr}px"
visual_rules:              # không đo được bằng hình học → câu hỏi đóng cho VLM
  - id: V1
    category: traffic light
    page: 3
    quote: "..."
    question: "Vật trong khung là đèn giao thông hay đèn đường / đèn xe?"
unclear:                   # LLM không tìm thấy → để trống, KHÔNG tự đoán
  - {category: traffic sign, field: min_height_px}
```

Mỗi `check` là một hàm đăng ký trong một dict `CHECKS = {"below_min_height": fn, ...}` — thêm luật mới = thêm hàm + thêm mục YAML, không sửa engine.

## Rule engine

- Đầu vào: bảng object, spec, (tuỳ chọn) kết quả khớp detector. Đầu ra: `SignalResult` theo quy ước, `name="guideline"`, `reason` **bắt đầu bằng rule ID trong ngoặc vuông**: `"[R4] Thiếu car cao 22px (model conf 0.88), ngưỡng 15px"`.
- Áp `merge` **trước** mọi kiểm tra (cả với nhãn lẫn dự đoán).
- **Lọc dự đoán detector theo spec trước khi khớp**: bỏ class không có trong `classes`, bỏ box thấp hơn `min_height_px`. Nếu không, hệ thống sẽ báo "thiếu box" cho object mà guideline cho phép bỏ qua.
- **Ca sát ngưỡng** (|h − thr| ≤ `near_threshold_px`): chỉ cộng một phần nhỏ điểm rủi ro (vd. severity × 0.3), reason ghi "sát ngưỡng", **không kết luận là lỗi**. Lý do: sai số vài px do người kéo box là bình thường.
- value của ảnh = `1 − Π(1 − severity_i)` trên các vi phạm (nhiều vi phạm nhỏ cộng dồn nhưng không vượt 1).

## Thí nghiệm đã đề xuất

Ba guideline giả lập trên cùng BDD100K: (1) gốc BDD, (2) ngưỡng 30px + gộp truck/bus, (3) bỏ traffic sign. Tiêm lỗi **theo từng guideline** (cái gì là lỗi phụ thuộc guideline), rồi so recall@20% của bản biết guideline với bản không biết. Ghi `guideline_id@version` vào `reports/results.jsonl`.

## Bước LLM đọc guideline (`src/guideline/extract.py`)

- Tách văn bản theo trang (`python-docx`, `pdfplumber`), gửi LLM kèm JSON schema sinh từ model `pydantic` của spec. Dùng lại backend V1 Guideline Assistant nếu được; local hay API chưa chốt.
- Temperature 0, ép JSON, validate bằng pydantic; sai schema thì báo lỗi, không tự sửa. Cache theo `sha256` file guideline.
- Mỗi luật bắt buộc có `page` + `quote` nguyên văn. Kiểm `quote` có thật trong văn bản (so chuỗi); không có thì đánh dấu để người duyệt xem kỹ.
- Ngưỡng/class không có trong guideline → đưa vào `unclear`, không điền mặc định.
- Luôn ghi ra `drafts/`, `approved_by` để trống. **Rule engine từ chối spec chưa duyệt** (cho phép `--allow-unapproved` khi dev, kèm cảnh báo).
- Reason hiển thị cho reviewer dẫn trang: `"[R1] traffic light cao 8px, ngưỡng 10px (tr.3)"`.

## Test tối thiểu

- Box 18px: lỗi R1 với ngưỡng 30px, không lỗi với ngưỡng 15px, "sát ngưỡng" với ngưỡng 20px.
- `merge {bus: truck}`: nhãn bus và dự đoán truck không bị báo sai class.
- Dự đoán dưới ngưỡng không sinh R4.
- Spec có `approved_by: ""` bị rule engine từ chối.
- Extract: `quote` không có trong văn bản gốc thì bị đánh dấu; class không có ngưỡng thì vào `unclear`, không có giá trị mặc định (test với LLM giả trả JSON cố định).
