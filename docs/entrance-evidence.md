# cloudline entrance decisions

Source: Hunter autonomy brain, cloudline intelligence lessons 001–010.
Decision: claimed identity, verified identity, and authority are distinct.

Source: Food City and Chainz evidence packages, 2026-09-21.
Decision: advertised payment support does not grant purchasing permission.

Source: GOSCE/cogDepot field notes.
Next requirement: unresolved questions have explicit state.

Source: Mastercard workshop IMG_2652, IMG_2657, IMG_2659.
Next requirement: authenticated participant registration and funded authority
must be checked using the supplied AP4M integration.

Current implementation:
- Local room-request storage and timestamped events.
- All participants remain unverified.
- No admission, agent conversations, or payments implemented yet.
- SQLite history is persistent but is not immutable ledger evidence.

Next:
- Authenticate each participant using the supplied integration.
- Bind verified identities to buyer/seller roles.
- Verify relevant authority before opening the negotiation.
- Recheck spending eligibility immediately before voucher signing.
- Do not accept client-supplied verified=true as evidence.
