"""Generate the team's four shareable architecture diagrams (PNG and SVG)."""

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/m13-diagram-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent
INK = "#172c43"
MUTED = "#50677c"
COLORS = {
    "neutral": ("#eef3f7", "#647b91"),
    "cuong": ("#eaf1ff", "#356ad2"),
    "son": ("#e8f6f1", "#168467"),
    "tuanh": ("#f2ebff", "#8051be"),
    "long": ("#fff3dc", "#ad710d"),
}


def canvas(number, title, subtitle):
    fig, ax = plt.subplots(figsize=(16, 10), dpi=130)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.patch.set_facecolor("#ffffff")
    ax.set(xlim=(0, 16), ylim=(0, 10))
    ax.axis("off")
    ax.text(0.55, 9.55, f"M13  /  {number:02}", fontsize=12, weight="bold", color="#356ad2")
    ax.text(0.55, 9.04, title, fontsize=26, weight="bold", color=INK)
    ax.text(0.55, 8.61, subtitle, fontsize=12.5, color=MUTED)
    ax.plot([0.55, 15.45], [8.36, 8.36], color="#dbe4ec", lw=1)
    ax.text(0.55, 0.30, "NHÓM M13 · 13/10/2026", fontsize=10, weight="bold", color=MUTED)
    ax.text(
        15.45,
        0.30,
        "Kiến trúc / phân công đề xuất · Hiện trạng chi tiết trong bản phân tích",
        ha="right",
        fontsize=10,
        color=MUTED,
    )
    return fig, ax


def box(ax, x, y, w, h, title, body, owner="neutral", tag=None, fs=14):
    fill, line = COLORS[owner]
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", facecolor=fill, edgecolor=line, lw=1.3
    )
    ax.add_patch(patch)
    texts = []
    if tag:
        texts.append(ax.text(x + 0.18, y + h - 0.30, tag.upper(), fontsize=10, color=line, weight="bold"))
    ty = y + h - (0.66 if tag else 0.38)
    texts.append(ax.text(x + 0.18, ty, title, fontsize=16, color=INK, weight="bold", va="top"))
    texts.append(ax.text(x + 0.18, ty - 0.43, body, fontsize=fs, color=INK, va="top", linespacing=1.55))
    for text in texts:
        text._m13_bounds = (x, y, x + w, y + h)


def arrow(ax, points, label=None, dashed=False, color=MUTED, label_xy=None):
    for i in range(len(points) - 1):
        ax.add_patch(
            FancyArrowPatch(
                points[i],
                points[i + 1],
                arrowstyle="-|>" if i == len(points) - 2 else "-",
                mutation_scale=15,
                color=color,
                lw=1.5,
                linestyle="--" if dashed else "-",
                shrinkA=3,
                shrinkB=3,
            )
        )
    if label:
        x, y = label_xy or ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2 + 0.15)
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=11,
            color=color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 2},
        )


def note(ax, x, y, text, fs=13):
    ax.text(x, y, text, fontsize=fs, color=MUTED, va="top", linespacing=1.6)


def save(fig, ax, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in ax.texts:
        if not hasattr(text, "_m13_bounds"):
            continue
        x0, y0, x1, y1 = text._m13_bounds
        bounds = text.get_window_extent(renderer).transformed(ax.transData.inverted())
        if bounds.x0 < x0 or bounds.x1 > x1 or bounds.y0 < y0 or bounds.y1 > y1:
            raise ValueError(f"Text exceeds card in {name}: {text.get_text()}")
    fig.savefig(OUT / f"{name}.png", dpi=160, facecolor="white")
    fig.savefig(OUT / f"{name}.svg", facecolor="white")
    plt.close(fig)
    print(name)


def workflow():
    fig, ax = canvas(
        1,
        "Từ nhãn cần QC đến quyết định của reviewer",
        "Luồng sử dụng thực tế · Không tiêm lỗi vào nhãn của batch đang review",
    )
    box(ax, 5.55, 7.10, 4.9, 0.99, "Guideline → spec đã duyệt", "", "long", fs=12)
    arrow(ax, [(8, 7.10), (8, 6.60)], "quy tắc của batch", label_xy=(9.18, 6.86))
    box(
        ax,
        0.55,
        4.80,
        4.0,
        1.8,
        "01  Batch cần kiểm",
        "Ảnh + nhãn bounding box\nGiữ nguyên nhãn đầu vào",
        tag="Đầu vào",
    )
    box(
        ax,
        6,
        4.80,
        4,
        1.8,
        "02  Tính rủi ro",
        "Hình học + detector + luật\nChưa kết luận là lỗi",
        "cuong",
        tag="Bộ máy QC",
    )
    box(
        ax,
        11.45,
        4.80,
        4,
        1.8,
        "03  Xếp thứ tự xem",
        "Điểm + tối đa 3 lý do\nBox nghi vấn để đối chiếu",
        "cuong",
        tag="Hàng đợi + bằng chứng",
    )
    arrow(ax, [(4.55, 5.70), (6, 5.70)])
    arrow(ax, [(10, 5.70), (11.45, 5.70)])
    box(
        ax,
        11.45,
        2.05,
        4,
        1.95,
        "04  Người review",
        "Mở đúng frame trong CVAT\nLỗi thật / Bot nhầm / Bỏ qua",
        "tuanh",
        tag="API + extension đã có code",
    )
    box(
        ax,
        6,
        2.05,
        4,
        1.95,
        "05  Lưu dấu vết",
        "Verdict + người + thời gian\nGắn phiên bản hàng đợi",
        "tuanh",
        tag="SQLite đã có code",
    )
    box(
        ax,
        0.55,
        2.05,
        4,
        1.95,
        "06  Đo hiệu quả",
        "Tìm lỗi sớm hơn bao nhiêu?\nHiệu quả ở cùng thời gian?",
        "long",
        tag="Cường + Long",
    )
    arrow(ax, [(13.45, 4.8), (13.45, 4)])
    arrow(ax, [(11.45, 3), (10, 3)])
    arrow(ax, [(6, 3), (4.55, 3)])
    note(
        ax,
        0.60,
        1.42,
        "Tú Anh đã viết phần review, lưu vết và công cụ guideline. "
        "Việc tiếp theo: ghép với kết quả QC thật.\n"
        "Sau sửa nhãn và Save: có thể yêu cầu chấm lại khi Cường nối xong backend recheck.",
    )
    save(fig, ax, "01-luong-qc")


def architecture():
    fig, ax = canvas(
        2,
        "Bốn người, một luồng dữ liệu chung",
        "Đọc theo mũi tên · Màu và tên cho biết người phụ trách · Chưa phải sơ đồ các khối đã nghiệm thu",
    )
    xs = [0.55, 5.75, 10.95]
    w = 4.5
    box(
        ax,
        xs[0],
        6.23,
        w,
        1.66,
        "Ảnh + nhãn + prediction",
        "BDD100K; yolo_preds.parquet",
        "son",
        tag="Sơn · chuẩn bị dữ liệu",
        fs=13,
    )
    box(
        ax,
        xs[0],
        3.73,
        w,
        1.90,
        "Ba nhóm tín hiệu",
        "Hình học: Tú Anh + Long\nDetector: Sơn · Luật: Long",
        "neutral",
        tag="SignalResult + evidence",
        fs=13.5,
    )
    box(
        ax,
        xs[0],
        1.23,
        w,
        1.90,
        "Chấm điểm & ghép pipeline",
        "Rule → điểm 0–100 + lý do\nGBM / VLM là phần mở rộng",
        "cuong",
        tag="Cường · còn phần cần nối",
        fs=13.5,
    )
    box(
        ax,
        xs[1],
        6.23,
        w,
        1.66,
        "Guideline → spec đã duyệt",
        "Tú Anh có tools · Long duyệt luật",
        "long",
        tag="Nguồn quy tắc",
        fs=12.5,
    )
    box(
        ax,
        xs[1],
        3.73,
        w,
        1.90,
        "Bộ file bàn giao",
        "ranked_queue_<v>.csv\nevidence_<v>.jsonl",
        "cuong",
        tag="Cường → Tú Anh",
        fs=14,
    )
    box(
        ax,
        xs[1],
        1.23,
        w,
        1.90,
        "Đánh giá & báo cáo",
        "Baseline + recall + gain curve\nKiểm tay + kết quả pilot",
        "long",
        tag="Cường + Long · Sơn kiểm tay",
        fs=13,
    )
    box(
        ax,
        xs[2],
        6.23,
        w,
        1.66,
        "Extension ↔ CVAT local",
        "Queue · đúng frame · verdict",
        "tuanh",
        tag="Tú Anh · đã viết",
        fs=13.5,
    )
    box(
        ax,
        xs[2],
        3.73,
        w,
        1.90,
        "FastAPI + cvat_map",
        "Đọc file · phục vụ ảnh / lý do\nRecheck chờ backend Cường",
        "tuanh",
        tag="Tú Anh · đã viết phía API",
        fs=13,
    )
    box(
        ax,
        xs[2],
        1.23,
        w,
        1.90,
        "SQLite & export pilot",
        "Lưu verdict, thời gian, phiên\nCó công cụ; còn chạy pilot thật",
        "tuanh",
        tag="Tú Anh · đã viết",
        fs=13,
    )
    arrow(ax, [(2.8, 6.23), (2.8, 5.63)])
    arrow(ax, [(2.8, 3.73), (2.8, 3.13)])
    arrow(ax, [(5.75, 6.5), (5.35, 6.5), (5.35, 5.15), (5.05, 5.15)])
    arrow(ax, [(5.05, 2.18), (5.4, 2.18), (5.4, 4.35), (5.75, 4.35)])
    arrow(ax, [(10.25, 4.68), (10.95, 4.68)])
    arrow(ax, [(13.05, 5.63), (13.05, 6.23)])
    arrow(ax, [(13.6, 6.23), (13.6, 5.63)])
    arrow(ax, [(13.2, 3.73), (13.2, 3.13)])
    arrow(ax, [(10.95, 2.18), (10.25, 2.18)])
    arrow(ax, [(8, 3.73), (8, 3.13)])
    note(
        ax,
        0.6,
        0.88,
        "Ghép đúng queue + evidence cùng phiên bản; mapping CVAT sinh riêng trên từng máy.",
        fs=12,
    )
    save(fig, ax, "02-kien-truc")


def evaluation():
    fig, ax = canvas(
        3,
        "Chứng minh tìm lỗi tốt hơn, không chỉ demo chạy được",
        "Tách lỗi tiêm, lỗi thật và thời gian người thật · Mỗi nguồn trả lời một câu hỏi khác nhau",
    )
    ax.text(
        0.55,
        7.94,
        "A  /  THÍ NGHIỆM LỖI TIÊM — so sánh khả năng xếp hạng",
        fontsize=14,
        weight="bold",
        color=COLORS["cuong"][1],
    )
    x = [0.55, 3.65, 6.75, 9.85, 12.95]
    titles = ["Chia theo ảnh", "Tiêm lỗi", "Chấm rủi ro", "Chốt cấu hình", "Đo trên test"]
    bodies = [
        "6k / 2k / 2k\nSeed 42",
        "Theo từng split\nLưu đáp án riêng",
        "Không đọc đáp án\nđể tạo feature",
        "Chọn bằng val\nĐóng băng model",
        "Recall@20%\nGain / từng lỗi",
    ]
    for xx, title, body in zip(x, titles, bodies, strict=True):
        box(ax, xx, 5.75, 2.5, 1.85, title, body, "cuong", fs=12.5)
    for left, right in zip(x[:-1], x[1:], strict=True):
        arrow(ax, [(left + 2.5, 6.7), (right, 6.7)])
    arrow(
        ax,
        [(4.9, 5.75), (4.9, 5.08), (14.2, 5.08), (14.2, 5.75)],
        "Đáp án test chỉ dùng khi tính metric",
        dashed=True,
        label_xy=(9.5, 5.08),
    )
    note(
        ax,
        0.55,
        4.70,
        "Đáp án train được dùng cho GBM nếu triển khai. "
        "So cùng split: random / thứ tự file / rule / bản đầy đủ.",
        fs=12,
    )
    ax.text(
        0.55,
        3.98,
        "B  /  NHÃN THẬT — kiểm lỗi thực tế và đo công sức review",
        fontsize=14,
        weight="bold",
        color=COLORS["long"][1],
    )
    box(
        ax,
        0.55,
        1.80,
        4.35,
        1.86,
        "150 ảnh kiểm tay",
        "75 ngẫu nhiên + 75 top, không trùng\nLong + Sơn kiểm độc lập, đo kappa",
        "long",
        fs=12.5,
    )
    box(
        ax,
        5.8,
        1.80,
        4.35,
        1.86,
        "Pilot cùng batch 30 ảnh",
        "Hai người, hai task CVAT riêng\nƯu tiên ↔ thứ tự file",
        "tuanh",
        fs=13,
    )
    box(
        ax,
        11.1,
        1.80,
        4.35,
        1.86,
        "Kết quả có nguồn",
        "Verdict + thời gian + queue_id\nSo ở cùng ngân sách thời gian",
        "long",
        fs=12.5,
    )
    arrow(ax, [(10.15, 2.75), (11.1, 2.75)])
    note(
        ax,
        0.55,
        1.35,
        "Mẫu kiểm tay không đại diện tự động cho toàn bộ 10k ảnh. "
        "Pilot nhỏ còn chịu ảnh hưởng tốc độ mỗi người.\n"
        "“Time saved” tính theo số ảnh là proxy; chỉ gọi là thời gian thực đo khi có dữ liệu pilot.",
        fs=12.5,
    )
    save(fig, ax, "03-danh-gia")


def handoff():
    fig, ax = canvas(
        4,
        "Phân công từ phần đã có, không giao lại từ đầu",
        "Ưu tiên ghép luồng review và đo hiệu quả · Đường găng là dữ liệu → QC → queue/evidence → pilot",
    )
    box(
        ax,
        0.55,
        5.92,
        4.4,
        2.05,
        "Sơn · dữ liệu & detector",
        "Tiếp: prediction + ghép box\nBàn giao: file + tín hiệu bất đồng\nKiểm tay cùng Long",
        "son",
        tag="Chưa xác minh batch detector thật",
        fs=12.5,
    )
    box(
        ax,
        0.55,
        2.85,
        4.4,
        2.23,
        "Long · guideline & chất lượng",
        "Đã có: 4 tín hiệu, load spec, R1\nTiếp: R2/R3, R4 sau Sơn\nDuyệt spec · kiểm tay · báo cáo",
        "long",
        tag="Code ở nhánh riêng",
        fs=12.5,
    )
    box(
        ax,
        6.02,
        4.25,
        4.4,
        2.55,
        "Cường · ghép & chấm điểm",
        "Nhận code thành viên\nTiêm lỗi + gom evidence + CLI\n"
        "Bàn giao queue thật và baseline\nNối backend recheck khi sẵn",
        "cuong",
        tag="Ưu tiên đường găng",
        fs=12.5,
    )
    box(
        ax,
        11.45,
        4.25,
        4.0,
        3.73,
        "Tú Anh · review & pilot",
        "ĐÃ VIẾT\nAPI / SQLite / CVAT / extension\nGuideline tools / demo / pilot\n\n"
        "TIẾP THEO\nGhép queue + evidence thật\nKiểm frame, verdict, thời gian\nChạy pilot và dựng máy demo",
        "tuanh",
        tag="Ghi nhận phần đã hoàn thành",
        fs=11.5,
    )
    arrow(ax, [(4.95, 6.65), (6.02, 6.0)])
    arrow(ax, [(4.95, 4.0), (6.02, 4.8)])
    arrow(ax, [(10.42, 5.55), (11.45, 5.55)])
    arrow(
        ax,
        [(13.45, 4.25), (13.45, 3.55), (8.22, 3.55), (8.22, 4.25)],
        "pilot export → đánh giá",
        label_xy=(10.9, 3.55),
    )
    note(
        ax,
        0.55,
        2.23,
        "Tú Anh bàn giao công cụ guideline đã viết → Long sử dụng, kiểm spec và hoàn thiện rule engine.\n"
        "Ba tín hiệu hình học khó / công cụ vẽ box của Tú Anh: làm sau tích hợp review, không chặn rule-v0.",
        fs=12.5,
    )
    ax.plot([0.55, 15.45], [1.38, 1.38], color="#dbe4ec", lw=1)
    note(ax, 0.55, 1.11, "13/10  Ghép code", fs=13)
    note(ax, 4.3, 1.11, "14/10  QC cốt lõi", fs=13)
    note(ax, 8.05, 1.11, "15/10  Đo & chốt số", fs=13)
    note(ax, 12.1, 1.11, "16/10  Demo & video", fs=13)
    save(fig, ax, "04-ban-giao")


if __name__ == "__main__":
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    workflow()
    architecture()
    evaluation()
    handoff()
