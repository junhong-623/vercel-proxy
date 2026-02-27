"""
api/rates.py  —  Vercel serverless endpoint
GET /api/rates?n=JPY  →  JSON list of MYR exchange rates from klmoneychanger.com

The page table has a repeating 4-row pattern per money changer:
  Row 1: name only (colspan, no data)
  Row 2: name | unit (e.g. "1000 JPY") | we_buy | we_sell | last_updated   ← the one we want
  Row 3: "Last updated on ..." (colspan, skip)
  Row 4: address block (colspan, skip)

Since the name already appears in Row 2 alongside the data,
we only need to parse Row 2 — identified by having the currency code in column 2.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import re
import json

SUPPORTED = {"USD", "JPY", "CNY", "SGD", "THB", "KRW", "HKD", "AUD"}


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", errors="ignore")


def strip_tags(html: str) -> str:
    """Remove all HTML tags, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def parse_rates(html: str, currency: str) -> list:
    """
    Extract all data rows from the comparison table.

    A data row has exactly 5 <td> cells:
      [0] money changer name  e.g. "MAXMONEY - MIDVALLEY MEGAMALL"
      [1] unit                e.g. "1000 JPY"
      [2] we_buy              e.g. "24.9200"
      [3] we_sell             e.g. "25.2200"
      [4] last_updated        e.g. "2026-02-27 8:55 AM"

    We confirm it's a data row by checking that column [1] contains
    a number followed by the currency code (case-insensitive).
    """
    results = []

    # Pull every <tr>...</tr> block (non-greedy, dotall)
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S | re.I):

        # Pull every <td>...</td> within this row
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, re.S | re.I)
        if len(cells) != 5:
            continue  # data rows always have exactly 5 cells

        name_raw, unit_raw, buy_raw, sell_raw, updated_raw = cells

        # Confirm column [1] looks like "1000 JPY" or "1 USD"
        unit_text = strip_tags(unit_raw)
        if not re.search(rf"\d+\s+{re.escape(currency)}\b", unit_text, re.I):
            continue

        # Parse unit number (the integer before the currency code)
        unit_match = re.search(r"(\d+)", unit_text)
        unit = int(unit_match.group(1)) if unit_match else 1

        # Parse buy / sell — keep only digits and decimal point
        try:
            buy  = float(re.sub(r"[^\d.]", "", strip_tags(buy_raw)))
            sell = float(re.sub(r"[^\d.]", "", strip_tags(sell_raw)))
        except ValueError:
            continue

        if buy <= 0 or sell <= 0:
            continue

        # Clean up name: Title Case, strip extra spaces
        name = " ".join(strip_tags(name_raw).title().split())

        results.append({
            "name":    name,
            "unit":    unit,
            "buy":     buy,
            "sell":    sell,
            "updated": strip_tags(updated_raw),
        })

    # Best buy price (highest MYR per foreign unit) first
    results.sort(key=lambda x: x["buy"], reverse=True)
    return results


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # --- parse ?n=JPY query param ---
        params = parse_qs(urlparse(self.path).query)
        currency = params.get("n", [""])[0].upper().strip()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if currency not in SUPPORTED:
            self._json({"error": f"Unsupported currency '{currency}'. Supported: {sorted(SUPPORTED)}", "data": []})
            return

        url = f"https://www.klmoneychanger.com/compare-rates?n={currency}"
        try:
            html = fetch_html(url)
        except urllib.error.URLError as e:
            self._json({"error": f"Fetch failed: {e.reason}", "data": []})
            return
        except Exception as e:
            self._json({"error": str(e), "data": []})
            return

        data = parse_rates(html, currency)
        self._json({
            "currency": currency,
            "base":     "MYR",
            "note":     "Rates from klmoneychanger.com — MYR-based, updated by each store daily",
            "count":    len(data),
            "data":     data,
        })

    def _json(self, obj: dict):
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args):
        pass  # suppress default access logs
