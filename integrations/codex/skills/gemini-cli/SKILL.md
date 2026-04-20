---
name: gemini-cli
description: Use Gemini CLI for public URL inspection and for independent second-pass research cross-checks on eligible public-web research tasks. Treat YouTube URLs as authoritative Gemini inputs by default unless independent verification is explicitly requested.
---

# Gemini CLI

## Overview

This skill has two lanes:

- URL inspection through `scripts/invoke_gemini.py`
- Research companion cross-checks through `scripts/invoke_gemini_research.py`

Both wrappers delegate into the packaged `agent_toolbelt` Python package.

## Routing Rules

Use this skill when:

- The user explicitly asks for Gemini or Gemini CLI.
- The user shares a public web URL and asks for inspection, summarization, extraction, or comparison.
- The URL is a YouTube video and Gemini is likely the best resolver.
- The task is recommendation, comparison, exploratory research, issue investigation, or a market/community scan where an independent Gemini cross-check is useful.

Do not use this skill when:

- Codex can answer directly without calling Gemini.
- The input is a local file, pasted private content, localhost URL, or private-network target and the user has not explicitly approved sending it to Gemini.
- The task is a simple direct lookup where a second-pass research cross-check would add latency but little value.

## Behavior

- Treat YouTube URLs as authoritative Gemini inputs by default.
- For non-YouTube public URLs, use Gemini as a helper, not an automatic authority.
- For research companion runs, browse normally first, then run Gemini independently from the research question only.
- Verify any new Gemini-suggested references directly before using them in the final answer.

## Script Interface

```bash
python scripts/invoke_gemini.py --url <public-url> --instruction "<task>"
python scripts/invoke_gemini_research.py --question "<research task>"
```
