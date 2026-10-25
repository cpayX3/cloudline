# Compatibility decisions

GOSCE/cogDepot:
A response is not necessarily an answer. Answers leave questions unresolved
until the asking participant acknowledges a specific answer.

Flockx/Food City/Chainz:
Operator visibility and payment metadata are claims, not authorization.
Payload fields cannot change admission, acceptance, or spending state.

Transport differences:
Preserve original payloads and extract text from supported envelopes.
Unknown structured content remains visible as data.
No claim of universal protocol compatibility.

Current limits:
Internal methods only; sender identity must come from authenticated transport.
No model interpretation, external protocol delivery, or spending implemented.
Question resolution records participant acknowledgment, not objective truth.
Negotiation admission must remain separate from later spending authorization.
