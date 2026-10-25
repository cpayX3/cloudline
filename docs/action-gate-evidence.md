# Action gate boundary

Field lesson: communication is not authority. Flockx operator claims and
conversational willingness must not authorize purchases. Blocking execution
must leave discussion available.

ActionGate is an internal service using RoomStore events. It defaults to
denial. It is not wired to a public HTTP route or payment SDK. Callers must
supply an authenticated actor, never trust a client-supplied identity.

The future trusted verifier must check current authority, revocation,
exact bilateral agreement, network, canonical asset, recipient, resource,
action, and budget. It must atomically reserve shared budget across
purchases and return a short-lived Permit bound to the full Action digest.
Tests use fixtures, not real Mastercard verification. Budget/revocation
tests check enforcement of adapter verdicts, not an implemented budget ledger.

A persistent unique reservation prevents repeating an identical action.
Crashes and uncertain submissions require reconciliation, not automatic retry.
Payment-adapter idempotency and settlement verification remain necessary.
Signing must use exactly the supplied Action.

SUBMITTED is not SETTLED. Delivery requires independently verified payment.
AP4M is separate from native XRPL cpX x402 Pay.

No real room is opened or authorized by installation.
No external agents are contacted or payments sent.
