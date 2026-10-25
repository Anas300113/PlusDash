from src.canonical.validators import validate_rights_status


def test_rights_values():
    for s in ("owned", "licensed", "permission_required", "reference_only", "unknown"):
        assert validate_rights_status(s) is True
    assert validate_rights_status("whatever") is False


def test_default_rights_is_unknown(session):
    from src.core.database import SourceDocument
    import uuid
    d = SourceDocument(id=str(uuid.uuid4()), repo_name="11-dump",
                       source_path="x.pdf", file_sha256="s", file_size=1,
                       file_type="pdf")
    session.add(d)
    session.commit()
    assert d.rights_status == "unknown"
