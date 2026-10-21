---
name: fedex-tracking
description: Retrieve public FedEx tracking status, travel history and shipment details, including multi-piece shipments, when ordinary web retrieval fails. Read-only; no signed-in account workflows or delivery changes.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Codex or Claude with browser tools that can read public rendered FedEx pages; no separate runtime or API key.
---

# FedEx Tracking

Use the tracking number or FedEx link supplied in the authorized task. Read the public tracking page; an existing accessible public tab may be used without entering the account area. Do not infer permission to search unrelated shipments.

## Reach the actual page

1. If ordinary retrieval already failed, use an available browser tool directly instead of repeating the same fetch. Follow that tool's installed instructions and documentation.
2. Inventory relevant open tabs. Match the official FedEx hostname and requested tracking identity, then select the **observed tab ID**. The same tracking page can include `trkqual` or other query parameters, so a URL-only lookup can miss an existing tab. Never hardcode a historical tab/browser ID.
3. If no matching tab exists, open the supplied official link once. For a bare number, use `https://www.fedex.com/fedextrack/?trknbr=<number>` through the browser. Verify the final official hostname and visible tracking number. Do not try grids of alternate URLs, locales, profiles or user agents.
4. Read the loaded state. Generic site navigation, a spinner, an HTTP 200 response, or a tracking number only in the URL is insufficient. Distinguish real shipment content from access denied, system down, CAPTCHA, invalid/no record and a browser integration error.

For Codex's `cua_repl`, see [references/browser.md](references/browser.md) when selecting a tab or recovering a DOM-read failure. Other agents should use their documented browser equivalent; this skill does not install or assume a particular browser integration.

## Read details without changing delivery

Use visible read-only controls such as **View more details**, **Shipment facts**, **Travel history**, and the **N Piece Shipment** table (labels vary by locale). Inspect the result after each action. A click can succeed even if the following DOM snapshot fails: check the rendered page before clicking again. Prefer accessible text; use screenshots when DOM extraction is unavailable. Read all relevant rows, including rows in an independently scrollable piece table, before claiming complete coverage.

Capture only fields needed by the request:

- Visible tracking number, master number when explicitly shown, piece count, and which piece is currently selected.
- Current status/exception text, latest scan location and timestamp, ETA or the literal no-estimate message. Read the active status; a progress bar's list of possible stages is not evidence of delivery.
- Travel events with their displayed date, time, location and selected time basis (for example Local Scan Time). Preserve ambiguous date strings; normalize only when locale or other page evidence establishes their meaning. Do not assign the computer's timezone to carrier scans.
- Shipment service, package weight, dimensions and units, total pieces, **total shipment weight**, packaging and other specifically requested shipment facts.
- Per-piece tracking IDs and statuses when relevant. Master and child pieces can disagree. Report the selected/master status separately; do not call the whole shipment delivered because some children are delivered. A date in a delivery-date column alone does not override an On the way status or an unavailable ETA.

Keep the field's original label, value and scope. Dimensions and Weight on the selected package must not be relabeled as dimensions or weight of every carton. Do not multiply a package weight by piece count to replace the explicitly shown total. Do not assume pounds and kilograms are separate packages. Missing fields remain unknown, not zero. Carrier dimensions/weights do not prove the merchandise inside a carton; comparisons with merchant specifications are explicitly labeled inferences.

## Evidence and failure reporting

Report the source link, observation time, retrieval method (live page, rendered screenshot, or user-supplied screenshot), selected tracking identity and material coverage gaps. Keep live facts distinct from older screenshots. If persistent evidence is needed, save it in the task's private record location, outside this skill and source repository. Treat tracking IDs and URLs, delivery addresses and screenshots as private shipment evidence; do not commit them into examples, logs or release bundles.

When blocked, preserve useful partial facts and state exactly which sections could not be read. A browser/CDP error means retrieval is incomplete, not that the package is delayed or missing. A FedEx system-down/access-denied page can return HTTP 200. Do not repeatedly retry it or treat it as a successful shipment response. An already accessible normal public tab can still be read; this is not permission to bypass the blocked context.

Do not log in, reuse/export cookies or tokens, replay hidden tracking endpoints, solve/bypass access challenges, or use stealth/proxy rotation. Do not click Manage delivery, change address/date, arrange collection, subscribe to updates, send messages, or create monitoring tasks under this read-only skill. If public access is unavailable, state the limitation and use explicitly supplied evidence with its provenance.

Official public tracking entry point: [FedEx tracking without login](https://www.fedex.com/en-nz/tracking.html). Page structure is dynamic; current visible content controls extraction, not historical labels or selectors.
