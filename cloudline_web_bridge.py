
import http.client
import json
from urllib.parse import urlsplit

PREFIX = "/web/partner"
ALLOWED_GET = {"/api/v1/agents", "/api/v1/inbox"}
ALLOWED_POST = {
    "/api/v1/agents/register",
    "/api/v1/rooms",
    "/api/v1/rooms/respond",
    "/api/v1/messages",
    "/api/v1/agreements",
    "/api/v1/agreements/accept",
    "/api/v1/actions/check",
}

def handle(handler, method):
    parsed = urlsplit(handler.path)
    if not parsed.path.startswith(PREFIX + "/"):
        return False

    target = parsed.path[len(PREFIX):]
    if method == "GET":
        permitted = (
            target in ALLOWED_GET or
            (target.startswith("/api/v1/rooms/") and target.endswith("/events"))
        )
    else:
        permitted = target in ALLOWED_POST

    if not permitted:
        handler.reply(404, {"error": "Unsupported partner route"})
        return True

    origin = handler.headers.get("Origin")
    if origin and origin != "http://127.0.0.1:8787":
        handler.reply(403, {"error": "Origin not allowed"})
        return True

    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 4096:
        handler.reply(401, {"error": "Agent authentication required"})
        return True

    body = None
    if method == "POST":
        try:
            size = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            size = -1
        if not 0 < size <= 65536:
            handler.reply(413, {"error": "Invalid request size"})
            return True
        body = handler.rfile.read(size)

    conn = http.client.HTTPConnection("127.0.0.1", 8788, timeout=8)
    try:
        route = target + ("?" + parsed.query if parsed.query else "")
        headers = {"Authorization": authorization, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"

        conn.request(method, route, body=body, headers=headers)
        response = conn.getresponse()
        payload = response.read(1048576)
        handler.send_response(response.status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
    except (OSError, TimeoutError):
        handler.reply(502, {"error": "Partner API unavailable on port 8788"})
    finally:
        conn.close()

    return True
