"""HTTP API.  GET /api/trips?date=YYYY-MM-DD   POST /api/trips"""
import json
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from service import ConflictError, TripStore, ValidationError, summarize


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/api/trips":
                return self._send(404, {"error": "not found"})
            raw = parse_qs(url.query).get("date", [None])[0]
            try:
                day = date.fromisoformat(raw) if raw else date.today()
            except ValueError:
                return self._send(400, {"error": "date: ожидается YYYY-MM-DD"})
            trips = store.for_day(day)
            self._send(200, {"date": day.isoformat(), "summary": summarize(trips), "trips": trips})

        def do_POST(self):
            if urlparse(self.path).path != "/api/trips":
                return self._send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"null")
                trip, created = store.add(payload)
            except json.JSONDecodeError:
                return self._send(400, {"error": "невалидный JSON"})
            except ValidationError as e:
                return self._send(422, {"error": str(e)})
            except ConflictError as e:
                return self._send(409, {"error": str(e)})
            self._send(201 if created else 200, {"created": created, "trip": trip})

        def log_message(self, *args):
            pass

    return Handler


def make_server(store, host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), make_handler(store))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    store = TripStore("data/trips.json")
    print(f"Сервер: http://127.0.0.1:{port}/api/trips")
    make_server(store, port=port).serve_forever()
