"""Chọn mẫu kiểm tay lỗi thật (docs/phan-tich-va-phan-cong-13-10.md): n_random ảnh ngẫu nhiên toàn batch
+ n_top ảnh đầu hàng đợi không trùng. Queue phải chấm trên NHÃN GỐC, không phải nhãn đã tiêm lỗi.

Ghi hai file:
- `<name>.csv`: danh sách cho người kiểm (check_order, image_id), đã trộn thứ tự và KHÔNG có nhóm/điểm/lý do,
  để người kiểm không biết ảnh nào do tool chọn (tránh thiên lệch).
- `<name>.key.json`: nhóm của từng ảnh, seed, sha256 của queue. Chỉ mở khi đối chiếu kết quả.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from src import contracts


def sample(queue_file: Path, out_dir: Path, name: str, *, n_random: int = 75, n_top: int = 75,
           seed: int = 42) -> dict:
    queue_file, out_dir = Path(queue_file), Path(out_dir)
    queue = pd.read_csv(queue_file, dtype={"image_id": str, "model_version": str}).fillna({"top_reasons": ""})
    errors = contracts.check_queue(queue)
    if errors:
        raise ValueError(f"Queue không hợp lệ: {errors}")
    if n_random + n_top > len(queue):
        raise ValueError("Queue ít ảnh hơn cỡ mẫu")
    files = {"list": out_dir / f"{name}.csv", "key": out_dir / f"{name}.key.json"}
    if any(f.exists() for f in files.values()):
        raise ValueError("Mẫu đã tồn tại; chọn tên khác, không ghi đè mẫu đã phát cho người kiểm")
    rng = random.Random(seed)
    ids = sorted(queue.image_id)
    rand = rng.sample(ids, n_random)
    taken = set(rand)
    top = [i for i in queue.sort_values("rank").image_id if i not in taken][:n_top]
    group = {**{i: "random" for i in rand}, **{i: "top" for i in top}}
    order = list(group)
    rng.shuffle(order)
    out_dir.mkdir(parents=True, exist_ok=True)
    listed = pd.DataFrame({"check_order": range(1, len(order) + 1), "image_id": order})
    listed.to_csv(files["list"], index=False)
    rank = dict(zip(queue.image_id, queue["rank"], strict=True))
    key = {"name": name, "seed": seed, "n_random": n_random, "n_top": n_top,
           "queue_file": queue_file.name,
           "queue_sha256": hashlib.sha256(queue_file.read_bytes()).hexdigest(),
           "model_version": str(queue.model_version.iloc[0]),
           "rule": ("random: random.Random(seed).sample(sorted image_id); "
                    "top: rank nhỏ nhất, bỏ ảnh đã ở random"),
           "images": [{"check_order": k + 1, "image_id": i, "group": group[i], "rank": int(rank[i])}
                      for k, i in enumerate(order)]}
    files["key"].write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in files.items()}
