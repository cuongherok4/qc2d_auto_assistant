"""Metric chuẩn cho hàng đợi review M13.

Quy ước đầu vào:
    ranked:  list image_id theo thứ tự hàng đợi (rank 1 trước). Phải chứa đủ mọi ảnh của split.
    errors:  list dict {"image_id", "type"} lấy từ injected_errors.json (đã lọc theo split).
    cost:    (tuỳ chọn) dict image_id -> thời gian review ước lượng (giây).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

DEFAULT_WEIGHTS = {"missing": 1.0, "wrong_class": 1.0, "spurious": 0.6, "shift": 0.3, "resize": 0.3}


def error_mass(errors, weights=DEFAULT_WEIGHTS, weighted=True) -> dict[str, float]:
    """image_id -> khối lượng lỗi (tổng trọng số, hoặc 1 nếu ảnh có lỗi khi weighted=False)."""
    mass: dict[str, float] = defaultdict(float)
    for e in errors:
        mass[e["image_id"]] += weights[e["type"]] if weighted else 1.0
    if not weighted:
        mass = defaultdict(float, {k: 1.0 for k in mass})
    return mass


def gain_curve(ranked, mass, cost=None) -> tuple[list[float], list[float]]:
    """Trả về (x, y): x = phần ảnh (hoặc thời gian) đã xem, y = phần lỗi đã bắt. Bắt đầu tại (0, 0)."""
    total = sum(mass.values())
    c = [cost[i] if cost else 1.0 for i in ranked]
    total_c = sum(c)
    xs, ys, acc_x, acc_y = [0.0], [0.0], 0.0, 0.0
    for img, ci in zip(ranked, c):
        acc_x += ci
        acc_y += mass.get(img, 0.0)
        xs.append(acc_x / total_c)
        ys.append(acc_y / total if total else 0.0)
    return xs, ys


def recall_at(ranked, mass, frac=0.2, cost=None) -> float:
    """Recall khi đã xem `frac` số ảnh (cost=None) hoặc `frac` tổng thời gian (có cost).

    Theo số ảnh: lấy đúng ceil(frac*N) ảnh đầu. Theo thời gian: chỉ tính ảnh xem trọn trong ngân sách.
    """
    total = sum(mass.values())
    if total == 0:
        return float("nan")
    if cost is None:
        k = math.ceil(frac * len(ranked))
        return sum(mass.get(i, 0.0) for i in ranked[:k]) / total
    budget = frac * sum(cost[i] for i in ranked)
    spent, got = 0.0, 0.0
    for i in ranked:
        spent += cost[i]
        if spent > budget + 1e-9:
            break
        got += mass.get(i, 0.0)
    return got / total


def precision_at(ranked, mass, frac=0.2) -> float:
    k = math.ceil(frac * len(ranked))
    return sum(1 for i in ranked[:k] if mass.get(i, 0) > 0) / k if k else float("nan")


def ndcg(ranked, mass) -> float:
    gains = [mass.get(i, 0.0) for i in ranked]
    dcg = sum(g / math.log2(r + 2) for r, g in enumerate(gains))
    idcg = sum(g / math.log2(r + 2) for r, g in enumerate(sorted(gains, reverse=True)))
    return dcg / idcg if idcg else float("nan")


def n_to_reach(ranked, mass, target=0.8) -> int:
    """Số ảnh phải xem theo thứ tự `ranked` để đạt recall `target`."""
    total = sum(mass.values())
    acc = 0.0
    for n, i in enumerate(ranked, 1):
        acc += mass.get(i, 0.0)
        if acc >= target * total - 1e-9:
            return n
    return len(ranked)


def random_orders(ids, n_seeds=20, base_seed=42):
    for s in range(n_seeds):
        order = list(ids)
        random.Random(base_seed + s).shuffle(order)
        yield order


def time_saved(ranked, mass, target=0.8, n_seeds=20) -> float:
    """1 − n_queue / mean(n_random) — định nghĩa đã chốt 07/10."""
    n_q = n_to_reach(ranked, mass, target)
    n_r = [n_to_reach(o, mass, target) for o in random_orders(ranked, n_seeds)]
    return 1 - n_q / (sum(n_r) / len(n_r))


def recall_by_type(ranked, errors, frac=0.2) -> dict[str, float]:
    top = set(ranked[: math.ceil(frac * len(ranked))])
    hit, tot = defaultdict(int), defaultdict(int)
    for e in errors:
        tot[e["type"]] += 1
        hit[e["type"]] += e["image_id"] in top
    return {t: hit[t] / tot[t] for t in tot}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy 95% cho tỉ lệ k/n (dùng cho kiểm ngẫu nhiên phần đuôi)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


if __name__ == "__main__":
    ids = [f"img{i:02d}" for i in range(10)]
    errs = [{"image_id": "img00", "type": "missing"}, {"image_id": "img01", "type": "shift"},
            {"image_id": "img09", "type": "missing"}]
    m = error_mass(errs)
    assert math.isclose(recall_at(ids, m, 0.2), 1.3 / 2.3)
    assert math.isclose(recall_at(ids, error_mass(errs, weighted=False), 0.2), 2 / 3)
    cost = {i: 1.0 for i in ids} | {"img00": 3.0}
    assert recall_at(ids, m, 0.2, cost) == 0.0  # ngân sách 2.4s, img00 tốn 3s
    assert math.isclose(recall_at(ids, m, 0.25, cost), 1.0 / 2.3)  # 3s: vừa đủ img00
    assert n_to_reach(ids, m, 0.8) == 10
    perfect = ["img00", "img09", "img01"] + ids[2:9]
    assert n_to_reach(perfect, m, 0.8) == 2 and math.isclose(ndcg(perfect, m), 1.0)
    assert time_saved(perfect, m) > 0
    assert recall_by_type(ids, errs) == {"missing": 0.5, "shift": 1.0}
    lo, hi = wilson(2, 100)
    assert 0 < lo < 0.02 < hi < 0.08
    print("metrics OK")
