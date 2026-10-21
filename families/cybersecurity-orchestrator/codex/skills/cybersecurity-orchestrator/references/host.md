# Host evidence

## Sysmon process-injection leads

Events 1 (process creation), 7 (image loading), 8 (remote thread), 10 (process access) and 25 (process tampering) offer different pivots. Event availability depends on the actual configuration and version; absent telemetry does not prove absent behavior.

Join process evidence by ProcessGUID and time rather than PID alone. A reused PID can refer to a different process. Remote-thread and process-access records have source and target identities: preserve that direction when reconstructing the sequence. Retain parent, command line, image, user and module context where captured.

GrantedAccess is a bitmask, not a label to match loosely. For example, `0x0040` is duplicate-handle access, whereas `0x0020` is VM-write access; a hexadecimal string containing a digit is not a semantic match. Parse and test the required bits, accounting for combined values. Handle access, a remote thread or a tampering signal is a lead requiring corroboration, not a confirmed malicious injection.

Primary sources: [Sysmon events and ProcessGUID](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon), [Windows process access rights](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights).

## Offline memory triage

Start from the supplied image's hash, acquisition context, operating system and symbol availability. Distinguish an unsupported image or missing symbols from an empty result. Record the actual framework version and resolve plugin names through its help; plugin paths in older examples can differ from current `windows.malware` namespaces.

Cross-check process-list and scan results, parent relationships, command lines, loaded modules, mapped memory and network artifacts where the image supports them. Account for terminated processes and incomplete capture. A `malfind` lead is not a malware verdict; inspect region permissions, content and process context and corroborate it with independent evidence.

Primary source: [Volatility Windows plugin reference](https://volatility3.readthedocs.io/en/latest/volatility3.plugins.windows.html). Offline triage does not require acquiring a new image, installing a driver or extracting credentials. No memory-forensics engine was qualified by this bundle's reference review.
