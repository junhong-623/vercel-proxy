from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import re
import json


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        num_raw = params.get("num", [""])[0]
        num = re.sub(r"\D", "", num_raw)

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if not num:
            self._write({"error": "请输入号码"})
            return

        url = f"https://4dmanager.net/no/{num}"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                # site uses windows-1252
                html = raw.decode("windows-1252", errors="replace")

        except urllib.error.URLError as e:
            self._write({"error": f"抓取失败: {e.reason}"})
            return
        except Exception as e:
            self._write({"error": f"未知错误: {str(e)}"})
            return

        records = parse_history(html, num)
        self._write({"num": num, "records": records})

    def _write(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


# ── HTML parser ────────────────────────────────────────────────────────────────

COMPANY_MAP = {
    "magnum":   "Magnum",
    "mgt":      "Magnum",
    "toto":     "Sports Toto",
    "damacai":  "Da Ma Cai",
    "dmc":      "Da Ma Cai",
    "sabah":    "Sabah",
    "sandakan": "Sandakan",
    "sarawak":  "Sarawak",
    "cashsweep":"Cash Sweep",
    "gd":       "Grand Dragon",
    "perdana":  "Perdana",
}

PRIZE_MAP = {
    "1":  "1st",  "1st": "1st", "first":   "1st",
    "2":  "2nd",  "2nd": "2nd", "second":  "2nd",
    "3":  "3rd",  "3rd": "3rd", "third":   "3rd",
    "s":  "Special",   "sp": "Special",   "special":    "Special",
    "c":  "Consolation","con":"Consolation","consolation":"Consolation",
}


def clean(s):
    """Strip tags and collapse whitespace."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_prize(raw):
    key = raw.lower().strip().lstrip("0")
    return PRIZE_MAP.get(key, raw)


def normalize_company(raw):
    low = raw.lower()
    for k, v in COMPANY_MAP.items():
        if k in low:
            return v
    return raw.strip()


def parse_history(html, num):
    """
    Extract draw history rows from 4dmanager.net/no/<num>.
    Returns list of {date, company, prize, number} dicts sorted newest-first.
    """
    records = []

    # Find all <tr> blocks
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL)

    # Detect header row to map column positions
    date_col = company_col = prize_col = number_col = -1

    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL)
        texts = [clean(c) for c in cells]

        if not texts:
            continue

        # Try to identify header row
        joined = " ".join(texts).lower()
        if date_col == -1 and ("date" in joined or "tarikh" in joined):
            for i, t in enumerate(texts):
                tl = t.lower()
                if "date" in tl or "tarikh" in tl:
                    date_col = i
                if "company" in tl or "operator" in tl or "syarikat" in tl:
                    company_col = i
                if "prize" in tl or "hadiah" in tl or "position" in tl:
                    prize_col = i
                if tl in ("no", "no.", "number", "nombor", "4d", "num", "result"):
                    number_col = i
            continue

        # Data row — need at least 3 cells
        if len(texts) < 3:
            continue

        # Skip rows that look like sub-headers or ads
        if any(t.lower() in ("date", "company", "prize", "no", "") for t in texts[:2]):
            continue

        # Use detected column positions or fall back to positional guessing
        date    = texts[date_col]    if 0 <= date_col    < len(texts) else texts[0]
        company = texts[company_col] if 0 <= company_col < len(texts) else texts[1]
        prize   = texts[prize_col]   if 0 <= prize_col   < len(texts) else texts[2]

        # Winning number: try detected column first, then scan all cells for digit-only value
        winning = texts[number_col] if 0 <= number_col < len(texts) else ""
        if not re.match(r"^\d+$", winning.strip()):
            for t in texts:
                t = t.strip()
                if re.match(r"^\d{2,6}$", t) and t != re.sub(r"\D", "", date):
                    winning = t
                    break

        # Validate date looks like a date (contains digits and separators)
        if not re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", date):
            continue

        records.append({
            "date":    date,
            "company": normalize_company(company),
            "prize":   normalize_prize(prize),
            "number":  winning.strip(),
        })

    # Deduplicate and return newest-first (assuming page is oldest-first)
    seen = set()
    unique = []
    for r in records:
        key = (r["date"], r["company"], r["prize"], r["number"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.reverse()
    return unique
