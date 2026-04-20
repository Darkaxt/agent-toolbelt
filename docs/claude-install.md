# Claude integration install

## Package install

Install the package from a clone:

```bash
pip install -e .
```

## Marketplace install

The Claude marketplace bundle lives under:

`integrations/claude/marketplaces/agent-toolbelt-local`

Validate the marketplace and plugins:

```bash
claude plugins validate integrations/claude/marketplaces/agent-toolbelt-local
claude plugins validate integrations/claude/marketplaces/agent-toolbelt-local/plugins/gemini-public-inspector
claude plugins validate integrations/claude/marketplaces/agent-toolbelt-local/plugins/everything-search
claude plugins validate integrations/claude/marketplaces/agent-toolbelt-local/plugins/uvrun-python
claude plugins validate integrations/claude/marketplaces/agent-toolbelt-local/plugins/yt-dlp-ffmpeg
```

Add the marketplace and install plugins from the clone:

```bash
claude plugins marketplace add integrations/claude/marketplaces/agent-toolbelt-local --scope user
claude plugins install gemini-public-inspector@agent-toolbelt-local --scope user
claude plugins install everything-search@agent-toolbelt-local --scope user
claude plugins install uvrun-python@agent-toolbelt-local --scope user
claude plugins install yt-dlp-ffmpeg@agent-toolbelt-local --scope user
```

## Plugin notes

- The Claude Gemini plugin stays URL-focused in v1.
- The plugin wrappers also bootstrap the local `src/` tree from the checkout.
- Use the package install and marketplace clone from the same checkout to keep behavior aligned.
