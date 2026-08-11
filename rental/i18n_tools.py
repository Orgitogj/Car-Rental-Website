from __future__ import annotations
import ast
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from django.utils.translation.template import templatize

MO_MAGIC = 0x950412DE
GETTEXT_NAMES = {
    "gettext",
    "gettext_lazy",
    "ugettext",
    "ugettext_lazy",
    "_",
}
NGETTEXT_NAMES = {"ngettext", "ngettext_lazy", "ungettext", "ungettext_lazy"}
PGETTEXT_NAMES = {"pgettext", "pgettext_lazy"}
NPGETTEXT_NAMES = {"npgettext", "npgettext_lazy"}


# ---------------------------------------------------------------------------
# Catalogue model
# ---------------------------------------------------------------------------


@dataclass
class Message:
    msgid: str
    msgid_plural: str | None = None
    msgstr: str = ""
    msgstr_plural: dict = field(default_factory=dict)
    msgctxt: str | None = None
    references: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    comments: list = field(default_factory=list)

    @property
    def key(self):
        return (self.msgctxt, self.msgid)

    @property
    def is_plural(self):
        return self.msgid_plural is not None

    @property
    def translated(self):
        if self.is_plural:
            return any(v.strip() for v in self.msgstr_plural.values())
        return bool(self.msgstr.strip())

    @property
    def fuzzy(self):
        return "fuzzy" in self.flags


@dataclass
class Catalogue:
    metadata: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)

    def index(self):
        return {m.key: m for m in self.messages}

    @property
    def translated_count(self):
        return sum(1 for m in self.messages if m.translated and not m.fuzzy)

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}
_UNESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r", "'": "'"}


def po_escape(value: str) -> str:
    return "".join(_ESCAPES.get(ch, ch) for ch in value)


def po_unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append(_UNESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _quote(value: str) -> str:
  
    escaped = po_escape(value)
    if len(escaped) <= 72 and "\\n" not in escaped:
        return f'"{escaped}"'
    chunks = []
    for part in value.split("\n")[:-1]:
        chunks.append(part + "\n")
    tail = value.split("\n")[-1]
    if tail or not chunks:
        chunks.append(tail)

    lines = ['""']
    for chunk in chunks:
        piece = po_escape(chunk)
        while len(piece) > 72:
            cut = piece.rfind(" ", 0, 72)
            if cut <= 0:
                cut = 72
            else:
                cut += 1
            lines.append(f'"{piece[:cut]}"')
            piece = piece[cut:]
        if piece:
            lines.append(f'"{piece}"')
    return "\n".join(lines)

_LINE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(.*)$')


def parse_po(path: Path) -> Catalogue:
  
    catalogue = Catalogue()
    if not path.exists():
        return catalogue

    current = None
    slot = None  
    plural_index = None
    pending_refs, pending_flags, pending_comments = [], [], []

    def flush():
        nonlocal current
        if current is None:
            return
        if current.msgid == "" and current.msgctxt is None:
            for line in current.msgstr.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    catalogue.metadata[key.strip()] = value.strip()
        else:
            catalogue.messages.append(current)
        current = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line:
            continue

        if line.startswith("#"):
            if line.startswith("#:"):
                pending_refs.extend(line[2:].split())
            elif line.startswith("#,"):
                pending_flags.extend(f.strip() for f in line[2:].split(","))
            elif line.startswith("#."):
                pending_comments.append(line[2:].strip())
            continue

        match = _LINE.match(line)
        if match:
            keyword, index, rest = match.group(1), match.group(2), match.group(3)
            value = po_unescape(rest.strip()[1:-1]) if rest.strip().startswith('"') else ""

            if keyword == "msgctxt":
                flush()
                current = Message(
                    msgid="",
                    msgctxt=value,
                    references=pending_refs,
                    flags=pending_flags,
                    comments=pending_comments,
                )
                pending_refs, pending_flags, pending_comments = [], [], []
                slot, plural_index = "msgctxt", None

            elif keyword == "msgid":
                if current is None or slot in {"msgstr", "msgstr_plural"}:
                    flush()
                    current = Message(
                        msgid=value,
                        references=pending_refs,
                        flags=pending_flags,
                        comments=pending_comments,
                    )
                    pending_refs, pending_flags, pending_comments = [], [], []
                else:
                    current.msgid = value
                slot, plural_index = "msgid", None

            elif keyword == "msgid_plural":
                if current is not None:
                    current.msgid_plural = value
                slot, plural_index = "msgid_plural", None

            else:  # msgstr / msgstr[n]
                if current is None:
                    continue
                if index is None:
                    current.msgstr = value
                    slot, plural_index = "msgstr", None
                else:
                    plural_index = int(index)
                    current.msgstr_plural[plural_index] = value
                    slot = "msgstr_plural"
            continue

        # Continuation line
        if line.startswith('"') and current is not None and slot:
            value = po_unescape(line[1:-1])
            if slot == "msgid":
                current.msgid += value
            elif slot == "msgid_plural":
                current.msgid_plural = (current.msgid_plural or "") + value
            elif slot == "msgctxt":
                current.msgctxt = (current.msgctxt or "") + value
            elif slot == "msgstr":
                current.msgstr += value
            elif slot == "msgstr_plural":
                current.msgstr_plural[plural_index] = (
                    current.msgstr_plural.get(plural_index, "") + value
                )

    flush()
    return catalogue

def write_po(path: Path, catalogue: Catalogue, header_comment: str = "") -> None:
    out = []

    if header_comment:
        for line in header_comment.strip().splitlines():
            out.append(f"# {line}".rstrip())

    out.append('msgid ""')
    out.append('msgstr ""')
    for key, value in catalogue.metadata.items():
        out.append(f'"{po_escape(key)}: {po_escape(value)}\\n"')
    out.append("")

    for message in catalogue.messages:
        for comment in message.comments:
            out.append(f"#. {comment}")
        for reference in message.references:
            out.append(f"#: {reference}")
        if message.flags:
            out.append("#, " + ", ".join(dict.fromkeys(message.flags)))

        if message.msgctxt is not None:
            out.append(f"msgctxt {_quote(message.msgctxt)}")

        out.append(f"msgid {_quote(message.msgid)}")

        if message.is_plural:
            out.append(f"msgid_plural {_quote(message.msgid_plural)}")
            for index in sorted(message.msgstr_plural or {0: "", 1: ""}):
                out.append(
                    f"msgstr[{index}] {_quote(message.msgstr_plural.get(index, ''))}"
                )
        else:
            out.append(f"msgstr {_quote(message.msgstr)}")

        out.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")

def write_mo(path: Path, catalogue: Catalogue) -> int:
    
    entries: list[tuple[bytes, bytes]] = []

    metadata = "".join(f"{k}: {v}\n" for k, v in catalogue.metadata.items())
    entries.append((b"", metadata.encode("utf-8")))

    for message in catalogue.messages:
        if message.fuzzy or not message.translated:
            continue

        if message.is_plural:
            key = f"{message.msgid}\x00{message.msgid_plural}"
            forms = [
                message.msgstr_plural.get(i, "")
                for i in range(max(message.msgstr_plural) + 1)
            ]
            value = "\x00".join(forms)
        else:
            key = message.msgid
            value = message.msgstr

        if message.msgctxt:
            key = f"{message.msgctxt}\x04{key}"

        entries.append((key.encode("utf-8"), value.encode("utf-8")))

    entries.sort(key=lambda pair: pair[0])
    count = len(entries)

    key_table_offset = 28
    value_table_offset = key_table_offset + count * 8
    data_offset = value_table_offset + count * 8

    key_table, value_table, blob = [], [], b""
    offset = data_offset
    for key, _value in entries:
        key_table.append((len(key), offset))
        blob += key + b"\x00"
        offset += len(key) + 1
    for _key, value in entries:
        value_table.append((len(value), offset))
        blob += value + b"\x00"
        offset += len(value) + 1

    output = struct.pack(
        "<Iiiiiii",
        MO_MAGIC,
        0,
        count,
        key_table_offset,
        value_table_offset,
        0,
        data_offset,
    )
    for length, off in key_table:
        output += struct.pack("<ii", length, off)
    for length, off in value_table:
        output += struct.pack("<ii", length, off)
    output += blob

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)
    return count - 1  


_PLACEHOLDER = re.compile(r"%(?:\((\w+)\)|)([sdfgr%])")


def placeholders(text: str) -> set:
    """The %(name)s / %s tokens a string interpolates.

    Django formats translated strings with the msgid's arguments, so a msgstr
    that names a placeholder the msgid does not have raises KeyError at render
    time. Comparing the two sets catches that before it reaches a browser.
    """
    found = set()
    positional = 0
    for name, kind in _PLACEHOLDER.findall(text):
        if kind == "%":
            continue
        if name:
            found.add(name)
        else:
            positional += 1
            found.add(f"#{positional}")
    return found


def check_placeholders(catalogue: "Catalogue") -> list:
    """Return (msgid, msgstr, missing, extra) for every inconsistent message."""
    problems = []
    for message in catalogue.messages:
        if message.fuzzy or not message.translated:
            continue

        pairs = (
            [(message.msgid, message.msgstr_plural.get(0, "")),
             (message.msgid_plural, message.msgstr_plural.get(1, ""))]
            if message.is_plural
            else [(message.msgid, message.msgstr)]
        )
        for source, target in pairs:
            if not target.strip():
                continue
            expected = placeholders(source or "")
            actual = placeholders(target)
            if expected != actual:
                problems.append(
                    (source, target, expected - actual, actual - expected)
                )
    return problems


_STRING = r"""(?:[uUbB]?(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"))"""
_CALL_RE = re.compile(
    r"\b(n?p?gettext)\s*\(\s*(" + _STRING + r")"
    r"\s*(?:,\s*(" + _STRING + r"))?"
    r"\s*(?:,\s*(" + _STRING + r"))?",
)


def _literal(token: str) -> str:
    
    try:
        return ast.literal_eval(token)
    except (SyntaxError, ValueError):
        return token[1:-1]


def _add(found: dict, msgid, plural, context, reference):
    if not msgid:
        return
    key = (context, msgid)
    entry = found.get(key)
    if entry is None:
        entry = Message(msgid=msgid, msgid_plural=plural, msgctxt=context)
        found[key] = entry
    if plural and not entry.msgid_plural:
        entry.msgid_plural = plural
    if reference not in entry.references:
        entry.references.append(reference)


class ExtractionError(Exception):
    """A source file could not be scanned for translatable strings."""


def extract_from_template(path: Path, relative: str, found: dict) -> None:

    source = path.read_text(encoding="utf-8")
    try:
        converted = templatize(source, origin=str(path))
    except Exception as exc:
        # A broken {% trans %}/{% blocktrans %} block would otherwise drop every
        # string in the file without a word of warning.
        raise ExtractionError(f"{relative}: {exc}") from exc

    for line_number, line in enumerate(converted.splitlines(), start=1):
        for match in _CALL_RE.finditer(line):
            func = match.group(1)
            first, second, third = (
                _literal(group) if group else None for group in match.group(2, 3, 4)
            )
            reference = f"{relative}:{line_number}"

            # gettext(msgid) / ngettext(singular, plural)
            # pgettext(context, msgid) / npgettext(context, singular, plural)
            if func == "ngettext":
                _add(found, first, second, None, reference)
            elif func == "pgettext":
                _add(found, second, None, first, reference)
            elif func == "npgettext":
                _add(found, second, third, first, reference)
            else:
                _add(found, first, None, None, reference)


def extract_from_python(path: Path, relative: str, found: dict) -> None:
    """Extract gettext calls from real Python using the AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ExtractionError(f"{relative}: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute) else None
        )
        if not name or not node.args:
            continue

        def const(index):
            if len(node.args) > index and isinstance(node.args[index], ast.Constant):
                value = node.args[index].value
                return value if isinstance(value, str) else None
            return None

        reference = f"{relative}:{node.lineno}"

        if name in GETTEXT_NAMES:
            _add(found, const(0), None, None, reference)
        elif name in NGETTEXT_NAMES:
            _add(found, const(0), const(1), None, reference)
        elif name in PGETTEXT_NAMES:
            _add(found, const(1), None, const(0), reference)
        elif name in NPGETTEXT_NAMES:
            _add(found, const(1), const(2), const(0), reference)


SKIP_DIRS = {
    "venv", ".git", "__pycache__", "node_modules", "staticfiles",
    "media", "migrations", "locale",
}


def extract_messages(base_dir: Path, roots: list[str]) -> list[Message]:
    """Walk the project and collect every translatable string."""
    found: dict = {}

    for root in roots:
        root_path = base_dir / root
        if not root_path.exists():
            continue

        for path in sorted(root_path.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue

            relative = path.relative_to(base_dir).as_posix()

            if path.suffix == ".html":
                extract_from_template(path, relative, found)
            elif path.suffix == ".py":
                extract_from_python(path, relative, found)

    return sorted(found.values(), key=lambda m: (m.msgid.lower(), m.msgctxt or ""))
