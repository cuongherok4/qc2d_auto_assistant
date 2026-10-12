import warnings

import pytest
import yaml

from src import config
from src.data import bdd100k
from src.features import guideline_rules as gr

SPEC = {
    "id": "toy", "version": "1.2.0", "approved_by": "Cường",
    "classes": ["car", "truck"], "min_height_px": {"default": 15},
    "rules": [{"id": "R1", "check": "below_min_height", "severity": 0.6, "message": "cao {h}px"}],
}


@pytest.fixture
def gdir(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "GUIDELINE_DIR", tmp_path)
    (tmp_path / "drafts").mkdir()
    return tmp_path


def write(d, spec, name=None):
    (d / f"{name or spec['id']}.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")


def test_load_approved_spec(gdir):
    write(gdir, SPEC)
    spec = gr.load_spec("toy@1.2.0")
    assert spec["min_height_px"]["default"] == 15
    assert spec["merge"] == {} and spec["unclear"] == []


def test_rejects_unapproved_spec(gdir):
    write(gdir, {**SPEC, "approved_by": ""})
    with pytest.raises(gr.UnapprovedSpecError):
        gr.load_spec("toy@1.2.0")
    with pytest.warns(UserWarning, match="chưa được duyệt"):
        assert gr.load_spec("toy@1.2.0", allow_unapproved=True)["id"] == "toy"


@pytest.mark.parametrize("ref", ["toy", "toy@", "@1.2.0"])
def test_rejects_bad_ref(gdir, ref):
    with pytest.raises(ValueError, match="<id>@<version>"):
        gr.load_spec(ref)


def test_rejects_wrong_version(gdir):
    write(gdir, SPEC)
    with pytest.raises(ValueError, match="version 1.2.0"):
        gr.load_spec("toy@1.0.0")


def test_rejects_id_mismatch_missing_keys_and_dup_rules(gdir):
    write(gdir, {**SPEC, "id": "other"}, name="toy")
    with pytest.raises(ValueError, match="id trong file"):
        gr.load_spec("toy@1.2.0")
    write(gdir, {k: v for k, v in SPEC.items() if k != "classes"})
    with pytest.raises(ValueError, match="thiếu khoá"):
        gr.load_spec("toy@1.2.0")
    write(gdir, {**SPEC, "rules": SPEC["rules"] * 2})
    with pytest.raises(ValueError, match="trùng"):
        gr.load_spec("toy@1.2.0")


def test_missing_spec_points_to_draft(gdir):
    write(gdir / "drafts", SPEC)
    with pytest.raises(FileNotFoundError, match="drafts"):
        gr.load_spec("toy@1.2.0")


def test_spec_for_batch(gdir, monkeypatch):
    write(gdir, SPEC)
    monkeypatch.setattr(config, "load", lambda name: {"b1": "toy@1.2.0", "b_off": None})
    assert gr.spec_for_batch("b1")["id"] == "toy"
    assert gr.spec_for_batch("b_off") is None
    with pytest.raises(KeyError):
        gr.spec_for_batch("b_missing")


def test_repo_bdd_default_spec_is_valid():
    """Spec thật trong configs/guidelines/: đúng cấu trúc, khớp batches.yaml (duyệt hay chưa đều qua)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = gr.load_spec(config.load("batches")["batch_01"], allow_unapproved=True)
    assert spec["id"] == "bdd-default"
    assert {r["id"] for r in spec["rules"]} >= {"R1", "R2", "R3"}


# --- R1: below_min_height ---

R1 = {"id": "R1", "check": "below_min_height", "severity": 0.6,
      "message": "Box {category} cao {h:.0f}px, dưới ngưỡng {thr}px của guideline"}


def r1_spec(min_height_px, **extra):
    return {"id": "toy", "rules": [R1], "min_height_px": min_height_px, "near_threshold_px": 3, **extra}


def tables(boxes: dict[str, list[tuple]], empty: tuple[str, ...] = ()):
    """boxes: {image_id: [(category, h), ...]} -> (objects, images); box rộng 40px, đặt giữa ảnh."""
    frames = [{"name": f"{img}.jpg", "labels": [
        {"id": str(i), "category": c, "box2d": {"x1": 600.0, "y1": 300.0, "x2": 640.0, "y2": 300.0 + h}}
        for i, (c, h) in enumerate(bs, 1)]} for img, bs in boxes.items()]
    frames += [{"name": f"{img}.jpg", "labels": None} for img in empty]
    return bdd100k.to_tables(frames)


@pytest.mark.parametrize(("thr", "expected"), [(30, "lỗi"), (15, "không lỗi"), (20, "sát ngưỡng")])
def test_r1_box_18px_against_threshold(thr, expected):
    objects, images = tables({"a": [("car", 18.0)]})
    r = gr.guideline(objects, images, r1_spec({"default": thr}))["a"]
    if expected == "lỗi":
        assert r.value == pytest.approx(0.6)
        assert r.reason == f"[R1] Box car cao 18px, dưới ngưỡng {thr}px của guideline"
    elif expected == "không lỗi":
        assert r.value == 0 and r.reason == ""
    else:
        assert r.value == pytest.approx(0.6 * gr.NEAR_FACTOR)
        assert r.reason.startswith("[R1]") and "sát ngưỡng 20px" in r.reason


def test_r1_threshold_per_class_overrides_default():
    objects, images = tables({"a": [("car", 18.0)], "b": [("traffic light", 18.0)]})
    out = gr.guideline(objects, images, r1_spec({"default": 0, "traffic light": 30}))
    assert out["a"].value == 0
    assert out["b"].value == pytest.approx(0.6)


def test_r1_merge_applied_before_threshold():
    objects, images = tables({"a": [("bus", 18.0)]})
    spec = r1_spec({"default": 0, "truck": 30}, merge={"bus": "truck"})
    r = gr.guideline(objects, images, spec)["a"]
    assert r.value == pytest.approx(0.6)
    assert "truck" in r.reason


def test_r1_combines_violations_and_cites_page():
    objects, images = tables({"a": [("car", 10.0), ("car", 12.0), ("car", 50.0)]}, empty=("empty",))
    spec = r1_spec({"default": 30}, rules=[{**R1, "page": 3}])
    out = gr.guideline(objects, images, spec)
    assert set(out) == {"a", "empty"}
    assert out["a"].value == pytest.approx(1 - 0.4 * 0.4)
    assert out["a"].reason.endswith("(tr.3) (+1 vi phạm khác)")
    assert [e["obj_id"] for e in out["a"].evidence] == ["1", "2"]
    assert out["empty"].value == 0


def test_unregistered_check_is_skipped_with_warning():
    objects, images = tables({"a": [("car", 10.0)]})
    spec = r1_spec({"default": 30}, rules=[R1, {"id": "R9", "check": "not_written_yet", "severity": 1.0}])
    with pytest.warns(UserWarning, match="R9"):
        out = gr.guideline(objects, images, spec)
    assert out["a"].value == pytest.approx(0.6)


def test_bdd_default_has_no_height_violation():
    """Guideline gốc BDD không đặt ngưỡng chiều cao (default 0): R1 không báo box nào."""
    objects, images = tables({"a": [("car", 2.0), ("traffic sign", 5.0)]})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = gr.load_spec("bdd-default@1.0.0", allow_unapproved=True)
        assert gr.guideline(objects, images, spec)["a"].value == 0
