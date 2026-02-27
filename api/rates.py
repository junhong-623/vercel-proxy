
Copy

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import re
import json

VALID_CURRENCIES = {"USD", "JPY", "CNY", "SGD", "THB", "KRW", "HKD", "AUD"}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        currency = params.get("n", [""])[0].upper().strip()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if currency not in VALID_CURRENCIES:
            self._write({"error": f"Unsupported currency: {currency}", "data": []})
            return

        url = f"https://www.klmoneychanger.com/compare-rates?n={currency}"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.URLError as e:
            self._write({"error": f"Fetch failed: {e.reason}", "data": []})
            return
        except Exception as e:
            self._write({"error": f"Unknown error: {str(e)}", "data": []})
            return

        data = self._parse(html, currency)
        self._write({
            "currency": currency,
            "base": "MYR",
            "note": "MYR-based rates from KL money changers (klmoneychanger.com)",
            "data": data
        })

    def _parse(self, html, currency):
        results = []

        # Each money changer block looks like:
        # <tr><td colspan=...>NAME</td></tr>
        # <tr><td>UNIT (e.g. 1000 JPY)</td><td>BUY</td><td>SELL</td><td>UPDATED</td></tr>
        # <tr><td colspan=...>Last updated on ...</td></tr>
        # <tr><td colspan=...>address block</td></tr>

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)

        def strip_tags(s):
            return re.sub(r"<[^>]+>", "", s).strip()

        current_name = None

        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
            texts = [strip_tags(c) for c in cells]
            texts = [t for t in texts if t]

            if not texts:
                continue

            # Data row: must contain currency code in first cell e.g. "1000 JPY" or "1 USD"
            if len(texts) >= 4 and re.search(rf"\d+\s*{currency}", texts[0], re.IGNORECASE):
                unit_str  = texts[0]   # "1000 JPY"
                buy_str   = texts[1]   # "24.92"
                sell_str  = texts[2]   # "25.22"
                updated   = texts[3]   # "2026-02-27 8:55 AM"

                unit_match = re.search(r"(\d+)", unit_str)
                unit = int(unit_match.group(1)) if unit_match else 1

                try:
                    buy  = float(re.sub(r"[^\d.]", "", buy_str))
                    sell = float(re.sub(r"[^\d.]", "", sell_str))
                except ValueError:
                    current_name = None
                    continue

                if buy <= 0 or sell <= 0 or not current_name:
                    continue

                results.append({
                    "name":    current_name,
                    "unit":    unit,
                    "buy":     buy,
                    "sell":    sell,
                    "updated": updated,
                })
                current_name = None
                continue

            # Name row: single cell, not "Last updated", not address-like
            if len(cells) == 1:
                name = texts[0] if texts else ""
                if (name
                    and not name.lower().startswith("last updated")
                    and not re.search(r"(google map|jalan|lot |level |floor|kuala lumpur|selangor|puchong|kajang|\+60)", name, re.IGNORECASE)
                ):
                    current_name = name.title()

        results.sort(key=lambda x: x["buy"], reverse=True)
        return results

    def _write(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silent logs
