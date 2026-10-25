
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parent / "runtime" / "cpx_registry.sqlite"
DB.parent.mkdir(exist_ok=True)

def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS wallets (
        id TEXT PRIMARY KEY,
        address TEXT NOT NULL UNIQUE,
        verification_status TEXT NOT NULL DEFAULT 'unverified',
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        wallet_id TEXT,
        status TEXT NOT NULL DEFAULT 'paused',
        max_payment TEXT NOT NULL,
        daily_budget TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(wallet_id) REFERENCES wallets(id)
    )""")
    db.commit()
    return db

def now():
    return datetime.now(timezone.utc).isoformat()

def amount(value):
    from decimal import Decimal, InvalidOperation
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n <= 0 or n >= 1000000:
            raise ValueError()
        if n.as_tuple().exponent < -6:
            raise ValueError()
        return str(n)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid spending amount")

def handle_get(handler, path):
    if path not in ("/api/cpx/agents", "/api/cpx/wallets"):
        return False
    table = "agents" if path.endswith("agents") else "wallets"
    with connect() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM " + table + " ORDER BY created_at DESC"
        )]
    handler.reply(200, {"items": rows})
    return True

def handle_post(handler):
    if handler.path not in ("/api/cpx/agents", "/api/cpx/wallets"):
        return False

    if handler.headers.get("Origin") != "http://127.0.0.1:8787":
        handler.reply(403, {"error": "Origin rejected"})
        return True

    try:
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= 4096:
            raise ValueError("Invalid request size")
        if handler.headers.get("Content-Type", "").split(";")[0] != "application/json":
            handler.reply(415, {"error": "JSON required"})
            return True
        data = json.loads(handler.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError("JSON object required")

        with connect() as db:
            if handler.path.endswith("wallets"):
                address = str(data.get("address", "")).strip()
                if not re.fullmatch(r"r[1-9A-HJ-NP-Za-km-z]{24,34}", address):
                    raise ValueError("Invalid XRPL address format")
                existing = db.execute(
                    "SELECT * FROM wallets WHERE address=?", (address,)
                ).fetchone()
                if existing:
                    handler.reply(200, dict(existing))
                    return True
                record = {
                    "id": "wallet_" + uuid.uuid4().hex,
                    "address": address,
                    "verification_status": "unverified",
                    "created_at": now()
                }
                db.execute(
                    "INSERT INTO wallets VALUES (?,?,?,?)",
                    tuple(record.values())
                )
            else:
                name = str(data.get("name", "")).strip()
                kind = str(data.get("type", "Custom / API")).strip()
                if not 1 <= len(name) <= 40:
                    raise ValueError("Agent name must be 1-40 characters")
                if not 1 <= len(kind) <= 60:
                    raise ValueError("Invalid agent type")
                maximum = amount(data.get("max_payment"))
                daily = amount(data.get("daily_budget"))
                from decimal import Decimal
                if Decimal(maximum) > Decimal(daily):
                    raise ValueError("Per-payment limit exceeds daily budget")
                record = {
                    "id": "agent_" + uuid.uuid4().hex,
                    "name": name,
                    "type": kind,
                    "wallet_id": None,
                    "status": "paused",
                    "max_payment": maximum,
                    "daily_budget": daily,
                    "created_at": now()
                }
                db.execute(
                    """INSERT INTO agents
                    (id,name,type,wallet_id,status,max_payment,daily_budget,created_at)
                    VALUES (:id,:name,:type,:wallet_id,:status,:max_payment,
                            :daily_budget,:created_at)""",
                    record
                )
            db.commit()
        handler.reply(201, record)
    except sqlite3.Error:
        handler.reply(500, {"error": "Database operation failed"})
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        handler.reply(400, {"error": str(exc)})
    return True
