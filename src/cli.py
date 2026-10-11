"""Điểm vào duy nhất của pipeline. Xem: python -m src.cli --help

    load      đọc nhãn BDD100K, tạo cache parquet           (bước 1)
    inject    tiêm lỗi có đáp án                            (bước 2)
    rank      tính tín hiệu + chấm điểm rule -> hàng đợi     (bước 3–4)
    evaluate  đo hàng đợi trên đáp án, ghi results.jsonl     (bước 7)
    check     kiểm file preds/queue đúng quy ước
    samples   tạo file mẫu đúng quy ước để code khi chưa có dữ liệu thật
    cvat-sync sinh bảng image_id -> frame từ CVAT local      (bước 5)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from src import config, contracts


def cmd_load(args) -> int:
    from src.data import bdd100k

    objects, images = bdd100k.load(args.labels, use_cache=False)
    print(f"{len(images)} ảnh, {len(objects)} box, {int((images.n_boxes == 0).sum())} ảnh không có box")
    print(objects["category"].value_counts().to_string())
    return 0


def cmd_inject(args) -> int:
    from src.data import bdd100k, inject

    frames, answer = inject.inject(bdd100k.read_frames(args.labels), config.load("injection"))
    out = config.path("injected_dir")
    out.mkdir(parents=True, exist_ok=True)
    (out / "det_val_injected.json").write_text(json.dumps(frames), encoding="utf-8")
    (out / "injected_errors.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
    print(f"{len(answer['errors'])} lỗi -> {out}")
    return 0


def cmd_rank(args) -> int:
    from src.data import bdd100k
    from src.features import geometric, simple_signals
    from src.scoring import rule

    labels = args.labels or config.path("injected_dir") / "det_val_injected.json"
    objects, images = bdd100k.load(labels)
    signals = {}
    for name, fn in {**geometric.SIGNALS, **simple_signals.SIGNALS}.items():
        try:
            signals[name] = fn(objects, images)
        except NotImplementedError as e:
            print(f"bỏ qua {name}: {e}", file=sys.stderr)
    w = config.load("weights")
    queue = rule.rank(signals, w["signals"], args.version, w.get("top_reasons", 3))
    out = config.path("reports_dir") / f"ranked_queue_{args.version}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(out, index=False)
    print(f"{len(queue)} ảnh, dùng {len(signals)} tín hiệu -> {out}")
    return 0


def cmd_evaluate(args) -> int:
    from src.eval import evaluate

    answer = json.loads((config.path("injected_dir") / "injected_errors.json").read_text(encoding="utf-8"))
    result = evaluate.evaluate(pd.read_csv(args.queue), answer, args.split)
    evaluate.append_result(result, config.path("reports_dir") / "results.jsonl")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args) -> int:
    errs = []
    if args.preds:
        errs += contracts.check_preds(pd.read_parquet(args.preds))
    if args.queue:
        errs += contracts.check_queue(pd.read_csv(args.queue))
    print("\n".join(errs) if errs else "OK")
    return 1 if errs else 0


def cmd_samples(args) -> int:
    preds = pd.DataFrame([
        ["b1c66a42-6f7d68ca", 100.0, 300.0, 260.0, 420.0, "car", 0.91],
        ["b1c66a42-6f7d68ca", 640.0, 200.0, 660.0, 250.0, "traffic light", 0.55],
        ["b1c81faa-3df17267", 50.0, 310.0, 90.0, 420.0, "pedestrian", 0.78],
    ], columns=contracts.PRED_COLS)
    queue = pd.DataFrame([
        ["b1c66a42-6f7d68ca", 87.5, 1, "Thiếu car cao 120px, model chắc 0.91 | Ảnh đêm, 23 box", "sample"],
        ["b1c81faa-3df17267", 12.0, 2, "Ảnh đông 31 box (bách phân vị 92)", "sample"],
    ], columns=contracts.QUEUE_COLS)
    preds_p = config.ROOT / "data" / "samples" / "yolo_preds.parquet"
    queue_p = config.path("reports_dir") / "ranked_queue_sample.csv"
    preds_p.parent.mkdir(parents=True, exist_ok=True)
    queue_p.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(preds_p, index=False)
    queue.to_csv(queue_p, index=False)
    print(f"{preds_p}\n{queue_p}")
    return 0


def cmd_cvat_sync(args) -> int:
    from src.api import cvat_sync

    n = cvat_sync.sync(config.load("paths")["cvat_url"], config.path("cvat_map"))
    print(f"Đã khớp {n} ảnh -> {config.path('cvat_map')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("load", help="đọc nhãn BDD100K, tạo cache")
    p.add_argument("--labels", type=Path, help="mặc định: configs/paths.yaml labels_json")
    p.set_defaults(fn=cmd_load)

    p = sub.add_parser("inject", help="tiêm lỗi có đáp án")
    p.add_argument("--labels", type=Path)
    p.set_defaults(fn=cmd_inject)

    p = sub.add_parser("rank", help="tín hiệu + chấm điểm rule -> reports/ranked_queue_<version>.csv")
    p.add_argument("--labels", type=Path, help="mặc định: nhãn đã tiêm lỗi")
    p.add_argument("--version", default="rule-v0")
    p.set_defaults(fn=cmd_rank)

    p = sub.add_parser("evaluate", help="đo hàng đợi, ghi reports/results.jsonl")
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("check", help="kiểm file đúng quy ước")
    p.add_argument("--preds", type=Path)
    p.add_argument("--queue", type=Path)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("samples", help="tạo file mẫu đúng quy ước (preds + queue)")
    p.set_defaults(fn=cmd_samples)

    p = sub.add_parser("cvat-sync", help="sinh bảng image_id -> task/job/frame từ CVAT local")
    p.set_defaults(fn=cmd_cvat_sync)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
