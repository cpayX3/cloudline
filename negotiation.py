"""Persistent bilateral negotiation. No execution authority granted."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4


class Negotiation:
    REQUIRED = (
        "service", "resource", "network", "asset",
        "recipient", "amount_units", "expires_at"
    )

    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS negotiation_offers (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                proposer TEXT NOT NULL,
                parent_id TEXT,
                terms_json TEXT NOT NULL,
                terms_hash TEXT NOT NULL,
                state TEXT NOT NULL
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS negotiation_acceptances (
                offer_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                terms_hash TEXT NOT NULL,
                PRIMARY KEY (offer_id, actor)
            )
        """)
        self.db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            one_agreement_per_room
            ON negotiation_offers(room_id)
            WHERE state='AGREED'
        """)
        self.db.commit()

    def participant(self, room_id, actor):
        room = self.store.get_room(room_id)
        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")
        if actor not in (room["buyer"], room["seller"]):
            raise PermissionError("NOT_PARTICIPANT")
        return room

    def canonical(self, terms):
        if not isinstance(terms, dict):
            raise ValueError("Terms must be an object")
        if set(terms) != set(self.REQUIRED):
            raise ValueError("Missing or unexpected terms")
        for key in self.REQUIRED:
            value = terms[key]
            if key == "amount_units":
                if type(value) is not int or value <= 0:
                    raise ValueError("Invalid amount")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid field: " + key)
            elif len(value) > 2000:
                raise ValueError("Field too long: " + key)
            elif value != value.strip():
                raise ValueError("Noncanonical field: " + key)

        expiry = datetime.fromisoformat(terms["expires_at"])
        if expiry.tzinfo is None or expiry.utcoffset() is None:
            raise ValueError("Expiry requires timezone")
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("Offer already expired")

        encoded = json.dumps(
            terms, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False
        )
        return encoded, hashlib.sha256(encoded.encode()).hexdigest()

    def event(self, room_id, kind, payload):
        self.db.execute("""
            INSERT INTO events(room_id, occurred_at, kind, payload)
            VALUES (?, ?, ?, ?)
        """, (
            room_id, datetime.now(timezone.utc).isoformat(),
            kind, json.dumps(payload, sort_keys=True)
        ))

    def offer(self, room_id, actor, terms, parent_id=None):
        self.participant(room_id, actor)
        encoded, digest = self.canonical(terms)
        offer_id = "offer_" + uuid4().hex

        with self.db:
            existing = self.db.execute("""
                SELECT id, state FROM negotiation_offers
                WHERE room_id=? AND state IN ('ACTIVE','AGREED')
            """, (room_id,)).fetchall()

            if parent_id is None:
                if existing:
                    raise ValueError("Existing negotiation must be resolved")
            else:
                if len(existing) != 1 or existing[0] != (parent_id, "ACTIVE"):
                    raise ValueError("Counteroffer must reference active offer")
                previous = self.get(parent_id)
                if previous["proposer"] == actor:
                    raise PermissionError("Counteroffer requires counterparty")

            if parent_id:
                self.db.execute("""
                    UPDATE negotiation_offers SET state='SUPERSEDED'
                    WHERE id=? AND state='ACTIVE'
                """, (parent_id,))

            self.db.execute("""
                INSERT INTO negotiation_offers
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
            """, (
                offer_id, room_id, actor, parent_id,
                encoded, digest
            ))
            self.event(room_id, "COUNTEROFFER" if parent_id else "PROPOSAL", {
                "offer_id": offer_id,
                "parent_id": parent_id,
                "proposer": actor,
                "terms": terms,
                "terms_hash": digest
            })
        return offer_id

    def get(self, offer_id):
        row = self.db.execute("""
            SELECT id, room_id, proposer, parent_id,
                   terms_json, terms_hash, state
            FROM negotiation_offers WHERE id=?
        """, (offer_id,)).fetchone()
        if row is None:
            raise KeyError("Offer not found")
        keys = (
            "id", "room_id", "proposer", "parent_id",
            "terms", "terms_hash", "state"
        )
        result = dict(zip(keys, row))
        result["terms"] = json.loads(result["terms"])
        return result

    def accept(self, room_id, actor, offer_id, expected_hash):
        room = self.participant(room_id, actor)

        with self.db:
            offer = self.get(offer_id)
            if offer["room_id"] != room_id:
                raise PermissionError("Offer belongs to another room")
            if offer["state"] != "ACTIVE":
                raise ValueError("Offer is no longer active")
            if expected_hash != offer["terms_hash"]:
                raise ValueError("Terms hash mismatch")

            self.canonical(offer["terms"])

            self.db.execute("""
                INSERT INTO negotiation_acceptances
                VALUES (?, ?, ?)
            """, (offer_id, actor, expected_hash))
            self.event(room_id, "OFFER_ACCEPTED", {
                "offer_id": offer_id,
                "actor": actor,
                "terms_hash": expected_hash
            })

            accepted = {
                row[0] for row in self.db.execute("""
                    SELECT actor FROM negotiation_acceptances
                    WHERE offer_id=? AND terms_hash=?
                """, (offer_id, expected_hash))
            }

            agreed = accepted == {room["buyer"], room["seller"]}
            if agreed:
                self.db.execute("""
                    UPDATE negotiation_offers SET state='AGREED'
                    WHERE id=? AND state='ACTIVE'
                """, (offer_id,))
                self.event(room_id, "AGREEMENT_RECORDED", {
                    "agreement_id": offer_id,
                    "terms_hash": expected_hash,
                    "authority": "NOT_VERIFIED",
                    "payment": "NOT_SUBMITTED"
                })

        return {
            "status": "AGREED" if agreed else "AWAITING_COUNTERPARTY",
            "agreement_id": offer_id if agreed else None,
            "terms_hash": expected_hash
        }
