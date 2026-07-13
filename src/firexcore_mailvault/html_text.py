from __future__ import annotations

from html.parser import HTMLParser

from firexcore_mailvault.unicode_safety import sanitize_text


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "head", "title", "noscript"}:
            self._hidden_depth += 1
        if tag.casefold() in {"br", "p", "div", "tr", "li", "hr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "head", "title", "noscript"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        if tag.casefold() in {"p", "div", "tr", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def html_to_visible_text(html: str | None) -> str | None:
    if not html:
        return None
    parser = _VisibleTextParser()
    parser.feed(sanitize_text(html))
    parser.close()
    return parser.text() or None
