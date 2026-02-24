from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import re
import json


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # ── 解析 ?num=1234 ──────────────────────────────────────
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        num_raw = params.get("num", [""])[0]
        num = re.sub(r"\D", "", num_raw).zfill(4)[:4]

        # CORS headers（允许 GitHub Pages 调用）
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if len(num) != 4:
            self._write({"error": "需要4位数字"})
            return

        url = f"https://4dmanager.net/search/{num}"

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
                html = resp.read().decode("utf-8", errors="ignore")

        except urllib.error.URLError as e:
            self._write({"error": f"抓取失败: {e.reason}"})
            return
        except Exception as e:
            self._write({"error": f"未知错误: {str(e)}"})
            return

        # ── 解析 keywords meta tag ───────────────────────────────
        # <meta name="keywords" content="超级玛丽,super mario">
        pattern = (
            r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']+)["\']'
            r'|<meta\s+content=["\']([^"\']+)["\']\s+name=["\']keywords["\']'
        )
        match = re.search(pattern, html, re.IGNORECASE)

        cn, en = "", ""
        if match:
            content = match.group(1) or match.group(2) or ""
            parts = [p.strip() for p in content.split(",") if p.strip()]
            cn = parts[0] if parts else ""
            en = parts[1] if len(parts) > 1 else ""
            # 如果只是号码本身，视为无名称
            if cn == num:
                cn, en = "", ""

        self._write({"num": num, "cn": cn, "en": en})

    def _write(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # 静默日志
