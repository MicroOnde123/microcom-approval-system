"""Database-free, synthetic Edge layout/PDF evidence; no deployed application.

Run --prepare first, then --browser under approved browser-launch permissions.
Artifacts stay in local_artifacts/invoice_pdf_delivery (never financial storage).
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import base64
import socket
import struct
import time
import urllib.request
from types import SimpleNamespace
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "local_artifacts" / "invoice_pdf_delivery"


def prepare():
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_stock_review_settings"
    import django
    django.setup()
    from django.template import Context, Engine
    from django.utils.translation import override
    from .pdf import render_pdf
    from inventory.test_address_offline import AddressOfflineTests
    OUTPUT.mkdir(parents=True, exist_ok=True)
    invoice = SimpleNamespace(
        pk=1, status="FINALIZED", get_status_display="FINALIZED",
        number="SYNTHETIC-INVOICE", currency="USD", total=2,
        business_timezone="Africa/Kinshasa",
        company_snapshot={"company_name": "Synthetic Company", "company_address": "Synthetic address"},
        succursale_snapshot={"code": "TEST", "name": "Synthetic test branch"},
        request_reference_snapshot="SYNTHETIC-REQUEST", audit_metadata={},
    )
    for language in ("en", "fr"):
        with override(language):
            html = Engine.get_default().get_template("invoicing/detail.html").render(Context({
                "invoice": invoice, "lines": [], "audit_history": [], "csrf_token": "synthetic-only",
                "return_note_nav": {"can_read": True, "can_issue": True, "invoice_id": 1},
                "request": SimpleNamespace(user=SimpleNamespace(
                    is_authenticated=False, username="synthetic", full_name="Synthetic user")),
                "LANGUAGE_CODE": language,
            }))
        # Read-only fixture: no background notification calls or form submissions.
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        html = html.replace('"/static/', '"' + (ROOT / "static").as_uri() + "/")
        checks = """<script>
window.addEventListener('load', () => {
 const bar = document.querySelector('.invoice-actions');
 const controls = [...bar.querySelectorAll('button,a')];
 const boxes = controls.map(e => {const b=e.getBoundingClientRect();return {text:e.textContent.trim(),x:b.x,y:b.y,w:b.width,h:b.height};});
 const result = {width:innerWidth, overflow:document.documentElement.scrollWidth>innerWidth,
  controls:boxes, readable:boxes.every(b=>b.w>80&&b.h>=44),
  allInside:boxes.every(b=>b.x>=0&&b.x+b.w<=innerWidth),
  printFirst:bar.querySelector('button').closest('form').action.endsWith('/invoices/1/print/')};
 document.body.setAttribute('data-invoice-qa',JSON.stringify(result));
});
</script>"""
        html = html.replace("</body>", checks + "</body>")
        (OUTPUT / f"invoice-{language}.html").write_text(html, encoding="utf-8")
        (OUTPUT / f"invoice-{language}.pdf").write_bytes(render_pdf(AddressOfflineTests().snapshot(), language))
    print("Prepared synthetic templates/PDFs; no database or financial record accessed.")


def browser():
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    profile = Path(mkdtemp(prefix="edge-cdp-", dir=OUTPUT))
    client = None
    process = subprocess.Popen([
        str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--disable-background-networking",
        "--remote-debugging-port=0", "--user-data-dir=" + str(profile), "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(100):
            port_file = profile / "DevToolsActivePort"
            if port_file.exists():
                break
            time.sleep(.1)
        port = int(port_file.read_text().splitlines()[0])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        pages = json.load(opener.open(f"http://127.0.0.1:{port}/json"))
        page = next(p for p in pages if p["type"] == "page")
        client = DevTools(page["webSocketDebuggerUrl"])
        client.call("Page.enable")
        results = []
        for language in ("en", "fr"):
            for width in (1440, 390):
                name = f"toolbar-{language}-{width}"
                client.call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 1100, "deviceScaleFactor": 1, "mobile": False})
                client.call("Page.navigate", {"url": (OUTPUT / f"invoice-{language}.html").as_uri()})
                for _ in range(60):
                    reply = client.call("Runtime.evaluate", {
                        "expression": "document.body && document.body.getAttribute('data-invoice-qa')",
                        "returnByValue": True})
                    value = reply.get("result", {}).get("value")
                    if value:
                        break
                    time.sleep(.1)
                result = json.loads(value)
                assert result["width"] == width, result
                assert not result["overflow"], result
                assert result["readable"] and result["allInside"] and result["printFirst"], result
                assert len(result["controls"]) == 4, result
                if width == 1440:
                    assert len({round(b["y"]) for b in result["controls"]}) == 1, result
                shot = client.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (OUTPUT / (name + ".png")).write_bytes(base64.b64decode(shot["data"]))
                results.append({"language": language, **result})
                print(name + ": exact viewport/layout assertions passed", flush=True)
        (OUTPUT / "browser-results.json").write_text(json.dumps({
            "environment": "Synthetic local templates, not authenticated deployment",
            "layout": results, "native_pdf_visual_review": "headless capture blank; not verified",
            "chrome_firefox": "not tested", "native_print_dialog": "not automated",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        if client:
            try:
                client.call("Browser.close")
            except (OSError, ConnectionError):
                pass
            client.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return


class DevTools:
    """Minimal local CDP socket; no new package or application connection."""
    def __init__(self, url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((
            f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            header += self.socket.recv(1)
        assert header.split(b"\r\n", 1)[0].split()[1] == b"101", header
        self.counter = 0

    def read(self, length):
        data = b""
        while len(data) < length:
            part = self.socket.recv(length-len(data))
            if not part:
                raise ConnectionError("Closed CDP socket")
            data += part
        return data

    def call(self, method, params=None):
        self.counter += 1
        payload = json.dumps({"id": self.counter, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        size = len(payload)
        head = bytes([129, 128 | size]) if size < 126 else (
            bytes([129, 254]) + struct.pack("!H", size) if size < 65536 else
            bytes([129, 255]) + struct.pack("!Q", size))
        self.socket.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        fragments = b""
        while True:
            first, second = self.read(2)
            length = second & 127
            if length == 126:
                length = struct.unpack("!H", self.read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self.read(8))[0]
            if second & 128:
                raise ValueError("Unexpected masked server frame")
            fragments += self.read(length)
            if not first & 128:
                continue
            message = json.loads(fragments)
            fragments = b""
            if message.get("id") == self.counter:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def close(self):
        self.socket.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.browser:
        browser()
