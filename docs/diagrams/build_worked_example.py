"""Draw a concrete, explicitly synthetic walkthrough of M13 inputs and outputs."""

import json

from build_system_diagrams import INK, MUTED, OUT, arrow, box, note, plt, save
from matplotlib.patches import Circle, Polygon, Rectangle

OBJECTS = {
    "A": {"box": [120, 390, 360, 510], "label": "car", "prediction": "car", "conf": 0.95},
    "B": {"box": [720, 400, 900, 460], "label": None, "prediction": "car", "conf": 0.91},
    "C": {"box": [570, 350, 606, 368], "label": "car", "prediction": "car", "conf": 0.88},
    "D": {"box": [990, 380, 1020, 470], "label": "car", "prediction": "pedestrian", "conf": 0.93},
}
SIGNALS = [("Thiếu box B", 0.9, 1.5), ("Sai class D", 0.8, 1.2), ("Vi phạm R1 ở C", 0.6, 1.0)]
SCORE = round(
    100 * sum(value * weight for _, value, weight in SIGNALS) / sum(weight for _, _, weight in SIGNALS), 2
)


def page(index, title, subtitle, height):
    fig, ax = plt.subplots(figsize=(16, height), dpi=130)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.patch.set_facecolor("white")
    ax.set(xlim=(0, 16), ylim=(0, height))
    ax.axis("off")
    ax.text(0.55, height - 0.48, f"M13 / VÍ DỤ {index}", color="#356ad2", weight="bold", fontsize=12)
    ax.text(0.55, height - 0.99, title, color=INK, weight="bold", fontsize=25)
    ax.text(0.55, height - 1.40, subtitle, color=MUTED, fontsize=12)
    ax.plot([0.55, 15.45], [height - 1.64] * 2, color="#dbe4ec")
    ax.text(
        0.55,
        0.30,
        "VÍ DỤ GIẢ LẬP · Ảnh vẽ minh họa, guideline và đầu ra model đều giả định",
        color=MUTED,
        fontsize=11,
    )
    return fig, ax


def scene(fig, rect, kind):
    """Draw identical 1280x720 scene with existing labels or mock detector boxes."""
    ax = fig.add_axes(rect)
    ax.set(xlim=(0, 1280), ylim=(720, 0))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1280, 720, color="#dceef8"))
    for x, y, w, h in [
        (0, 140, 140, 190),
        (155, 190, 110, 140),
        (275, 230, 120, 100),
        (940, 170, 150, 160),
        (1100, 100, 180, 230),
    ]:
        ax.add_patch(Rectangle((x, y), w, h, color="#a6bbca"))
        for wx in range(x + 15, x + w - 15, 30):
            for wy in range(y + 15, y + h - 15, 35):
                ax.add_patch(Rectangle((wx, wy), 13, 18, color="#e8f1f7"))
    ax.add_patch(Rectangle((0, 320), 1280, 400, color="#a9c7ac"))
    ax.add_patch(Polygon([(525, 320), (750, 320), (1280, 720), (0, 720)], color="#727e8b"))
    ax.add_patch(Polygon([(510, 320), (525, 320), (0, 720), (0, 680)], color="#d3d8de"))
    ax.add_patch(Polygon([(750, 320), (765, 320), (1280, 680), (1280, 720)], color="#d3d8de"))
    for y, h in [(350, 22), (405, 32), (485, 45), (595, 65)]:
        ax.add_patch(Polygon([(631, y), (639, y), (645, y + h), (627, y + h)], color="#f9e6a5"))
    for key, obj in OBJECTS.items():
        x1, y1, x2, y2 = obj["box"]
        w, h = x2 - x1, y2 - y1
        if key == "D":
            ax.add_patch(Circle((x1 + w / 2, y1 + 12), 10, color="#c49b7a"))
            ax.add_patch(Rectangle((x1 + 5, y1 + 23), w - 10, 35, color="#ab5361"))
            ax.plot([x1 + 10, x1 + 7], [y1 + 58, y2 - 2], color="#263e51", lw=3)
            ax.plot([x2 - 10, x2 - 7], [y1 + 58, y2 - 2], color="#263e51", lw=3)
        else:
            fill = {"A": "#4471a0", "B": "#ddaa51", "C": "#b86665"}[key]
            ax.add_patch(
                Polygon(
                    [
                        (x1, y1 + h * 0.4),
                        (x1 + w * 0.23, y1),
                        (x1 + w * 0.74, y1),
                        (x2, y1 + h * 0.4),
                        (x2, y2 - h * 0.1),
                        (x1, y2 - h * 0.1),
                    ],
                    color=fill,
                )
            )
            ax.add_patch(
                Polygon(
                    [
                        (x1 + w * 0.24, y1 + h * 0.08),
                        (x1 + w * 0.7, y1 + h * 0.08),
                        (x1 + w * 0.83, y1 + h * 0.4),
                        (x1 + w * 0.15, y1 + h * 0.4),
                    ],
                    color="#c4e1ec",
                )
            )
            for wheel in [x1 + w * 0.2, x1 + w * 0.8]:
                ax.add_patch(Circle((wheel, y2 - h * 0.13), h * 0.12, color="#263540"))
        color = "#087d60" if kind == "labels" else "#305bc4"
        has_box = kind != "labels" or obj["label"] is not None
        if has_box:
            ax.add_patch(Rectangle((x1, y1), w, h, fill=False, edgecolor=color, lw=2))
        # A-D identify objects for the explanatory table; they are not predicted classes.
        lx, ly = {"A": (180, 570), "B": (820, 535), "C": (565, 265), "D": (1050, 540)}[key]
        ax.annotate(
            key,
            xy=((x1 + x2) / 2, y1 if key == "C" else y2),
            xytext=(lx, ly),
            ha="center",
            va="center",
            weight="bold",
            fontsize=14,
            color="white",
            bbox={
                "boxstyle": "circle,pad=.25",
                "facecolor": color if has_box else "#697580",
                "edgecolor": "white",
            },
            arrowprops={"arrowstyle": "-", "color": color if has_box else "#697580"},
        )
    ax.text(25, 45, "street_017.jpg · 1280 × 720", fontsize=12, color=INK)
    return ax


def guideline_figure():
    fig, ax = page(
        "1/2",
        "Guideline được gửi vào LLM để làm gì?",
        "Một batch có hai đầu vào: ảnh + nhãn hiện tại, và tài liệu quy định cách gán nhãn.",
        13,
    )
    box(
        ax,
        0.55,
        7.83,
        5.95,
        3.16,
        "01  guideline-demo.pdf · trang 2",
        "“Chỉ gán car và pedestrian.\nBỏ qua car thấp hơn 30 pixel.\n"
        "Bỏ qua pedestrian thấp hơn 40 pixel.\nChiều cao đo trên ảnh gốc.”\n\n"
        "Đây là guideline giả lập để giải thích.",
        "long",
        fs=14,
    )
    box(
        ax,
        8.05,
        7.83,
        7.4,
        3.16,
        "02  LLM đọc văn bản và trích quy tắc",
        "Nhận: nội dung trang 2 + yêu cầu định dạng.\n"
        "Yêu cầu: lấy class, ngưỡng, đơn vị, câu trích/trang.\n"
        "Không có thông tin → đưa vào mục unclear.\n\n"
        "Kết quả: bản nháp có cấu trúc để chương trình đọc.\n"
        "Bước này chưa chấm điểm hay kết luận ảnh sai.",
        "tuanh",
        fs=14,
    )
    arrow(ax, [(6.5, 9.4), (8.05, 9.4)], "văn bản", label_xy=(7.27, 9.68))
    box(
        ax,
        8.05,
        3.82,
        7.4,
        3.32,
        "03  Ví dụ nội dung spec nháp",
        "classes: [car, pedestrian]\nmin_height_px: {car: 30, pedestrian: 40}\n"
        "R1: kiểm box đã gán thấp hơn ngưỡng\nsource: trang 2 + câu trích tương ứng\n"
        "approved_by: rỗng (chưa được dùng chính thức)\n\n"
        "Hiển thị rút gọn; schema đầy đủ nằm trong code.",
        "cuong",
        fs=14,
    )
    arrow(ax, [(11.75, 7.83), (11.75, 7.14)], "LLM trả bản nháp", label_xy=(13.18, 7.49))
    box(
        ax,
        0.55,
        3.82,
        5.95,
        3.32,
        "04  Long đọc lại nguồn và duyệt",
        "Đúng class? Đúng 30 / 40 px?\nCó câu trích? Có tự suy diễn không?\n\n"
        "Đúng → ghi người duyệt và phiên bản.\nSai / thiếu → sửa, hỏi lại trước khi duyệt.\n\n"
        "Tú Anh đã viết công cụ trích xuất / editor.",
        "long",
        fs=14,
    )
    arrow(ax, [(8.05, 5.48), (6.5, 5.48)], "đối chiếu", label_xy=(7.27, 5.77))
    box(
        ax,
        0.55,
        0.98,
        14.9,
        2.04,
        "05  Spec đã duyệt được dùng ở HAI chỗ",
        "Rule kiểm nhãn: box car C cao 18 px < 30 px → nghi gán thừa theo R1.\n"
        "Lọc prediction: detector thấy car C cao 18 px → bỏ khỏi tập bắt buộc phải có nhãn.\n"
        "Nhờ vậy, một vật nhỏ được phép bỏ qua sẽ không bị báo thành “thiếu box”.",
        "son",
        fs=14,
    )
    arrow(ax, [(3.52, 3.82), (3.52, 3.02)])
    save(fig, ax, "05-vi-du-guideline-llm")


def image_figure():
    fig, ax = page(
        "2/2",
        "Một ảnh đi qua QC và biến thành hàng đợi thế nào?",
        "Tiếp ví dụ 1: spec đã duyệt yêu cầu car ≥ 30 px, pedestrian ≥ 40 px trên ảnh gốc.",
        17,
    )
    ax.text(0.55, 14.97, "01  Ảnh + nhãn hiện có", color=INK, fontsize=18, weight="bold")
    ax.text(8.35, 14.97, "02  Cùng ảnh → detector → prediction", color=INK, fontsize=17, weight="bold")
    scene(fig, [0.55 / 16, 10.6 / 17, 7.10 / 16, 4.0 / 17], "labels")
    scene(fig, [8.35 / 16, 10.6 / 17, 7.10 / 16, 4.0 / 17], "predictions")
    note(
        ax,
        0.55,
        10.48,
        "Box xanh lá = nhãn đang có: A, C, D.\nB có trong cảnh nhưng chưa được gán box.",
        fs=12.5,
    )
    note(
        ax,
        8.35,
        10.48,
        "Box xanh dương = model dự đoán: A, B, C, D.\nA–D là ký hiệu minh họa để đối chiếu bảng dưới.",
        fs=12.5,
    )
    arrow(ax, [(7.65, 12.62), (8.35, 12.62)])
    ax.text(0.55, 9.36, "03  Ghép box và đối chiếu với spec đã duyệt", color=INK, fontsize=18, weight="bold")
    columns = [0.55, 2.45, 5.65, 9.00, 15.45]
    ax.add_patch(Rectangle((0.55, 8.65), 14.9, 0.48, color="#edf2f7"))
    for x, label in zip(
        columns[:-1], ["Vật / cao", "Nhãn hiện có", "Detector giả định", "Xử lý của QC"], strict=True
    ):
        ax.text(x + 0.13, 8.82, label, fontsize=13, color=INK, weight="bold")
    rows = [
        ["A · 120 px", "car", "car · conf 0,95", "Khớp nhãn, đủ ngưỡng → không có cảnh báo này"],
        ["B · 60 px", "Không có box", "car · conf 0,91", "Đủ 30 px, không ghép được nhãn → nghi thiếu box"],
        ["C · 18 px", "car", "car · conf 0,88", "Lọc prediction C; R1 vẫn bắt nhãn C dưới ngưỡng"],
        ["D · 90 px", "car", "pedestrian · conf 0,93", "Ghép cùng vị trí, khác class → nghi sai class"],
    ]
    for i, row in enumerate(rows):
        y = 8.27 - i * 0.59
        for x, label in zip(columns[:-1], row, strict=True):
            ax.text(x + 0.13, y, label, fontsize=11.5, color=INK)
        ax.plot([0.55, 15.45], [y - 0.18] * 2, color="#dbe4ec", lw=0.8)
    note(
        ax,
        0.65,
        6.08,
        "Thứ tự: lọc theo spec → ghép vị trí box → so class. Nhãn gốc vẫn được rule R1 kiểm riêng.",
        fs=12,
    )
    box(
        ax,
        0.55,
        3.60,
        7.1,
        1.94,
        "04  Chuyển thành tín hiệu 0–1",
        "Ví dụ giả định: thiếu B = 0,90; sai D = 0,80; R1 = 0,60.\n"
        "Đây là giá trị tín hiệu minh họa, không phải conf detector.\n"
        "Bằng chứng giữ box cụ thể + lý do cho từng tín hiệu.",
        "son",
        fs=12.5,
    )
    box(
        ax,
        8.35,
        3.60,
        7.1,
        1.94,
        f"05  Rule scorer → {SCORE:.2f}/100 điểm rủi ro",
        "Trong ví dụ chỉ dùng 3 tín hiệu; trọng số 1,5 / 1,2 / 1,0.\n"
        "100 × (1,5×0,90 + 1,2×0,80 + 1×0,60) / 3,7 = 78,65.\n"
        "Điểm này dùng xếp hạng; không phải xác suất sai.",
        "cuong",
        fs=12.5,
    )
    arrow(ax, [(4.1, 5.87), (4.1, 5.54)])
    arrow(ax, [(7.65, 4.57), (8.35, 4.57)])
    box(
        ax,
        0.55,
        0.85,
        7.1,
        2.18,
        "06  API + extension hiển thị cho reviewer",
        "street_017.jpg · 78,65 điểm\n"
        "1. Nghi thiếu car B cao 60 px, detector conf 0,91.\n"
        "2. Box D: nhãn car, model thấy pedestrian cao 90 px.\n"
        "3. [R1] Box C cao 18 px, dưới ngưỡng 30 px.",
        "tuanh",
        fs=12.5,
    )
    box(
        ax,
        8.35,
        0.85,
        7.1,
        2.18,
        "07  Reviewer xác nhận rồi lưu verdict",
        "Mở đúng frame CVAT → xem box B / C / D + guideline.\n"
        "Chọn Lỗi thật / Bot nhầm / Bỏ qua.\n"
        "SQLite lưu người, thời gian, queue_id và model_version.\n"
        "Nếu sửa nhãn: Save; chấm lại cần backend QC đã tích hợp.",
        "tuanh",
        fs=12.5,
    )
    arrow(ax, [(11.9, 3.60), (11.9, 3.31), (4.1, 3.31), (4.1, 3.03)])
    arrow(ax, [(7.65, 1.93), (8.35, 1.93)])
    save(fig, ax, "06-vi-du-anh-den-review")


if __name__ == "__main__":
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    guideline_figure()
    image_figure()
    (OUT / "vi-du-du-lieu.json").write_text(
        json.dumps(
            {
                "purpose": "illustration_only_not_model_output",
                "image_id": "street_017",
                "image_size": [1280, 720],
                "objects": OBJECTS,
                "illustrative_signals": [{"name": n, "value": v, "weight": w} for n, v, w in SIGNALS],
                "risk_score": SCORE,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
