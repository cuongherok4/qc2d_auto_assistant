"""Kiểm file được commit: không dữ liệu, không phiếu kiểm tay, không secret, không đường dẫn máy cá nhân.

Chạy: python .github/scripts/check_repo.py (từ gốc repo). Chỉ dùng thư viện chuẩn để CI chạy không cần cài gì.
Repo sẽ public: dữ liệu, phiếu, DB, mật khẩu gửi qua Drive (CONTRIBUTING.md).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
FORBIDDEN_DIRS = ("data/", "models/")
FORBIDDEN_EXT = {".parquet", ".pt", ".onnx", ".db", ".sqlite", ".sqlite3", ".zip", ".jpg", ".jpeg", ".mp4",
                 ".env", ".pem", ".key"}
# icon của Chrome extension là file ảnh duy nhất được commit
ALLOWED = re.compile(r"^extension/icon\d+\.png$")
FORBIDDEN_NAME = re.compile(r"(^|/)(\.env(\..*)?|phieu-[^/]*\.csv|manual-check[^/]*\.(csv|json))$")
SECRET = re.compile(
    r"AIza[0-9A-Za-z_-]{35}"            # Google / Gemini API key
    r"|gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{40,}"
    r"|sk-ant-[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{40,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
HOME_PATH = re.compile(r"(/home/|/Users/|[A-Z]:\\Users\\)[A-Za-z0-9_.-]+")
# compose gốc của CVAT dùng thư mục home của user django trong container, không phải máy cá nhân
HOME_PATH_SKIP = ("deployment/cvat/upstream/",)


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def check(path: str) -> list[str]:
    p = Path(path)
    if not p.is_file():  # submodule hoặc file đã xoá chưa commit
        return []
    errors = []
    if path.startswith(FORBIDDEN_DIRS):
        errors.append("nằm trong data/ hoặc models/")
    if not ALLOWED.match(path) and (p.suffix.lower() in FORBIDDEN_EXT or p.suffix.lower() == ".png"):
        errors.append(f"loại file {p.suffix} không được commit")
    if FORBIDDEN_NAME.search(path):
        errors.append("file môi trường hoặc phiếu/danh sách kiểm tay")
    size = p.stat().st_size
    if size > MAX_BYTES:
        errors.append(f"nặng {size / 1024 / 1024:.1f}MB > 2MB")
    raw = p.read_bytes()
    if b"\0" in raw[:8192]:  # file nhị phân: không quét nội dung
        return errors
    text = raw.decode("utf-8", errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        if SECRET.search(line):
            errors.append(f"dòng {n}: giống API key / token / private key")
        m = HOME_PATH.search(line)
        if m and not path.startswith(HOME_PATH_SKIP):
            errors.append(f"dòng {n}: đường dẫn máy cá nhân {m.group(0)}, dùng đường dẫn tương đối repo")
    return errors


def main() -> int:
    bad = {path: errs for path in tracked() if (errs := check(path))}
    for path, errs in bad.items():
        for e in errs:
            print(f"::error file={path}::{e}")
            print(f"{path}: {e}")
    if bad:
        print(f"\n{len(bad)} file không đạt. Dữ liệu, phiếu, DB, mật khẩu gửi qua Drive; xoá khỏi git bằng "
              "`git rm --cached <file>`.")
        return 1
    print("Repo sạch: không dữ liệu, phiếu kiểm tay, secret hay đường dẫn máy cá nhân.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
