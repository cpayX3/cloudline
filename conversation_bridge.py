"""cloudline format compatibility.
Internal use only: authenticated sender supplied by the transport adapter.
External payloads are data, never authority or executable instructions.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

def normalize(payload):
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(raw.encode("utf-8")) > 65536:
        raise ValueError("Message exceeds 64 KiB")

    texts = []

    def extract(value, depth=0):
        if depth > 12:
            raise ValueError("Message nesting exceeds limit")
        if isinstance(value, str):
            if value.strip():
                texts.append(value.strip())
            return
        if isinstance(value, list):
            for item in value:
                extract(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        if isinstance(value.get("text"), str):
            extract(value["text"], depth + 1)
            return
        # Known text-bearing envelopes. Never execute embedded tools.
        for field in ("parts", "content", "message", "result"):
            if field in value:
                extract(value[field], depth + 1)
                if texts:
                    return

    parsed = payload
    source_format = "structured"
    if isinstance(payload, str):
        source_format = "text"
        try:
            parsed = json.loads(payload)
            source_format = "json_string"
        except ValueError:
            pass
    extract(parsed)

    if texts:
        text = "\n\n".join(texts)
        handling = "TEXT_EXTRACTED"
    else:
        text = json.dumps(parsed, ensure_ascii=False, indent=2)
        handling = "STRUCTURED_DATA_PRESERVED"

    return {
        "original": payload,
        "text": text,
        "source_format": source_format,
        "handling": handling,
        "interpretation": "NOT_YET_INTERPRETED"
    }

class ConversationBridge:
    def __init__(self, store):
        self.store = store

    def _participant(self, room_id, sender):
        room = self.store.get_room(room_id)
        if room["state"] != "OPEN":
            raise PermissionError("Negotiation admission is not complete")
        if sender not in (room["buyer"], room["seller"]):
            raise PermissionError("Not a room participant")

    def _write(self, room_id, kind, payload):
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO events
                   (room_id, occurred_at, kind, payload) VALUES (?, ?, ?, ?)""",
                (room_id, datetime.now(timezone.utc).isoformat(),
                 kind, json.dumps(payload, ensure_ascii=False))
            )

    def question(self, room_id, question_id):
        events = self.store.events(room_id)
        for event in events:
            p = event["payload"]
            if event["kind"] == "QUESTION" and p["message_id"] == question_id:
                resolved = any(
                    e["kind"] == "QUESTION_RESOLVED"
                    and e["payload"]["question_id"] == question_id
                    for e in events
                )
                return p, resolved
        raise ValueError("Question does not belong to this room")

    def receive(self, room_id, sender, payload, action="message",
                question_id=None):
        self._participant(room_id, sender)
        if action not in ("message", "ask", "answer"):
            raise ValueError("Unsupported conversational action")
        message = normalize(payload)
        if not message["text"].strip():
            raise ValueError("Empty message")
        if action == "answer":
            question, resolved = self.question(room_id, question_id)
            if resolved:
                raise ValueError("Question is already resolved")
            if question["sender"] == sender:
                raise PermissionError("Answer must come from the counterparty")
        elif question_id is not None:
            raise ValueError("Only answers may reference a question")

        message_id = "msg_" + uuid4().hex
        message.update({
            "message_id": message_id, "sender": sender,
            "action": action, "question_id": question_id
        })
        kind = {"message": "MESSAGE", "ask": "QUESTION",
                "answer": "ANSWER"}[action]
        self._write(room_id, kind, message)
        return message_id

    def resolve(self, room_id, sender, question_id, answer_id):
        self._participant(room_id, sender)
        question, resolved = self.question(room_id, question_id)
        if question["sender"] != sender:
            raise PermissionError("Only the asking participant may resolve")
        if resolved:
            raise ValueError("Question is already resolved")
        answer = next((
            e for e in self.store.events(room_id)
            if e["kind"] == "ANSWER"
            and e["payload"]["message_id"] == answer_id
            and e["payload"]["question_id"] == question_id
        ), None)
        if answer is None:
            raise ValueError("Matching answer required")
        self._write(room_id, "QUESTION_RESOLVED", {
            "sender": sender, "question_id": question_id,
            "answer_id": answer_id,
            "text": "Asking participant marked this question resolved."
        })
