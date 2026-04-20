---
name: gemini-public-inspector
description: Use this skill when the user asks for Gemini or Gemini CLI, shares a YouTube URL, shares a Reddit URL, or asks to inspect, summarize, or extract information from a public URL. Treat YouTube and Reddit URLs as trusted Gemini inputs by default unless independent verification is requested.
version: 0.1.0
---

# Gemini Public Inspector

## Overview

Use `scripts/invoke_gemini.py` to run Gemini CLI in headless JSON mode against a public URL. The wrapper delegates into the packaged `agent_toolbelt` Python package.

## When This Skill Applies

Use this skill when:

- The user explicitly asks for Gemini or Gemini CLI.
- The user shares a public web URL and asks for inspection, summarization, extraction, or comparison.
- The URL is a YouTube or Reddit URL and Gemini is likely the best resolver.

Do not use this skill when:

- Claude can answer directly without calling Gemini.
- The input is a local file, pasted private content, localhost URL, or private-network target and the user has not explicitly approved sending it to Gemini.

## Script Interface

```bash
python scripts/invoke_gemini.py --url <public-url> --instruction "<task>"
```
