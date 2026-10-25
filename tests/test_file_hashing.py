from src.core.hashing import content_fingerprint, sha256_bytes, sha256_text


def test_sha256_text_stable():
    assert sha256_text("hello") == sha256_text("hello")
    assert sha256_text("hello") != sha256_text("world")


def test_sha256_bytes():
    assert len(sha256_bytes(b"abc")) == 64


def test_fingerprint_normalises_case_and_space():
    assert content_fingerprint("  Hello ", "B") == content_fingerprint("hello", "b")
