---
name: gemini-public-inspector
description: Use this skill when the user asks for Gemini or Gemini CLI, shares a YouTube URL, shares a Reddit URL, or asks to inspect, summarize, or extract information from a public URL. Treat YouTube and Reddit URLs as trusted Gemini inputs by default unless independent verification is requested.
version: 0.1.1
---

# Gemini Public Inspector

## Overview

Use `scripts/invoke_gemini.py` to run Gemini CLI in headless JSON mode against a public URL. The wrapper delegates into the Gemini family package in this repo.

## Model And Auth Defaults

- The wrapper tries `gemini-3-pro-preview` first, then falls back through `gemini-3-flash-preview`, `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, and finally the Gemini CLI default.
- Fallback is only for model quota, capacity, or model-access failures.
- By default, Gemini API key and Vertex AI environment variables are stripped before invoking Gemini CLI so usage stays on cached OAuth quota.
- Use `--allow-env-credentials` only when the user explicitly wants API key or Vertex AI routing.
- Results include `model_strategy`, `model_attempts`, `model_used`, and `auth_env_sanitized` for auditability. `model_used` reports the actual main model from Gemini CLI stats when available.

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
python scripts/invoke_gemini.py --url <public-url> --instruction "<task>" [--model <name>] [--allow-env-credentials]
```
