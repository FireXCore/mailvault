from pathlib import Path

from firexcore_mailvault.archive import BlobStore
from firexcore_mailvault.mime_parser import parse_message
from firexcore_mailvault.models import PartRole


def test_preserves_body_inline_asset_and_attachment(
    sample_message_bytes: bytes,
    archive_root: Path,
) -> None:
    store = BlobStore(archive_root / "objects" / "blobs" / "sha256", archive_root)
    result = parse_message(sample_message_bytes, store)

    roles = [part.role for part in result.parsed_message.parts]
    assert PartRole.BODY_PLAIN in roles
    assert PartRole.BODY_HTML in roles
    assert PartRole.INLINE_RESOURCE in roles
    assert PartRole.ATTACHMENT in roles
    attachment = next(
        part for part in result.parsed_message.parts if part.role is PartRole.ATTACHMENT
    )
    assert attachment.filename_original == "Quotation CTG-87-22.pdf"
    assert attachment.sha256 is not None
    assert attachment.blob_path is not None
    assert "EUR 1250" in (result.parsed_message.plain_text or "")
