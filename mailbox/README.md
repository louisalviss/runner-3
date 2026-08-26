# Encrypted VPS Mailbox

Public transport for encrypted ChatGPT iPhone → VPS request envelopes.

Only ciphertext, request IDs, timestamps, and public reply keys are stored here. Plaintext commands and VPS results must never be committed to this repository.

The VPS polls `inbox.json`, downloads immutable request envelopes from `requests/`, decrypts them locally with its private key, routes only allowlisted flows, then writes an encrypted result to Runner3 Core durable state.
