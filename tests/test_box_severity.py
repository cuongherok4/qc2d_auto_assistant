from src.api.box_severity import annotate

POLICY = {"error_signals": ["guideline"],
          "error_conf_signals": ["model_missing_label", "model_class_conflict"], "error_conf": 0.85}


def _box(obj_id, note, signal):
    return {"obj_id": obj_id, "box": [0, 0, 10, 10], "note": note, "signal": signal}


def test_missing_label_uses_model_conf():
    out = annotate([_box(None, "model: car 0.94", "model_missing_label"),
                    _box(None, "model: car 0.70", "model_missing_label")], POLICY)
    assert [b["severity"] for b in out] == ["error", "review"]


def test_class_conflict_pair_shares_model_conf():
    out = annotate([_box("26", "nhãn: bus", "model_class_conflict"),
                    _box(None, "model: truck 0.90", "model_class_conflict")], POLICY)
    assert [b["severity"] for b in out] == ["error", "error"]


def test_loose_box_and_unsupported_stay_review():
    out = annotate([_box("48", "nhãn", "model_loose_box"), _box(None, "model: car 0.99", "model_loose_box"),
                    _box("50", "không có dự đoán", "label_unsupported")], POLICY)
    assert {b["severity"] for b in out} == {"review"}


def test_guideline_always_error_and_input_not_mutated():
    boxes = [_box("3", "[R1] box cao 8px < 10px", "guideline")]
    assert annotate(boxes, POLICY)[0]["severity"] == "error"
    assert "severity" not in boxes[0]


def test_empty_policy_marks_everything_review():
    assert annotate([_box(None, "model: car 0.99", "model_missing_label")], {})[0]["severity"] == "review"


def test_image_detail_schema_keeps_severity():
    from src.api.schemas import Evidence

    assert Evidence(box=[0, 0, 1, 1], severity="error").model_dump()["severity"] == "error"
