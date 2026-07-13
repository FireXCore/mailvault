from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest


@pytest.fixture
def sample_message_bytes() -> bytes:
    message = EmailMessage()
    message["Message-ID"] = "<quote-1@example.com>"
    message["From"] = "Vendor Sales <sales@vendor.example>"
    message["To"] = "Buyer <buyer@example.org>"
    message["Subject"] = "RE: Quotation CTG-87-22"
    message["Date"] = "Mon, 14 Mar 2011 12:52:12 +0330"
    message.set_content("Price: EUR 1250. Delivery: 6 weeks.")
    message.add_alternative(
        '<html><body><p>Price: EUR 1250.</p><img src="cid:logo1"></body></html>',
        subtype="html",
    )
    message.get_payload()[1].add_related(
        b"GIF89a",
        maintype="image",
        subtype="gif",
        cid="<logo1>",
        filename="logo.gif",
        disposition="inline",
    )
    message.add_attachment(
        b"%PDF-1.4\nquotation-data",
        maintype="application",
        subtype="pdf",
        filename="Quotation CTG-87-22.pdf",
    )
    return message.as_bytes()


@pytest.fixture
def archive_root(tmp_path: Path) -> Path:
    return tmp_path / "archive"
