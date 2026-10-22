"""Recipe errors."""

import re
from pathlib import Path


class RecipeError(ValueError):
    """A recipe problem, with the line it is on and how to fix it."""

    def __init__(
        self,
        message: str,
        path: Path | None = None,
        line: int | None = None,
        hint: str = "",
    ) -> None:
        super().__init__(message)
        self.message, self.path, self.line, self.hint = message, path, line, hint

    def source_line(self) -> str:
        """The offending line of the recipe file ("" when unknown)."""
        if not (self.path and self.line):
            return ""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        return lines[self.line - 1] if 0 < self.line <= len(lines) else ""


def _line(text: str, section: str, key: str | None = None, index: int = 0) -> int | None:
    """Return a key's 1-based line, or its section header's line."""
    current, seen, header = "", -1, None
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if h := re.match(r"^\[\[?\s*([\w.-]+)\s*\]\]?", line):
            current = h.group(1)
            if current == section:
                seen += 1
                if seen == index:
                    header = i
            continue
        name = re.escape(key or "")
        is_key = bool(key) and bool(re.match(rf'^"?{name}"?\s*=', line))
        if current == section and (not section or seen == index) and is_key:
            return i
    return header
