
import hashlib
import hmac
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "runtime/partner_api.sqlite"

def handle(handler, path):
    if path != "/api/web/platform":
        return False

    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        handler.reply(401, {"error": "Platform key required"})
        return True

    key = authorization[7:]
    if not key or len(key) > 4096:
        handler.reply(401, {"error": "Invalid platform key"})
        return True

    if not DB.is_file():
        handler.reply(503, {"error": "Partner database unavailable"})
        return True

    connection = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True
    )
    connection.row_factory = sqlite3.Row

    try:
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        platform = None
        for row in connection.execute(
            "SELECT id, name, key_hash FROM platforms"
        ):
            if hmac.compare_digest(row["key_hash"], key_hash):
                platform = row
                break

        if platform is None:
            handler.reply(401, {"error": "Invalid platform key"})
            return True

        platform_id = platform["id"]

        agents = connection.execute(
            """
            SELECT id, name, merchant_ref, capabilities
            FROM agents
            WHERE platform_id=?
            ORDER BY created_at DESC
            """,
            (platform_id,)
        ).fetchall()

        rooms = connection.execute(
            """
            SELECT id, buyer, seller, purpose, status, created_at
            FROM rooms
            WHERE buyer IN (
                SELECT id FROM agents WHERE platform_id=?
            )
            OR seller IN (
                SELECT id FROM agents WHERE platform_id=?
            )
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (platform_id, platform_id)
        ).fetchall()

        def capabilities(value):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return []

        handler.reply(200, {
            "platform": {
                "id": platform_id,
                "name": platform["name"]
            },
            "agents": [
                {
                    "agent_id": a["id"],
                    "name": a["name"],
                    "merchant_ref": a["merchant_ref"],
                    "capabilities": capabilities(a["capabilities"])
                }
                for a in agents
            ],
            "rooms": [dict(r) for r in rooms]
        })
    finally:
        connection.close()

    return True
