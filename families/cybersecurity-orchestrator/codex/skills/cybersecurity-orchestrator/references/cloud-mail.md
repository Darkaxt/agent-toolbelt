# Cloud and mail evidence

## CloudTrail reconstruction

Record account, region, trail/event-store coverage, time range and event category before building a timeline. CloudTrail event history and LookupEvents are a recent regional management-event view, not a complete history of data access. Missing S3 GetObject in that view does not prove no object access. Data events require appropriate collection and retrieval; distinguish unavailable evidence from a negative result.

Preserve event ID, event time, identity/session context, event source/name, region, resources, source address and error fields. Deduplicate copied event records by event ID while preserving provenance and recording conflicting copies. Sort by event time with timezone explicit; ingestion order is not necessarily activity order. A source address or shared session attribute alone is not actor attribution.

Primary source: [CloudTrail event-history coverage](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html). An offline export can support reconstruction without logging into an account or changing credentials.

## Phishing headers

Retrieve the actual message and full headers through the installed mail workflow when authorized; screenshots alone rarely show the full transport evidence. Keep displayed sender, envelope sender, Reply-To, message IDs, recipient and visible destinations distinct. Compare SPF/DKIM results with the authenticated identity and DMARC alignment rather than treating a single "pass" as legitimacy.

Authentication-Results and Received lines can be supplied by an attacker. Establish the trusted receiving boundary before relying on them. The bottom-most Received line is not automatically the sender's genuine origin. Preserve original evidence and distinguish a display-name impersonation from authenticated domain identity and compromise of a legitimate sender.

Primary source: [Authentication-Results trust boundary, RFC 8601](https://www.rfc-editor.org/rfc/rfc8601.html). Do not submit message contents or URLs to public scanning services, purge mail or reset an account merely because a reference recommends it; those are separate actions governed by the user's request.
