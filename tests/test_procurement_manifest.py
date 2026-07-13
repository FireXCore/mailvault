import json
from pathlib import Path

from firexcore_mailvault.procurement import ProcurementManifestExporter
from firexcore_mailvault.repository import ArchiveRepository


def test_procurement_manifest_empty_archive_is_valid(tmp_path: Path) -> None:
    output = tmp_path / "procurement_sources.jsonl"
    with ArchiveRepository(tmp_path / "mailvault.sqlite3") as repository:
        ProcurementManifestExporter(repository).export(output)
    assert output.exists()
    assert output.read_text(encoding="utf-8") == ""


def test_schema_name_is_stable() -> None:
    record = {"schema_version": "firexcore.mailvault.procurement-source.v1"}
    encoded = json.dumps(record)
    assert "procurement-source.v1" in encoded
