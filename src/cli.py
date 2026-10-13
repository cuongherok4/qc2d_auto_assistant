"""Điểm vào duy nhất của pipeline. Xem: python -m src.cli --help

load      đọc nhãn BDD100K, tạo cache parquet           (bước 1)
inject    tiêm lỗi có đáp án                            (bước 2)
rank      tín hiệu + rule -> hàng đợi + evidence     (bước 3–4)
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
    from src import pipeline
    from src.data import bdd100k

    labels = args.labels or config.path("injected_dir") / "det_val_injected.json"
    spec = pipeline.load_spec(args.spec) if args.spec else None
    manifest = pipeline.publish(
        bdd100k.read_frames(labels), args.out or config.path("reports_dir"), args.version,
        names=args.signals, preds_file=args.preds, spec=spec,
        provenance={"kind": "cli_rank", "labels_file": str(Path(labels).resolve()),
                    "labels_sha256": pipeline.sha256(labels)},
    )
    print(f"{manifest['n_images']} ảnh, tín hiệu {', '.join(manifest['used_signals'])}"
          f" -> {manifest['queue_file']}\nevidence -> {manifest['evidence_file']}")
    return 0


def cmd_evaluate(args) -> int:
    from src.eval import evaluate

    answer_file = args.answer or config.path("injected_dir") / "injected_errors.json"
    answer = json.loads(Path(answer_file).read_text(encoding="utf-8"))
    queue = pd.read_csv(args.queue, dtype={"image_id": str, "model_version": str}).fillna({"top_reasons": ""})
    out = args.out or config.path("reports_dir") / f"eval_{queue.model_version.iloc[0]}_{args.split}"
    result = evaluate.comparison(queue, answer, out, split=args.split, top_frac=args.top_frac)
    result["queue_file"] = str(Path(args.queue).resolve())
    evaluate.append_result(result, config.path("reports_dir") / "results.jsonl")
    keys = ("recall20_img", "recall20_weighted", "precision20", "ndcg", "time_saved")
    print(pd.read_csv(out / "comparison.csv")[["method", *keys]].to_string(index=False))
    print(f"chi tiết -> {out}; dòng mới trong reports/results.jsonl")
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
    preds = pd.DataFrame(
        [
            ["b1c66a42-6f7d68ca", 100.0, 300.0, 260.0, 420.0, "car", 0.91],
            ["b1c66a42-6f7d68ca", 640.0, 200.0, 660.0, 250.0, "traffic light", 0.55],
            ["b1c81faa-3df17267", 50.0, 310.0, 90.0, 420.0, "pedestrian", 0.78],
        ],
        columns=contracts.PRED_COLS,
    )
    queue = pd.DataFrame(
        [
            [
                "b1c66a42-6f7d68ca",
                87.5,
                1,
                "Thiếu car cao 120px, model chắc 0.91 | Ảnh đêm, 23 box",
                "sample",
            ],
            ["b1c81faa-3df17267", 12.0, 2, "Ảnh đông 31 box (bách phân vị 92)", "sample"],
        ],
        columns=contracts.QUEUE_COLS,
    )
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

    image_ids = pd.read_csv(args.queue, dtype={"image_id": str}).image_id.tolist() if args.queue else None
    output = args.out or config.path("cvat_map")
    n = cvat_sync.sync(
        args.url or config.load("paths")["cvat_url"], output, task_ids=args.task_id, image_ids=image_ids
    )
    print(f"Đã khớp {n} ảnh -> {output}; ảnh thiếu xem {output.with_suffix('.report.json')}")
    return 0


def cmd_guideline_extract(args) -> int:
    from src.guideline.extract import extract

    options, backend = {}, None
    if args.model:
        options["model"] = args.model
    if args.fixture_response:
        import hashlib

        raw = args.fixture_response.read_bytes()
        options.update(
            provider="fixture", model="offline-fixture", fixture_sha256=hashlib.sha256(raw).hexdigest()
        )

        def backend(pages, schema, cfg):
            return json.loads(raw)

        print("FIXTURE: không gọi Gemini; chưa nghiệm thu guideline thật", file=sys.stderr)
    output = extract(args.file, args.outdir, options=options, backend=backend)
    print(f"Draft chưa duyệt -> {output}")
    return 0


def cmd_guideline_approve(args) -> int:
    from src.guideline.extract import approve

    output = approve(args.draft, args.approved_by, acknowledged=args.confirm_reviewed, outdir=args.outdir)
    print(f"Spec đã duyệt -> {output}; người phụ trách rule engine cần tiếp nhận bằng load_approved")
    return 0


def cmd_guideline_samples(args) -> int:
    from docx import Document

    samples = json.loads((config.ROOT / "tests/fixtures/guidelines/samples.json").read_text(encoding="utf-8"))
    out = args.out or config.ROOT / "data/samples/guidelines"
    out.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        document = Document()
        for paragraph in sample["paragraphs"]:
            document.add_paragraph(paragraph)
        document.save(out / f"{sample['id']}.docx")
        (out / f"{sample['id']}.response.json").write_text(
            json.dumps(sample["response"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"3 guideline FIXTURE để phát triển, không phải tài liệu của Long -> {out}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    cfg = config.load("review")
    uvicorn.run(
        "src.api.main:app",
        host=args.host or cfg["server_host"],
        port=args.port or cfg["server_port"],
        reload=args.reload,
    )
    return 0


def cmd_doctor(args) -> int:
    from src.api.operations import doctor

    result = doctor(verify_cvat=args.verify_cvat)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_extension_pack(args) -> int:
    from src.api.operations import package_extension

    output = args.out or config.ROOT / "data/packages/m13-review-extension.zip"
    count = package_extension(output)
    print(f"{count} file -> {output}; giải nén rồi Load unpacked trong Chrome")
    return 0


def cmd_pilot_export(args) -> int:
    from src.api.operations import export_pilot

    result = export_pilot(
        args.out,
        reviewer=args.reviewer,
        session_id=args.session_id,
        include_development=args.include_development,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_guideline_review(args) -> int:
    from src.guideline.review import review_sheet

    path = review_sheet(args.draft, args.out or args.draft.with_suffix(".review.html"))
    print(f"Phiếu đối chiếu, chưa duyệt -> {path}")
    return 0


def cmd_pilot_register(args) -> int:
    from src.api.pilot import PilotPlan, register

    result = register(PilotPlan.model_validate_json(args.plan.read_text()), confirmed=args.confirm_human)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_pilot_compare(args) -> int:
    from src.api.pilot import compare

    print(json.dumps(compare(args.first, args.second, args.out), ensure_ascii=False, indent=2))
    return 0


def cmd_review_fixtures(args) -> int:
    from src.api.fixtures import prepare

    print(json.dumps(prepare(args.out), ensure_ascii=False, indent=2))
    return 0


def cmd_cvat_import(args) -> int:
    from src.api.cvat_import import import_batch

    result = import_batch(
        args.url or config.load("paths")["cvat_url"],
        args.queue,
        args.images or config.path("images_dir"),
        args.labels or config.path("labels_json"),
        args.name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_cvat_prepare(args) -> int:
    from src.api.cvat_install import prepare_install

    print(json.dumps(prepare_install(args.out, project=args.project, port=args.port), indent=2))
    return 0


def cmd_cvat_restore(args) -> int:
    from src.api.cvat_install import restore_source

    print(json.dumps(restore_source(args.out), indent=2))
    return 0


def cmd_cvat_preflight(args) -> int:
    from src.api.cvat_install import preflight

    result = preflight(args.folder)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


def cmd_demo_prepare(args) -> int:
    from src.api.demo_setup import prepare_demo

    print(json.dumps(prepare_demo(args.out, image=args.image), ensure_ascii=False, indent=2))
    return 0


def cmd_demo_connect(args) -> int:
    from src.api.demo_setup import connect_demo

    print(json.dumps(connect_demo(args.folder, args.url, args.name), ensure_ascii=False, indent=2))
    return 0


def cmd_demo_pack(args) -> int:
    from src.api.demo_setup import pack_demo

    print(json.dumps(pack_demo(args.folder, args.out), ensure_ascii=False, indent=2))
    return 0


def cmd_guideline_ui(args) -> int:
    import uvicorn

    from src.guideline.editor import create_editor

    cfg = config.load("guideline-ui")
    port = args.port or cfg["port"]
    app = create_editor(args.drafts, args.approved)
    print(f"Mở http://127.0.0.1:{port} · chỉ người dùng chủ động duyệt spec")
    uvicorn.run(app, host=cfg["host"], port=port)
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

    p = sub.add_parser("rank", help="tín hiệu + rule -> ranked_queue, evidence, manifest (không ghi đè)")
    p.add_argument("--labels", type=Path, help="mặc định: nhãn đã tiêm lỗi")
    p.add_argument("--version", default="rule-v0")
    p.add_argument("--signals", nargs="+", help="mặc định: configs/pipeline.yaml signals")
    p.add_argument("--preds", type=Path, help="yolo_preds.parquet; bật 4 tín hiệu detector")
    p.add_argument("--spec", type=Path, help="spec guideline ĐÃ DUYỆT; bật tín hiệu guideline")
    p.add_argument("--out", type=Path, help="mặc định: reports/")
    p.set_defaults(fn=cmd_rank)

    p = sub.add_parser("evaluate", help="đo hàng đợi vs file order/random, gain curve, ghi results.jsonl")
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--answer", type=Path, help="mặc định: data/injected/injected_errors.json")
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--top-frac", type=float, default=0.2)
    p.add_argument("--out", type=Path, help="mặc định: reports/eval_<version>_<split>/")
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("check", help="kiểm file đúng quy ước")
    p.add_argument("--preds", type=Path)
    p.add_argument("--queue", type=Path)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("samples", help="tạo file mẫu đúng quy ước (preds + queue)")
    p.set_defaults(fn=cmd_samples)

    p = sub.add_parser("cvat-sync", help="sinh bảng image_id -> task/job/frame từ CVAT local")
    p.add_argument("--url")
    p.add_argument("--task-id", type=int, action="append", help="chỉ task demo; dùng nhiều lần")
    p.add_argument("--queue", type=Path, help="chỉ khớp ảnh có trong CSV này")
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_cvat_sync)

    p = sub.add_parser("guideline", help="trích draft và duyệt guideline có nguồn kiểm chứng")
    guideline = p.add_subparsers(dest="guideline_cmd", required=True)
    p = guideline.add_parser("extract")
    p.add_argument("file", type=Path)
    p.add_argument("--outdir", type=Path)
    p.add_argument("--model", help="model Gemini; mặc định configs/guideline_extract.yaml")
    p.add_argument("--fixture-response", type=Path, help="chỉ dev: JSON offline, đánh dấu provider=fixture")
    p.set_defaults(fn=cmd_guideline_extract)
    p = guideline.add_parser("review", help="tạo phiếu HTML đối chiếu nguồn/spec, không tự duyệt")
    p.add_argument("draft", type=Path)
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_guideline_review)
    p = guideline.add_parser("approve")
    p.add_argument("draft", type=Path)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--confirm-reviewed", action="store_true", help="người duyệt xác nhận đã đọc PDF/spec")
    p.add_argument("--outdir", type=Path)
    p.set_defaults(fn=cmd_guideline_approve)
    p = guideline.add_parser("ui", help="giao diện local sửa/duyệt spec, không gọi Gemini")
    p.add_argument("--drafts", type=Path, required=True)
    p.add_argument("--approved", type=Path, required=True)
    p.add_argument("--port", type=int)
    p.set_defaults(fn=cmd_guideline_ui)
    p = guideline.add_parser("samples", help="tạo 3 DOCX fixture và JSON offline cho dev")
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_guideline_samples)

    p = sub.add_parser("serve", help="chạy API review local")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("doctor", help="kiểm tra môi trường và đầu vào, không in credentials")
    p.add_argument("--out", type=Path, help="lưu bằng chứng riêng cho máy đang kiểm tra")
    p.add_argument(
        "--verify-cvat", action="store_true", help="đọc nhãn/meta của từng ảnh để kiểm task/job/frame"
    )
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("extension-pack", help="đóng gói extension MV3")
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_extension_pack)
    p = sub.add_parser("pilot-export", help="xuất verdict và thời gian đã đo, tách theo phiên/thứ tự")
    p.add_argument("--out", type=Path, required=True, help="dữ liệu đo thật: lưu trong data/, không commit")
    p.add_argument("--reviewer")
    p.add_argument("--session-id")
    p.add_argument(
        "--include-development",
        action="store_true",
        help="export fixture/development riêng, không dùng làm pilot",
    )
    p.set_defaults(fn=cmd_pilot_export)
    p = sub.add_parser("pilot-register", help="người review đăng ký phiên thật trước khi bắt đầu đo")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--confirm-human", action="store_true")
    p.set_defaults(fn=cmd_pilot_register)
    p = sub.add_parser(
        "pilot-compare", help="so sánh hai summary pilot cùng snapshot, hai task và hai reviewer"
    )
    p.add_argument("first", type=Path)
    p.add_argument("second", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_pilot_compare)
    p = sub.add_parser("review-fixtures", help="tạo 3 ảnh tổng hợp/nhãn/queue/evidence để kiểm API và CVAT")
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_review_fixtures)
    p = sub.add_parser("cvat-import", help="nạp ảnh trong queue và nhãn 2D BDD vào task CVAT MỚI")
    p.add_argument("--name", required=True)
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--images", type=Path)
    p.add_argument("--labels", type=Path)
    p.add_argument("--url")
    p.set_defaults(fn=cmd_cvat_import)

    p = sub.add_parser("cvat-prepare", help="chuẩn bị Compose ghim phiên bản, project/cổng riêng")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--project")
    p.add_argument("--port", type=int)
    p.set_defaults(fn=cmd_cvat_prepare)
    p = sub.add_parser("cvat-restore-source", help="khôi phục file nguồn đã mất, không ghi đè nội dung khác")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_cvat_restore)
    p = sub.add_parser("cvat-preflight", help="kiểm tài nguyên/bộ cài/cổng trước khi dựng stack cô lập")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path)
    p.set_defaults(fn=cmd_cvat_preflight)
    p = sub.add_parser("demo-prepare", help="demo mang sang máy khác, chạy lại không reset dữ liệu")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--image", type=Path, help="JPEG/PNG 1280×720, không có nhãn/QC")
    p.set_defaults(fn=cmd_demo_prepare)
    p = sub.add_parser("demo-connect", help="import task mới hoặc đọc lại task đã đăng ký, sinh mapping")
    p.add_argument("folder", type=Path)
    p.add_argument("--url", default="http://localhost:8080")
    p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_demo_connect)
    p = sub.add_parser("demo-pack", help="đóng gói demo, loại DB/mapping/credentials của máy")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_demo_pack)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError, ImportError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
