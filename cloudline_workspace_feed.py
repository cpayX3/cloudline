
"""Local-only, database-driven cloudline negotiation feed."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

DB = Path(__file__).resolve().parent / "runtime" / "partner_api.sqlite"


def decode(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def get_rooms():
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row

        rooms = db.execute("""
            SELECT r.id, r.buyer, r.seller, r.purpose,
                   r.status, r.created_at,
                   b.name AS buyer_name,
                   s.name AS seller_name
            FROM rooms r
            LEFT JOIN agents b ON b.id = r.buyer
            LEFT JOIN agents s ON s.id = r.seller
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT 200
        """).fetchall()

        result = []

        for room in rooms:
            events = [
                {
                    **dict(event),
                    "payload": decode(event["payload"])
                }
                for event in db.execute("""
                    SELECT id, room_id, sender, kind, payload,
                           created_at
                    FROM events
                    WHERE room_id = ?
                    ORDER BY created_at, id
                """, (room["id"],))
            ]

            agreements = [
                {
                    **dict(agreement),
                    "terms": decode(agreement["terms"])
                }
                for agreement in db.execute("""
                    SELECT * FROM agreements
                    WHERE room_id = ?
                """, (room["id"],))
            ]

            result.append({
                "room": {
                    key: room[key]
                    for key in (
                        "id", "buyer", "seller", "purpose",
                        "status", "created_at"
                    )
                },
                "buyer_name": room["buyer_name"] or room["buyer"],
                "seller_name": room["seller_name"] or room["seller"],
                "events": events,
                "agreements": agreements
            })

        return result


def install(handler_class):
    original_get = handler_class.do_GET

    def workspace_get(self):
        if urlparse(self.path).path != "/api/workspace/rooms":
            return original_get(self)

        if not self.valid_host():
            return self.reply(403, {"error": "Local access only"})

        try:
            rooms = get_rooms()
            return self.reply(200, {
                "source": "partner_api.sqlite",
                "mode": "LOCAL_LIVE",
                "room_count": len(rooms),
                "rooms": rooms
            })
        except Exception as error:
            print(
                "CLOUDLINE WORKSPACE ERROR:",
                repr(error),
                flush=True
            )
            return self.reply(
                500, {"error": "Workspace feed unavailable"}
            )

    handler_class.do_GET = workspace_get
