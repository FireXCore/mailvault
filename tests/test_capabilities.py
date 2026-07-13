from firexcore_mailvault.protocols.imap.capabilities import (
    effective_batch_size,
    parse_capabilities,
)


def test_parses_modern_imap_capabilities() -> None:
    caps = parse_capabilities(
        [
            b"IMAP4rev2",
            b"OBJECTID",
            b"CONDSTORE",
            b"QRESYNC",
            b"UIDONLY",
            b"MESSAGELIMIT=750",
        ]
    )

    assert caps.imap4rev2 is True
    assert caps.object_id is True
    assert caps.condstore is True
    assert caps.qresync is True
    assert caps.uid_only is True
    assert caps.message_limit == 750
    assert effective_batch_size(1000, caps) == 750
