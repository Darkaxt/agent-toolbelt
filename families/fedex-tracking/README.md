# FedEx Tracking

Read-only public FedEx tracking, travel history and shipment facts using the agent's existing browser tools. No runtime, API key or FedEx login is needed.

Copy `codex/skills/fedex-tracking` into the personal Codex, agents or Claude skill directory. Use the identical bundle in each environment. A browser tool capable of reading rendered pages is required when generic web retrieval cannot read FedEx.

The skill handles browser tab discovery, blocked responses, master/piece status differences and package versus total shipment weight. It does not manage accounts, deliveries or notifications.
