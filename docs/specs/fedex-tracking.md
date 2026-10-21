# FedEx public tracking skill

Authorization: user requested creation; clarified scope is public tracking and shipment details only.

## Requirements and acceptance

- R1: A discoverable `fedex-tracking` skill retrieves public FedEx status, travel history and shipment facts through available browser tools when generic retrieval fails. Verify against a real public page without login.
- R2: Preserve tracking identity, master/piece relationships, separate per-piece statuses, package versus shipment weights, units, dates/time basis and missing data. Verify the live multi-piece/details workflow and review hypothetical ambiguous/blocked cases.
- R3: Account login, delivery changes, notifications, purchases, unofficial API replay and access-control bypass are excluded. A retrieval failure is not a shipment status; HTTP 200 is insufficient proof.
- R4: Deploy identical validated v0.1.0 instruction bundles to personal Codex, agents and Claude roots. Verify content hashes and all referenced resources; no shipment identifiers or private evidence in the repository or package.
- R5: Commit the verified scoped changes and deliver an independently checked versioned local bundle. This is an instruction-only skill; no executable runtime, public software release or application configuration change is required.

## Execution and reconciliation

| Stage | Status | Requirements | Evidence |
| --- | --- | --- | --- |
| Public retrieval workflow and skill | COMPLETE | R1-R3 | Existing public tab selected by observed ID; details expanded; rendered shipment facts/history and mixed piece statuses read. Internally scrolling piece table exposed six of seven rows; full piece census was not claimed. Generic retrieval failed; anonymous browser returned an HTTP-200 denial page. |
| Deployment and delivery | COMPLETE | R4-R5 | Canonical and all installed skill validations, repository layout and portability checks pass. Local skills CLI discovers all 26 skills including FedEx. Codex/agents/Claude contents and independently opened v0.1.0 ZIP match source hashes. Verified scoped implementation committed; this final ledger closure is included in the same commit. |

Discovery: local copies contained no FedEx skill. Narrow skills.sh scout inspected ecommerce-shipping-rates (rate strategy) and parcel-tracking (mail-backed discovery); neither implements public FedEx shipment-fact retrieval. No third-party skill installed.

Design: instruction-only workflow reuses existing browser tools. No duplicate browser runtime, parser, credential store or scheduler. URL matching must tolerate extra query parameters; use an inventoried tab ID. A failed post-click DOM read requires state inspection before repeating an action.

Blockers: none identified. Tracked deferrals: none. Private live evidence stays outside the published bundle.

Behavioral reconciliation: reviewed mixed master/child delivery states, missing ETA with a populated delivery-date column, package/total-weight separation, ambiguous dates, HTTP-200 denial, and supplied-screenshot provenance. Each has an explicit extraction/reporting rule. Full browser reading succeeded through rendered screenshots after a post-click DOM error; no login or delivery mutation occurred.

Repository-wide publishing validation remains independently blocked by an existing non-generic absolute path in context-transfer/SKILL.md line 21. This is unrelated to this bundle; no public-release validation claim is made. Local discovery and the FedEx bundle's metadata/portability were verified directly. No remote synchronization or public publication is performed for this instruction-only local delivery.

Stage-closure design assessment: no material debt found within this scope; the browser workflow needs no additional runtime, parser, credential store or background service.

Final reconciliation: R1-R5 satisfied for the public-only instruction skill. No required blockers or deferrals remain. The signed cleanup transaction removed all exact temporary probe artifacts; durable private verification and the requested versioned deliverable are retained outside source. No live account, automation or delivery settings were changed.
