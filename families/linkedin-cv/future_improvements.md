# LinkedIn CV Future Improvements

## Proper RSC Text Parser For Edit-Form Blobs

Current request-only experience enrichment resolves description text from LinkedIn's `window.__como_rehydration__` stream, but the text reconstruction is still heuristic. This can leave minor artifacts such as soft-wrap splits (`rule\ns`) or other stream-boundary noise in long descriptions.

Why this should not be fixed with more regex duct tape:
- The edit-form payload is an RSC-style stream with labeled entries like `f:T...`, `10:T...`, `1a:[...]`.
- Reconstructing long text by joining raw fragments is structurally fragile.
- More ad-hoc cleanup rules will eventually create regressions on multilingual content or different profile layouts.

Recommended fix:
1. Implement a proper parser for the `window.__como_rehydration__` stream.
2. Tokenize label boundaries explicitly instead of treating the stream as generic newline-delimited text.
3. Resolve references like `$f` and `$10` against parsed label entries, preserving true paragraph boundaries.
4. Rebuild long text payloads from the parsed label graph rather than from regex-based substring trimming.

Scope:
- Primarily affects long-text fields resolved from edit-form routes, especially `experience.description`.
- Should be implemented without changing the request-only transport model.
