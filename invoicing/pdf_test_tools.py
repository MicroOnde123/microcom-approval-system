"""Small test-only reader for the PDF syntax emitted by ReportLab (not uploads)."""
import base64
import re
import zlib


def pdf_text(content):
    objects = {int(n): body for n, body in re.findall(rb"(\d+) 0 obj\s*(.*?)\s*endobj", content, re.S)}

    def stream(body):
        data = re.search(rb"stream\r?\n(.*?)endstream", body, re.S).group(1).rstrip(b"\r\n")
        if b"/ASCII85Decode" in body:
            data = base64.a85decode(data, adobe=True)
        if b"/FlateDecode" in body:
            data = zlib.decompress(data)
        return data

    fonts = {}
    for body in objects.values():
        match = re.search(rb"/Name /(\S+).*?/ToUnicode (\d+) 0 R", body, re.S)
        if match:
            cmap = stream(objects[int(match[2])])
            block = re.search(rb"beginbfchar(.*?)endbfchar", cmap, re.S).group(1)
            fonts[match[1]] = {int(a, 16): bytes.fromhex(b.decode()).decode("utf-16-be")
                                for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block)}

    def literal(data):
        def replace(match):
            escaped = match[1]
            if escaped[:1] in b"01234567":
                return bytes([int(escaped, 8)])
            return {b"n":b"\n", b"r":b"\r", b"t":b"\t", b"b":b"\b", b"f":b"\f"}.get(escaped, escaped)
        return re.sub(rb"\\([0-7]{1,3}|.)", replace, data, flags=re.S)

    text = []
    for body in objects.values():
        if not re.search(rb"\bstream\r?\n", body) or b"/Subtype /Image" in body:
            continue
        data = stream(body)
        if b"BT" not in data:
            continue
        font = None
        for token in re.finditer(rb"/(\S+)\s+[\d.]+\s+Tf|\(((?:\\.|[^\\)])*)\)\s*Tj", data, re.S):
            if token[1]:
                font = token[1]
            else:
                text.append("".join(fonts.get(font, {}).get(c, chr(c)) for c in literal(token[2])))
    return "\n".join(text)
