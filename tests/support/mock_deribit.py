"""Deterministic exchange stub used only by the Compose CI scenario."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            payload = {"status": "ok"}
        elif parsed.path == "/api/v2/public/get_index_price":
            index = parse_qs(parsed.query).get("index_name", [None])[0]
            prices = {"btc_usd": 65000.12, "eth_usd": 3000.34}
            if index not in prices:
                self.send_error(400)
                return
            payload = {"jsonrpc": "2.0", "result": {"index_price": prices[index]}}
        else:
            self.send_error(404)
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
