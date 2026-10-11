"""Hàm hình học dùng chung cho tín hiệu QC: IoU, clip, khớp nhãn với dự đoán.

Box là mảng (N, 4) dạng [x1, y1, x2, y2] pixel.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

IMG_W, IMG_H = 1280, 720


def clip_boxes(boxes: np.ndarray, w: int = IMG_W, h: int = IMG_H) -> np.ndarray:
    b = np.asarray(boxes, dtype=float).reshape(-1, 4).copy()
    b[:, [0, 2]] = b[:, [0, 2]].clip(0, w)
    b[:, [1, 3]] = b[:, [1, 3]].clip(0, h)
    return b


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU giữa mọi cặp box của a (N,4) và b (M,4) → (N, M)."""
    a = np.asarray(a, dtype=float).reshape(-1, 4)
    b = np.asarray(b, dtype=float).reshape(-1, 4)
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    ix1 = np.maximum(a[:, None, 0], b[None, :, 0])
    iy1 = np.maximum(a[:, None, 1], b[None, :, 1])
    ix2 = np.minimum(a[:, None, 2], b[None, :, 2])
    iy2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = (ix2 - ix1).clip(0) * (iy2 - iy1).clip(0)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)


def match_boxes(labels: np.ndarray, preds: np.ndarray, min_iou: float = 0.5):
    """Khớp 1-1 bằng Hungarian trên 1−IoU.

    Trả về (pairs, unmatched_labels, unmatched_preds); pairs là list (i_label, j_pred, iou).
    Cặp có IoU < min_iou bị coi là không khớp.
    """
    iou = iou_matrix(labels, preds)
    n, m = iou.shape
    if n == 0 or m == 0:
        return [], list(range(n)), list(range(m))
    rows, cols = linear_sum_assignment(1.0 - iou)
    pairs = [
        (int(i), int(j), float(iou[i, j]))
        for i, j in zip(rows, cols, strict=True)
        if iou[i, j] >= min_iou
    ]
    ml = {i for i, _, _ in pairs}
    mp = {j for _, j, _ in pairs}
    return pairs, [i for i in range(n) if i not in ml], [j for j in range(m) if j not in mp]


def touches_edge(boxes: np.ndarray, margin: float = 2.0, w: int = IMG_W, h: int = IMG_H) -> np.ndarray:
    b = np.asarray(boxes, dtype=float).reshape(-1, 4)
    return (b[:, 0] <= margin) | (b[:, 1] <= margin) | (b[:, 2] >= w - margin) | (b[:, 3] >= h - margin)


def robust_z(x: np.ndarray) -> np.ndarray:
    """z-score dùng median/MAD (ít bị chính các box lỗi kéo lệch)."""
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    return (x - med) / mad if mad > 0 else np.zeros_like(x)

