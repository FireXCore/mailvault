from __future__ import annotations

from email.headerregistry import Address
from email.utils import getaddresses

from firexcore_mailvault.models import AddressValue
from firexcore_mailvault.unicode_safety import sanitize_text


def parse_addresses(values: list[str] | tuple[str, ...]) -> tuple[AddressValue, ...]:
    result: list[AddressValue] = []
    seen: set[tuple[str, str]] = set()
    for display_name, address in getaddresses(list(values)):
        normalized_address = sanitize_text(address).strip().casefold()
        if not normalized_address:
            continue
        normalized_name = sanitize_text(display_name).strip()
        key = (normalized_name, normalized_address)
        if key in seen:
            continue
        seen.add(key)
        domain = normalized_address.rsplit("@", 1)[1] if "@" in normalized_address else None
        result.append(AddressValue(normalized_name, normalized_address, domain))
    return tuple(result)


def address_header_to_strings(value: object) -> list[str]:
    if value is None:
        return []
    addresses = getattr(value, "addresses", None)
    if addresses is None:
        return [sanitize_text(str(value))]
    output: list[str] = []
    for item in addresses:
        if isinstance(item, Address):
            output.append(sanitize_text(str(item)))
        else:
            output.append(sanitize_text(str(item)))
    return output
