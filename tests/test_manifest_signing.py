"""P2 hygiene: manifest signing (HMAC-SHA256) tests.

Manifests written by ``scripts.import_reference._write_manifests`` are
HMAC-signed when ``PLUS_MANIFEST_SIGNING_KEY`` is set. Signatures are
reproducible, tamper-evident, and verifiable with ``verify_manifest``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.import_reference import (
    sign_manifest, verify_manifest, _manifest_signing_key,
)


@pytest.fixture(autouse=True)
def _no_signing_key(monkeypatch):
    """Ensure tests run without a signing key unless explicitly set."""
    monkeypatch.delenv("PLUS_MANIFEST_SIGNING_KEY", raising=False)


def test_sign_manifest_without_key_returns_empty():
    """No key configured -> empty signature (unsigned manifest)."""
    assert sign_manifest({"a": 1}) == ""
    assert sign_manifest({"a": 1}, None) == ""


def test_sign_manifest_with_key_is_deterministic():
    """Same payload + same key -> same signature; different payloads differ."""
    key = "test-signing-key-12345"
    payload = {"run_id": "run-1", "repo": "11plus-prep", "totals": {"records": 5}}
    sig1 = sign_manifest(dict(payload), key)
    sig2 = sign_manifest(dict(payload), key)
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA-256 hex

    payload2 = dict(payload, totals={"records": 6})
    assert sign_manifest(payload2, key) != sig1


def test_sign_manifest_key_order_independence():
    """Signature over canonical JSON: key order does not matter."""
    key = "k"
    a = sign_manifest({"b": 2, "a": 1}, key)
    b = sign_manifest({"a": 1, "b": 2}, key)
    assert a == b


def test_verify_manifest_roundtrip(tmp_path, monkeypatch):
    """Write a signed manifest, then verify it round-trips."""
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "roundtrip-key")
    payload = {"run_id": "run-rt", "repo": "11plus-prep",
               "totals": {"records": 3}}
    sig = sign_manifest(payload)
    payload["signature"] = sig
    path = tmp_path / "11plus-prep-abc123-runrt.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert verify_manifest(path) is True


def test_verify_manifest_tampering_detected(tmp_path, monkeypatch):
    """Changing any field after signing makes verification fail."""
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "tamper-key")
    payload = {"run_id": "run-t", "repo": "11plus-prep",
               "totals": {"records": 3}}
    sig = sign_manifest(payload)
    payload["signature"] = sig
    path = tmp_path / "11plus-prep-abc123-runrt.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert verify_manifest(path) is True

    # Tamper with a payload field.
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["totals"]["records"] = 999
    path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    assert verify_manifest(path) is False


def test_verify_manifest_wrong_key_fails(tmp_path, monkeypatch):
    """A signature made with key A cannot be verified with key B."""
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "key-b")
    payload = {"run_id": "run-w", "repo": "11plus-prep",
               "totals": {"records": 1}}
    sig_a = sign_manifest(payload, "key-a")
    payload["signature"] = sig_a
    path = tmp_path / "11plus-prep-abc123-runw.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert verify_manifest(path) is False


def test_verify_manifest_missing_file_returns_false(tmp_path):
    """Non-existent manifest path -> False."""
    assert verify_manifest(tmp_path / "does-not-exist.json") is False


def test_verify_manifest_unparseable_returns_false(tmp_path):
    """Garbage content -> False."""
    path = tmp_path / "bad.json"
    path.write_text("not json {{{", encoding="utf-8")
    assert verify_manifest(path) is False


def test_verify_manifest_unsigned_when_no_key(tmp_path):
    """No signing key configured: a manifest without signature is valid."""
    path = tmp_path / "unsigned.json"
    path.write_text(json.dumps({"run_id": "run-u"}), encoding="utf-8")
    assert verify_manifest(path) is True


def test_verify_manifest_unsigned_when_key_required_fails(tmp_path, monkeypatch):
    """Signing key configured but manifest has no signature -> False."""
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "req-key")
    path = tmp_path / "unsigned-req.json"
    path.write_text(json.dumps({"run_id": "run-ur"}), encoding="utf-8")
    assert verify_manifest(path) is False


def test_manifest_signing_key_env_var(monkeypatch):
    """_manifest_signing_key reads PLUS_MANIFEST_SIGNING_KEY from env."""
    assert _manifest_signing_key() is None
    monkeypatch.setenv("PLUS_MANIFEST_SIGNING_KEY", "env-key")
    assert _manifest_signing_key() == "env-key"