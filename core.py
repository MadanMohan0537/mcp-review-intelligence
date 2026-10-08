"""Small dependency-free MCP 2025-11-25 stdio transport and localhost UI host."""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MAX_BYTES = 1_000_000


def validate(value, schema, path="arguments"):
    kinds = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool}
    kind = schema.get("type")
    if kind and (not isinstance(value, kinds[kind]) or kind in ("number", "integer") and isinstance(value, bool)):
        raise ValueError(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"Unknown fields in {path}: {sorted(set(value) - set(properties))}")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], f"{path}.{key}")
    if kind == "array":
        if len(value) > schema.get("maxItems", 1000):
            raise ValueError(f"{path} contains too many items")
        for item in value:
            validate(item, schema.get("items", {}), path + "[]")
    if kind == "string" and (len(value) > schema.get("maxLength", 100_000) or len(value) < schema.get("minLength", 0)):
        raise ValueError(f"{path} has an invalid length")
    if kind in ("integer", "number"):
        import math
        if not math.isfinite(value) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError(f"{path} is out of range")


def tool(name, description, properties, required=(), write=False):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False},
            "annotations": {"readOnlyHint": not write, "destructiveHint": False, "openWorldHint": write}}


def invoke(app, name, arguments):
    definition = next((t for t in app.tools if t["name"] == name), None)
    if not definition:
        raise ValueError("Unknown tool: " + str(name))
    validate(arguments, definition["inputSchema"])
    return app.call(name, arguments)


def serve_stdio(app):
    initialized = ready = False
    while True:
        line = sys.stdin.buffer.readline(MAX_BYTES + 1)
        if not line:
            break
        response = None
        request_id = None
        try:
            if len(line) > MAX_BYTES:
                while line and not line.endswith(b"\n"):
                    line = sys.stdin.buffer.readline(MAX_BYTES + 1)
                raise ValueError("Message too large")
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                raise ValueError("Invalid JSON-RPC request")
            method = request["method"]
            request_id = request.get("id")
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            if method == "notifications/initialized":
                ready = initialized
                continue
            if request_id is None:
                continue
            if method == "initialize":
                if initialized:
                    raise ValueError("Already initialized")
                if not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                    raise ValueError("initialize requires protocolVersion, capabilities and clientInfo")
                initialized = True
                result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                          "serverInfo": {"name": app.name, "version": "1.0.0"}}
            elif method == "ping":
                result = {}
            elif not ready:
                raise ValueError("Complete initialization before using tools")
            elif method == "tools/list":
                if params.get("cursor"):
                    raise ValueError("Unknown cursor")
                result = {"tools": app.tools}
            elif method == "tools/call":
                if not any(t["name"] == params.get("name") for t in app.tools):
                    raise ValueError("Unknown tool")
                try:
                    data = invoke(app, params["name"], params.get("arguments", {}))
                    result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}], "structuredContent": data, "isError": False}
                except (ValueError, KeyError, TypeError) as exc:
                    result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            else:
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
            if response is None:
                response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        except ValueError as exc:
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}
        except Exception:
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal error; inspect local storage configuration"}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def serve_web(app, port):
    expected = f"127.0.0.1:{port}"
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data if isinstance(data, bytes) else json.dumps(data).encode())
        def allowed(self):
            return self.headers.get("Host") == expected and self.headers.get("Origin", f"http://{expected}") == f"http://{expected}"
        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error": "Invalid host or origin"})
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if self.path not in files:
                return self.send(404, {"error": "Not found"})
            file, mime = files[self.path]
            return self.send(200, (Path(__file__).parent / "web" / file).read_bytes(), mime)
        def do_POST(self):
            if not self.allowed():
                return self.send(403, {"error": "Invalid host or origin"})
            if self.path != "/api/call":
                return self.send(404, {"error": "Not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BYTES:
                    raise ValueError("Request must be between 1 byte and 1 MB")
                body = json.loads(self.rfile.read(size))
                return self.send(200, invoke(app, body["name"], body.get("arguments", {})))
            except (ValueError, KeyError, TypeError) as exc:
                return self.send(400, {"error": str(exc)})
    print(f"{app.name}: http://{expected}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main(factory, default_port):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/store.sqlite")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    app = factory(args.db)
    if args.demo:
        app.demo()
    if args.collect:
        print(json.dumps(app.collect()))
    elif args.web:
        serve_web(app, args.port)
    else:
        serve_stdio(app)
