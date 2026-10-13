"""Per-machine checks never count instructions as an installation."""

from contextlib import nullcontext

import pandas as pd
from test_recheck import setup_recheck as setup_recheck

from src.api import operations
from src.api.saved_labels import SavedLabels
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore


def test_doctor_verifies_each_mapping_with_cvat_metadata(setup_recheck, monkeypatch):
    settings, _, _, cvat, _ = setup_recheck
    monkeypatch.setattr(Settings, "configured", lambda: settings)
    monkeypatch.setattr(operations.socket, "create_connection", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(operations, "SavedLabels", lambda cfg, service: SavedLabels(cfg, service, cvat))
    report = operations.doctor(verify_cvat=True)
    assert report["machine"]["system"]
    assert report["mapping"]["cvat_readonly"]["checked_images"] == 2
    assert report["mapping"]["cvat_readonly"]["errors"] == []


def test_mapping_refuses_two_images_on_same_task_job_frame(setup_recheck):
    settings, _, _, _, _ = setup_recheck
    frame = pd.read_parquet(settings.mapping)
    frame.loc[1, "frame"] = frame.loc[0, "frame"]
    frame.to_parquet(settings.mapping)
    mapping, warnings = QueueService(settings, ReviewStore(settings.database)).mapping()
    assert mapping == {} and "task/job/frame" in warnings[0]
