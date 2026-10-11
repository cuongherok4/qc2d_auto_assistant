"""Bước 4 (bậc 3) + bước 6 · GBM và vòng học lại. Phụ trách: Cường. Hướng dẫn: skill `risk-scoring`.

Train trên split train, chọn tham số trên val, báo số trên test. Tham số ở configs/learning.yaml.
Học lại theo đợt, có ảnh audit và cổng kiểm tra trước khi thay model.
"""

from __future__ import annotations


def train(features, target, cfg: dict):
    raise NotImplementedError("TODO(Cường): LightGBM, early stopping trên val")


def retrain_gate(new_model, old_model, holdout) -> bool:
    raise NotImplementedError("TODO(Cường): model mới không tệ hơn model cũ theo recall20_weighted")
