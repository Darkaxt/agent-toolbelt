# Gemini Public Web Research Workspace

- Work only with public-web prompts supplied in the request, whether they are public URLs or question-first research tasks.
- Use `web_fetch` or `google_web_search` only.
- Do not use shell commands.
- Do not read or write local files.
- Do not access localhost, private IP ranges, or private-network hosts.
- For YouTube and Reddit URLs, answer directly from the accessible public page context.
- For question-first research tasks, start from the supplied question only and do not assume any prior Codex findings or selected sources.
- If access fails, say so plainly instead of guessing.
