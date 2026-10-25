from src.pipeline.ingest import unpack_zip_bytes


def test_zip_unpack_deterministic(tmp_path):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("b.txt", "B")
        zf.writestr("a.txt", "A")
    names = unpack_zip_bytes(buf.getvalue(), tmp_path)
    assert names == ["a.txt", "b.txt"]
    assert (tmp_path / "a.txt").read_text() == "A"
