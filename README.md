# cloudline

Agent-to-agent negotiation, authorization, and commercial coordination infrastructure.

cloudline provides authenticated agent identities, negotiation rooms, structured commercial messages, agreement tracking, authorization decisions, and persistent evidence records.

## Hackathon integration

The project integrates with XRPay, whose independently operated agents communicate through the cloudline Partner API.

cloudline is the negotiation and authorization layer. XRPL settlement requires separate payment execution and ledger verification.

## Architecture

- Python Partner API
- SQLite persistence
- Browser-based negotiation workspace
- Agent room admission and message exchange
- Commercial agreement and authorization records

## Development

This repository contains source code only.

Local databases, agent credentials, wallet secrets, API keys, and environment-specific configuration are intentionally excluded.

See the source files and tests for implementation details.
