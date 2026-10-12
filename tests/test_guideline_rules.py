import warnings

import pytest
import yaml

from src import config
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
