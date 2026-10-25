"""P2 hygiene: dependency/licence manifest per source repo tests.

``scripts.import_reference._write_licence_manifest`` writes one JSON file per
source repo recording name, URL, commit SHA, licence, rights note, import
batch, run_id, and the Plus project's Python dependencies (from
pyproject.toml).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.import_reference import _write_licence_manifest, sign_manifest


@pytest.fixture(autouse=True)
def _no_signing_key(monkeypatch):
    monkeypatch.delenv("PLUS_MANIFEST_SIGNING_KEY", raising=False)


def _source_repos():
    return [
        {
            "name": "11plus-prep",
            "repo_url": "https://github.com/SahirVhora/11plus-prep",
            "commit_sha": "d970c16614c95140dc946bd3f8f320aeef4a69f3",
            "licence": "MIT License, Copyright (c) 2026 Sahir Vhora",
            "rights_note": "MIT License, Copyright (c) 2026 Sahir Vhora",
            "batch": "prep-d970c16",
        },
        {
            "name": "11plus-tutor",
            "repo_url": "https://github.com/jhammant/11plus-tutor",
            "commit_sha": "",
            "licence": "see source repository",
            "rights_note": "see source repository",
            "batch": "tutor-001",
        },
    ]


def test_write_licence_manifest_creates_one_file_per_repo(tmp_path):
    repos = _source_repos()
    _write_licence_manifest(tmp_path, repos, run_id="run-123")

    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 2
    assert any("11plus-prep" in f for f in files)
    assert any("11plus-tutor" in f for f in files)
    assert all("run-123" in f for f in files)


def test_write_licence_manifest_payload_fields(tmp_path):
    repos = _source_repos()
    _write_licence_manifest(tmp_path, repos, run_id="run-abc")

    prep_file = next(p for p in tmp_path.iterdir() if "11plus-prep" in p.name)
    payload = json.loads(prep_file.read_text(encoding="utf-8"))

    assert payload["source_repo"] == "11plus-prep"
    assert payload["source_url"] == "https://github.com/SahirVhora/11plus-prep"
    assert payload["source_commit_sha"] == (
        "d970c16614c95140dc946bd3f8f320aeef4a69f3")
    assert "MIT License" in payload["licence"]
    assert payload["import_batch"] == "prep-d970c16"
    assert payload["run_id"] == "run-abc"
    assert "generated_at_utc" in payload
    assert "project_dependencies" in payload
    assert payload["project_license"] == "MIT"
    # pyproject.toml deps should be present.
    assert any("fastapi" in d for d in payload["project_dependencies"])
    assert any("sqlalchemy" in d for d in payload["project_dependencies"])


def test_write_licence_manifest_unsigned_without_key(tmp_path):
    repos = _source_repos()
    _write_licence_manifest(tmp_path, repos, run_id="run-unsigned")

    payload = json.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
    assert "signature" not in payload


def test_write_licence_manifest_signed_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "licence-sign-key")
    repos = _source_repos()
    _write_licence_manifest(tmp_path, repos, run_id="run-signed")

    payload = json.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
    assert "signature" in payload
    assert len(payload["signature"]) == 64

    # Verify the signature round-trips.
    from scripts.import_reference import verify_manifest
    assert verify_manifest(next(tmp_path.iterdir())) is True


def test_write_licence_manifest_empty_repos(tmp_path):
    _write_licence_manifest(tmp_path, [], run_id="run-empty")
    assert list(tmp_path.iterdir()) == []