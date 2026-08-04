"""Tests for registry sync env wiring (no network)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import model_registry_sync as mrs


def test_sync_skipped_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MODEL_REGISTRY_SYNC", raising=False)
    assert mrs.sync_active_models(weights_dir=tmp_path) == {}


def test_sync_applies_detector_and_ppe(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MODEL_REGISTRY_SYNC", "true")
    monkeypatch.delenv("ONNX_MODEL", raising=False)
    monkeypatch.delenv("YOLO_MODEL", raising=False)
    monkeypatch.delenv("VISIONOPS_PPE_MODEL", raising=False)
    monkeypatch.delenv("USE_ONNX", raising=False)

    active = {
        "detector": {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "yolov8n",
            "version": "2.0.0",
            "format": "onnx",
            "filename": "det.onnx",
        },
        "ppe": {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "hardhat",
            "version": "1.0.0",
            "format": "pytorch",
            "filename": "ppe.pt",
        },
    }

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/models/active"):
            resp.json.return_value = active
            return resp
        if "11111111" in url:
            resp.content = b"ONNX"
            return resp
        if "22222222" in url:
            resp.content = b"PPE"
            return resp
        raise AssertionError(url)

    with patch.object(mrs.requests, "get", side_effect=fake_get):
        resolved = mrs.sync_active_models(
            api_url="http://api.test",
            api_key="k",
            weights_dir=tmp_path,
        )

    assert "detector" in resolved and "ppe" in resolved
    assert resolved["detector"].read_bytes() == b"ONNX"
    assert resolved["ppe"].read_bytes() == b"PPE"
    assert os.environ["ONNX_MODEL"] == str(resolved["detector"])
    assert os.environ["USE_ONNX"] == "true"
    assert os.environ["VISIONOPS_PPE_MODEL"] == str(resolved["ppe"])
