"""Bước 4 (bậc 3) + bước 6 · GBM và vòng học lại. Phụ trách: Cường. Hướng dẫn: skill `risk-scoring`.

Train trên split train, early stopping trên val, báo số trên test. Tham số ở configs/learning.yaml mục `gbm`.
Đặc trưng = value của mọi tín hiệu + đặc trưng phụ (số box, số vật model thấy, đêm/thời tiết).
Nhãn học: ảnh có lỗi (giai đoạn phát triển: lỗi tiêm; giai đoạn thật: verdict "lỗi thật").
risk_score = 100 * xác suất ảnh có lỗi. Lý do hiện cho reviewer vẫn là `reason` của tín hiệu,
xếp theo đóng góp (pred_contrib) của tín hiệu đó vào điểm của chính ảnh.
Dùng API gốc của LightGBM (không cần scikit-learn). Model lưu ở models/ (không commit).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src import config
from src.contracts import QUEUE_COLS, REASON_SEP
from src.data import bdd100k
from src.pipeline import portable

EXTRA = ["n_boxes", "n_tiny", "n_pred_0.3", "n_pred_0.5", "n_pred_0.7", "pred_minus_label",
         "night", "bad_weather"]


def extra_features(frames, preds: pd.DataFrame | None) -> pd.DataFrame:
    objects, images = bdd100k.to_tables(frames)
    ids = images["image_id"]
    out = pd.DataFrame(index=pd.Index(ids, name="image_id"))
    out["n_boxes"] = images.set_index("image_id")["n_boxes"]
    out["n_tiny"] = objects[objects["h"] < 20].groupby("image_id").size().reindex(ids, fill_value=0).values
    for c in (0.3, 0.5, 0.7):
        hit = preds[preds["conf"] >= c] if preds is not None else pd.DataFrame(columns=["image_id"])
        out[f"n_pred_{c}"] = hit.groupby("image_id").size().reindex(ids, fill_value=0).values
    out["pred_minus_label"] = out["n_pred_0.5"] - out["n_boxes"]
    out["night"] = (images["timeofday"] == "night").astype(int).values
    out["bad_weather"] = images["weather"].isin(["rainy", "snowy", "foggy"]).astype(int).values
    return out.astype(float)


def target_from_answer(answer: dict, ids) -> tuple[pd.Series, pd.Series]:
    """(y: ảnh có lỗi 0/1, split của từng ảnh). Test giữ trong split nhưng không bao giờ dùng để train."""
    split = pd.Series(answer["splits"]).reindex(ids)
    if split.isna().any():
        raise ValueError("Đáp án thiếu split cho một số ảnh")
    bad = {e["image_id"] for e in answer["errors"]}
    return pd.Series([int(i in bad) for i in ids], index=ids, dtype=float), split


def _params(cfg: dict) -> tuple[dict, int, int]:
    cfg = dict(cfg)
    rounds, stop = cfg.pop("n_estimators", 500), cfg.pop("early_stopping_rounds", 50)
    seed = cfg.pop("seed", 42)
    return {"objective": "binary", "verbose": -1, "deterministic": True, "num_threads": 4,
            "seed": seed, **cfg}, rounds, stop


def train(features: pd.DataFrame, target: pd.Series, cfg: dict, train_ids, val_ids):
    """LightGBM, early stopping trên val. Trả (booster, info)."""
    import lightgbm as lgb

    params, rounds, stop = _params(cfg)
    dtr = lgb.Dataset(features.loc[train_ids], target.loc[train_ids])
    dva = lgb.Dataset(features.loc[val_ids], target.loc[val_ids], reference=dtr)
    booster = lgb.train(params, dtr, rounds, valid_sets=[dva],
                        callbacks=[lgb.early_stopping(stop, verbose=False)])
    info = {"params": params, "best_iteration": booster.best_iteration, "n_train": len(train_ids),
            "n_val": len(val_ids), "train_positive": int(target.loc[train_ids].sum()),
            "val_logloss": float(booster.best_score["valid_0"]["binary_logloss"])}
    return booster, info


def recall_at(score: pd.Series, mass: pd.Series, top_frac: float = 0.2) -> float:
    """Phần khối lượng lỗi nằm trong top_frac ảnh điểm cao nhất (hoà điểm xếp theo image_id)."""
    order = pd.DataFrame({"s": score, "id": score.index}).sort_values(["s", "id"], ascending=[False, True])
    top = set(order["id"].iloc[:int(round(top_frac * len(order)))])
    total = mass.loc[score.index].sum()
    return float(mass.loc[[i for i in score.index if i in top]].sum() / total) if total > 0 else 0.0


def retrain_gate(new_model, old_model, holdout, max_drop: float = 0.005) -> bool:
    """Model mới chỉ được thay khi recall20 trên holdout cố định không tệ hơn model cũ quá max_drop.
    new_model/old_model: hàm features -> điểm; holdout: (features, khối lượng lỗi theo ảnh)."""
    features, mass = holdout
    new = recall_at(pd.Series(new_model(features), index=features.index), mass)
    old = recall_at(pd.Series(old_model(features), index=features.index), mass)
    return new >= old - max_drop


def queue_from_scores(prob: pd.Series, contrib: pd.DataFrame, signals: dict, version: str,
                      top_k: int = 3) -> pd.DataFrame:
    rows = []
    for img, p in prob.items():
        ranked = sorted(((contrib.at[img, n], s[img].reason) for n, s in signals.items()
                         if s[img].value > 0 and s[img].reason), key=lambda x: -x[0])
        reasons = [r for c, r in ranked if c > 0][:top_k] or [r for _, r in ranked][:top_k]
        rows.append({"image_id": img, "p": p, "risk_score": round(100 * float(p), 2),
                     "top_reasons": REASON_SEP.join(reasons)})
    df = pd.DataFrame(rows).sort_values(["p", "image_id"], ascending=[False, True])
    df["rank"] = range(1, len(df) + 1)
    df["model_version"] = version
    return df[QUEUE_COLS].reset_index(drop=True)


class Scorer:
    """Scorer cho pipeline.publish: học từ đáp án (split train/val), chấm mọi ảnh, lưu model."""

    def __init__(self, answer: dict, cfg: dict | None = None, models_dir: Path | None = None):
        self.answer = answer
        self.cfg = cfg if cfg is not None else config.load("learning")["gbm"]
        self.models_dir = Path(models_dir or config.path("models_dir"))

    def __call__(self, signals, features, frames, preds, version):
        X = features.join(extra_features(frames, preds), how="left")
        X = X[sorted(X.columns)]
        y, split = target_from_answer(self.answer, X.index)
        tr, va = split.index[split == "train"], split.index[split == "val"]
        if not len(tr) or not len(va) or y.loc[tr].nunique() < 2:
            raise ValueError("GBM cần split train (có cả ảnh lỗi và không lỗi) và val")
        booster, info = train(X, y, self.cfg, tr, va)
        it = booster.best_iteration
        prob = pd.Series(booster.predict(X, num_iteration=it), index=X.index)
        contrib = pd.DataFrame(booster.predict(X, num_iteration=it, pred_contrib=True)[:, :-1],
                               index=X.index, columns=X.columns)
        queue = queue_from_scores(prob, contrib, signals, version,
                                  config.load("weights").get("top_reasons", 3))
        self.models_dir.mkdir(parents=True, exist_ok=True)
        model_file = self.models_dir / f"gbm_{version}.txt"
        if model_file.exists():
            raise ValueError(f"{model_file} đã có; chọn --version mới")
        booster.save_model(str(model_file), num_iteration=it)
        gain = booster.feature_importance("gain", iteration=it)
        importance = {c: round(float(g), 2) for c, g in sorted(zip(X.columns, gain, strict=True),
                                                                key=lambda x: -x[1])}
        mass_types = config.load("injection")["types"]
        mass = pd.Series(0.0, index=X.index)
        for e in self.answer["errors"]:
            mass[e["image_id"]] += mass_types.get(e["type"], 1.0)
        return queue, {"method": "gbm", **info, "features": list(X.columns), "importance": importance,
                       "val_recall20_weighted": round(recall_at(prob.loc[va], mass), 4),
                       "model_file": portable(model_file),
                       "model_sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(),
                       "answer_sha256": hashlib.sha256(json.dumps(
                           self.answer, sort_keys=True).encode()).hexdigest(),
                       "trained_on": "train split; early stopping trên val; test không dùng"}
