"""Lightweight Mock API Server for Automated Printing System.

Provides endpoints to simulate external ERP / Serial / Product APIs:
- GET  /api/products    - Returns product master catalog
- GET  /api/unit-box    - Returns unit box label data (item_code, item_name, serial_code, retail_barcode, mrp_value, batch_code)
- GET  /api/b-box       - Returns B-box label data (serial_code, no_of_quantity, batch_no, barcode, item_code, item_name)
- GET  /api/m-box       - Returns M-box label data (serial_code, no_of_quantity, barcode, item_code, item_name)
- GET  /api/all         - Returns aggregated JSON containing all sections
- POST /production/jobs - Simulates serial allocation for RemoteSerialApiClient

Usage:
    python -m mock_api.mock_server [--port 8000]
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA_DIR = Path(__file__).resolve().parent


def _load_json(filename: str) -> list | dict:
    file_path = DATA_DIR / filename
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class MockApiHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: list | dict) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        endpoint_map = {
            "/api/products": "product_data.json",
            "/products": "product_data.json",
            "/api/unit-box": "unit_box.json",
            "/api/unit_box": "unit_box.json",
            "/unit-box": "unit_box.json",
            "/api/b-box": "b_box.json",
            "/api/b_box": "b_box.json",
            "/b-box": "b_box.json",
            "/api/m-box": "m_box.json",
            "/api/m_box": "m_box.json",
            "/m-box": "m_box.json",
            "/api/all": "mock_api.json",
            "/all": "mock_api.json",
        }

        if path in endpoint_map:
            data = _load_json(endpoint_map[path])
            # Optional filter by item_code
            target_code = query.get("item_code", [None])[0] or query.get("code", [None])[0]
            if target_code and isinstance(data, list):
                data = [item for item in data if item.get("item_code") == target_code]
            if "single" in query and isinstance(data, list) and data:
                data = data[0]
            self._send_json(200, data)
        elif path == "" or path == "/":
            self._send_json(200, {
                "service": "Automated Printing System Mock API",
                "endpoints": [
                    "/api/products",
                    "/api/unit-box",
                    "/api/b-box",
                    "/api/m-box",
                    "/api/all",
                ],
            })
        else:
            self._send_json(404, {"error": "Not Found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path in ("/production/jobs", "/api/production/jobs"):
            # Matches RemoteSerialApiClient.allocate schema
            product_id = payload.get("product_id", "101-1001")
            quantity = int(payload.get("quantity", 10))
            client_job_id = payload.get("client_job_id", "MOCK-JOB-001")
            serials = [f"SN{n:08d}" for n in range(1, quantity + 1)]
            response = {
                "serial_batch_id": f"BATCH-{client_job_id}",
                "job_id": client_job_id,
                "quantity": quantity,
                "product_id": product_id,
                "serials": serials,
            }
            self._send_json(201, response)
        else:
            self._send_json(404, {"error": "Endpoint not found"})


def run_server(port: int = 8000) -> None:
    server = HTTPServer(("0.0.0.0", port), MockApiHandler)
    print(f"Mock API server running on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock API Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()
    run_server(args.port)
