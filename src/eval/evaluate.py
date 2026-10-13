"""Validate complete evaluation splits and compare with file/random baselines."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config, contracts
from src.eval import metrics


def _finite(value):
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def context(queue, answer, split, top_frac, cost=None):
    errors = contracts.check_queue(queue)
    if errors or queue.empty:
        raise ValueError(f"Queue không hợp lệ: {errors}")
    if split not in {"train", "val", "test"} or not 0 < top_frac <= 1:
        raise ValueError("split/top_frac không hợp lệ")
    ids = {i for i, s in answer["splits"].items() if s == split}
    if not ids:
        raise ValueError(f"Split {split} rỗng")
    if not ids.issubset(set(queue.image_id)):
        raise ValueError("Queue thiếu ảnh trong split; không được đo trên một phần hàng đợi")
    if set(queue.image_id) - set(answer["splits"]):
        raise ValueError("Queue chứa ảnh không có trong đáp án")
    source_order = answer["image_order"]
    if len(source_order) != len(set(source_order)) or set(source_order) != set(answer["splits"]):
        raise ValueError("image_order không khớp split manifest")
    if any(e["image_id"] not in answer["splits"] or e["split"] != answer["splits"][e["image_id"]]
           for e in answer["errors"]):
        raise ValueError("Lỗi có image_id/split sai manifest")
    ranked = [i for i in queue.sort_values("rank").image_id if i in ids]
    errors = [e for e in answer["errors"] if e["image_id"] in ids]
    if cost is not None and any(i not in cost or not math.isfinite(cost[i]) or cost[i] <= 0 for i in ids):
        raise ValueError("Thời gian phải hữu hạn, dương và bao phủ đủ mọi ảnh của split")
    return ranked, [i for i in source_order if i in ids], errors


def evaluate(queue: pd.DataFrame, answer: dict, split: str = "test", top_frac: float = .2,
             cost=None, cost_kind=None) -> dict:
    ranked, file_order, errors = context(queue, answer, split, top_frac, cost)
    cfg = config.load("learning")["eval"]
    weights = answer["meta"].get("weights", metrics.DEFAULT_WEIGHTS)
    mass = metrics.error_mass(errors, weights)
    image_mass = metrics.error_mass(errors, weights, weighted=False)
    seeds = cfg["random_seeds"]
    if seeds < 1:
        raise ValueError("random_seeds phải dương")
    orders = list(metrics.random_orders(file_order, seeds, answer["meta"].get("seed", 42)))
    target = cfg["recall_target"]
    random_n = np.mean([metrics.n_to_reach(o, mass, target) for o in orders]) if mass else None

    def score(order):
        return {"recall20_img": metrics.recall_at(order, image_mass, top_frac),
                "recall20_weighted": metrics.recall_at(order, mass, top_frac),
                "precision20": metrics.precision_at(order, image_mass, top_frac),
                "ndcg": metrics.ndcg(order, mass),
                "time_saved": 1-metrics.n_to_reach(order, mass, target)/random_n if mass else None,
                "recall20_time": metrics.recall_at(order, mass, top_frac, cost) if cost else None}

    random_scores = [score(order) for order in orders]
    random_summary = {}
    for key in random_scores[0]:
        vals = [s[key] for s in random_scores if s[key] is not None and math.isfinite(s[key])]
        random_summary[key] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))} if vals else {
            "mean": None, "std": None}
    result = {
        "method": "ranked_queue", "model_version": str(queue.model_version.iloc[0]),
        "split": split, "seed": answer["meta"].get("seed"), "n_images": len(ranked),
        "n_errors": len(errors), "n_error_images": len(image_mass), "top_frac": top_frac,
        "data_kind": "synthetic_errors", "time_saved_kind": "image_count_proxy_not_measured_time",
        "review_cost_kind": cost_kind if cost is not None else "unavailable",
        "recall_target": target, "random_seeds": seeds,
        "error_weights": weights, **score(ranked),
        "per_type": metrics.recall_by_type(ranked, errors, top_frac),
        "file_order": score(file_order), "random": random_summary,
    }
    return _finite(result)


def comparison(queue, answer, output_dir, *, split="test", top_frac=.2, cost=None, cost_kind=None):
    result = evaluate(queue, answer, split, top_frac, cost, cost_kind)
    ranked, file_order, errors = context(queue, answer, split, top_frac, cost)
    mass = metrics.error_mass(errors, answer["meta"].get("weights", metrics.DEFAULT_WEIGHTS))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    identity = {k: result[k] for k in ("split", "seed", "n_images", "data_kind", "top_frac")}
    rows = [{**identity, "method": result["model_version"], **{k: result[k] for k in result["file_order"]}},
            {**identity, "method": "file_order", **result["file_order"]},
            {**identity, "method": "random_mean", **{k: v["mean"] for k, v in result["random"].items()}},
            {**identity, "method": "random_std", **{k: v["std"] for k, v in result["random"].items()}}]
    pd.DataFrame(rows).to_csv(output/"comparison.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    for label, order in [(result["model_version"], ranked), ("File order", file_order),
                         ("Ideal (known answers)", sorted(file_order, key=lambda i: -mass.get(i, 0)))]:
        xs, ys = metrics.gain_curve(order, mass)
        ax.step(xs, ys, where="post", label=label)
    orders = list(metrics.random_orders(file_order, result["random_seeds"], result["seed"]))
    curves = np.array([metrics.gain_curve(o, mass)[1] for o in orders])
    xs = np.linspace(0, 1, len(ranked)+1)
    ax.plot(xs, curves.mean(axis=0), label=f"Random ({len(orders)} seeds)")
    ax.fill_between(xs, np.maximum(0, curves.mean(axis=0)-curves.std(axis=0)),
                    np.minimum(1, curves.mean(axis=0)+curves.std(axis=0)), alpha=.15)
    ax.axvline(top_frac, color="gray", linestyle=":")
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Fraction of images reviewed",
           ylabel="Fraction of weighted injected errors", title=f"Synthetic errors / {split}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output/"gain_curve.png", dpi=150)
    plt.close(fig)
    (output/"evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                   allow_nan=False)+"\n", encoding="utf-8")
    return result


def append_result(result: dict, path: Path) -> None:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "diff", "--binary"], capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, diff = "nogit", b""
    # Include uncommitted implementation files in a reproducible source fingerprint.
    digest = hashlib.sha256()
    for root in (config.ROOT/"src", config.CONFIG_DIR):
        for file in sorted(root.rglob("*")):
            if file.is_file() and file.suffix in {".py", ".yaml"}:
                digest.update(str(file.relative_to(config.ROOT)).encode())
                digest.update(file.read_bytes())
    row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "commit": commit,
           "working_tree_diff_sha256": hashlib.sha256(diff).hexdigest(),
           "source_sha256": digest.hexdigest(), **_finite(result)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
