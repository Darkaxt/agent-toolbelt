# Private sender routing and alias identity

The helper reads private sender routes automatically from
`%LOCALAPPDATA%/Tools/outlook-classic-mail/state/sender_routes.json`.
`OUTLOOK_CLASSIC_MAIL_SENDER_ROUTES` may select another private file.
Read that local file when its provider notes are relevant; never copy its real
addresses, domains, contact routes or credentials into source, tests, skill text,
release archives or public issue/commit bodies.

Schema (examples only; configure actual values exclusively in the private file):

```json
{"version": 1, "routes": [{"recipient_domain": "aliases.example", "send_using_account": "mailbox@example.net", "provider": "simplelogin"}]}
```

An original recipient domain is matched exactly, case-insensitively. It selects
an existing configured Outlook transport account for replies and forwards,
ahead of ordinary recipient-account inference. Explicit `--send-using-account`
overrides inference. Conflicting routes or a missing configured account require
resolution; do not silently pick another transport account. Results identify
`send_using_account_selection.source: private_recipient_domain` and the matched
alias addresses. Multiple possible aliases do not establish which visible
identity to use. Without a private file, normal account inference is unchanged.

## SimpleLogin

The transport mailbox and recipient-visible sender are different identities.
For mail received through SimpleLogin, reply to the original message's native
reverse alias using the configured transport mailbox. SimpleLogin relays it
with the corresponding alias as the visible sender. Preserve the native
reply destination; replacing it with the person's direct address bypasses this
route. Do not set an arbitrary `SentOnBehalfOfName`, spoof a From header or infer
successful alias delivery from the Outlook account selector.

For a different or new contact, find or create that contact's reverse alias
under the intended alias through the user's authorized SimpleLogin workflow.
A reverse alias belongs to one contact/alias pair: do not reuse another contact's
route, guess its address, or contact a no-reply endpoint for a different support
address. If the correct reverse alias is unavailable, retain the draft and
report the precise missing route; do not silently send directly. Apply the same
check to To, Cc and Bcc when alias identity is required. Forwarding to a direct
address does not preserve the alias automatically.

`alias_identity.delivery_verified: false` and
`alias_reverse_route_requires_verification` distinguish planned identity from
provider delivery. Saved sender verification proves only the transport account;
an end-to-end alias claim needs recipient-side/header evidence from an
explicitly authorized send. Do not send a test solely to validate this policy.

References: [reverse aliases](https://simplelogin.io/docs/getting-started/reverse-alias/)
and [sending from an alias](https://simplelogin.io/docs/getting-started/send-email/).
