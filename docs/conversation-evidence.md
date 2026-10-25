# Conversation boundary

Hunter brain: communication is not authority.
Implementation: greetings require OPEN room state and participant membership.

Hunter field observations: claimed action is not observed action.
Implementation: UI renders stored backend events; no generated sample transcript.

GOSCE/cogDepot: a response does not necessarily answer a question.
Next increment: explicit question IDs and resolution acknowledgments.

Current integration boundary:
record_greeting is an internal method, not an authenticated HTTP endpoint.
The eventual adapter must supply authenticated identity.
No production admission bypass is implemented.
Test OPEN state is confined to an in-memory test database.
