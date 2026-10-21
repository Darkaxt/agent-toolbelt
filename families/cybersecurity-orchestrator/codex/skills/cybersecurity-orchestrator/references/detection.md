# Detection engineering

Use for Sigma conversion or YARA rule design. These are author-written interpretation notes, not copied vendor rules or tested engine integrations.

## Sigma

Treat a rule as a hypothesis tied to a log source and deployment environment. Confirm product/category/service, available fields and their normalization, backend and processing pipeline. A syntactically valid YAML file can still compile incorrectly for the target SIEM or refer to fields it never receives.

Use the installed converter's current help and supported backend/pipeline listing. Older `sigmac` and validator API examples are not portable instructions. Compare the generated query with actual event mappings and replay both a positive event and a plausible benign counterexample before deployment. Broad signer/path exclusions can hide the behavior being sought; justify each exclusion from the local evidence. A sample report saying "deployed" proves nothing about the current SIEM.

Primary source: [Sigma getting started](https://sigmahq.io/docs/guide/getting-started.html). Actual conversion, SIEM execution and rule deployment need their own verification; this bundle has not qualified a backend.

## YARA

Choose discriminating features from the supplied sample set, then test against both representative positives and a relevant benign corpus. Combine pattern evidence with appropriate file context; distinguish file offsets, virtual addresses and process-memory semantics. A byte string found in one sample is not evidence of family uniqueness. Evaluate loose alternatives, wildcards and expensive patterns against the target scanning workload.

Resolve the actual target engine and version before writing modules or syntax. Do not assume YARA and YARA-X feature compatibility. Compile and replay the complete rule in that engine before reporting it usable. Report corpus coverage and false positives; a match alone does not establish maliciousness.

Primary source: [YARA rule documentation](https://github.com/VirusTotal/yara/blob/master/docs/writingrules.rst). Sample execution or uploading private material is not part of offline rule design by default.
