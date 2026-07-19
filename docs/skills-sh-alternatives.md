# skills.sh alternative analysis

Generated: 2026-04-26

This report compares the public `agent-toolbelt` skills plus
`xsoar-development` against public skills.sh alternatives. The primary source
was the skills.sh search API:

```text
https://skills.sh/api/search?q=<query>&limit=100
```

Install counts are useful for triage, but the verdicts below are based on
feature-set fit for the same workflow. Local integration, fail-closed behavior,
and safety gates count as first-class features for local-first skills.

## Overall verdicts

| Module | Verdict | Recommendation |
| --- | --- | --- |
| `amazon-cli` | Strong direct competitors exist | Keep. Integrate product-API/no-captcha ideas only if they fit the local retail workflow. |
| `codex-thread-recall` | Strong direct competitors exist | Keep. Public recall tools are stronger for broad cross-session search; ours is stronger for current-thread episode/timeline/worklog semantics. |
| `everything-search` | No meaningful direct alternative found | Keep. Public hits are generic file/content search, not Windows Everything `es.exe`. |
| `antigravity-cli` | Partial alternatives exist | Keep as an isolated exact-model packet reviewer; use official Google skills for Gemini API/app development and `yt-dlp-ffmpeg` for public-video evidence preparation. |
| `linkedin-cv` | Partial alternatives exist | Keep, but position around local read-only capture/comparison. Public skills are better for generic profile advice. |
| `mail-domain-quarantine` | No meaningful direct alternative found | Keep. No public hit matched RDAP/blocklist-driven Outlook quarantine. |
| `yt-dlp-ffmpeg` | Strong direct competitors exist | Keep unless we want to depend on multiple public skills. Public skills cover pieces; ours combines download/probe/clip/remux/transcode with stricter safety. |
| `observable-reputation` | No meaningful direct alternative found | Keep. Public hits are mostly brand reputation, DNS admin, or general OSINT. |
| `outlook-classic-mail` | Partial alternatives exist | Keep. Public alternatives target cloud Outlook/M365 connectors; ours targets local Outlook Classic COM. |
| `whatsapp-wacli` | Strong direct competitors exist | Re-evaluate carefully. `steipete/clawdis/wacli` is a direct public local-wacli competitor. |
| `xsoar-development` | Partial alternatives exist | Keep. Public alternatives target live SOAR actions; ours targets content-development correctness. |

## 1. `amazon-cli`

Queries: `amazon`, `amazon product`, `amazon seller`, `asin`,
`amazon shopping`, `amazon reviews`, `amazon scraper`

API coverage: 150 unique hits. `amazon` returned exactly 100 and is therefore
capped; narrower follow-up queries were required.

Verdict: strong direct competitors exist.

Feature comparison: public alternatives cover Amazon seller operations,
affiliate product finding, BrowserAct-based Amazon product/review APIs, and
generic shopping workflows. They do not appear to replace our local Amazon CLI
workflow for exact model lookup, cross-market same-ASIN offers, managed retail
or business sessions, address consistency checks, VAT-sensitive offers, and
explicitly confirmed cart add/remove.

Recommendation: keep `amazon-cli`, but treat it as a local retail/product
research adapter rather than an Amazon seller skill. Candidate features worth
studying: BrowserAct-style stable product/review extraction, affiliate output
formats, and richer product research reports.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 954 | [`claude-office-skills/skills/amazon-seller`](https://skills.sh/claude-office-skills/skills/amazon-seller) | Strong seller/FBA alternative, not retail-session equivalent. |
| 280 | [`noemi-paradise/openclaw-skill-amazon-product-finder/amazon-product-finder`](https://skills.sh/noemi-paradise/openclaw-skill-amazon-product-finder/amazon-product-finder) | Affiliate product finder with ASIN support. |
| 113 | [`browser-act/skills/amazon-competitor-analyzer`](https://skills.sh/browser-act/skills/amazon-competitor-analyzer) | Competitor analysis; adjacent. |
| 113 | [`rocket-repos/agent-skills/amazon-associates`](https://skills.sh/rocket-repos/agent-skills/amazon-associates) | Affiliate workflow; adjacent. |
| 112 | [`nexscope-ai/amazon-skills/amazon-product-research`](https://skills.sh/nexscope-ai/amazon-skills/amazon-product-research) | Product research; adjacent/direct. |
| 73 | [`browser-act/skills/amazon-reviews-api-skill`](https://skills.sh/browser-act/skills/amazon-reviews-api-skill) | Review extraction alternative. |
| 70 | [`browser-act/skills/amazon-product-api-skill`](https://skills.sh/browser-act/skills/amazon-product-api-skill) | Structured product API extraction alternative. |
| 64 | [`jlave-dev/agent-skills/amazon-shopping`](https://skills.sh/jlave-dev/agent-skills/amazon-shopping) | Shopping/recommendation workflow; direct but browser-oriented. |
| 48 | [`browser-act/skills/amazon-product-search-api-skill`](https://skills.sh/browser-act/skills/amazon-product-search-api-skill) | Search extraction; direct. |
| 38 | [`browser-act/skills/amazon-asin-lookup-api-skill`](https://skills.sh/browser-act/skills/amazon-asin-lookup-api-skill) | ASIN lookup; direct partial. |

High-volume false-positive clusters: AWS service skills, Amazon Seller Central
PPC/listing micro-skills, Amazon video downloaders, and generic scrapers.

## 2. `codex-thread-recall`

Queries: `recall`, `thread recall`, `conversation memory`, `session search`,
`codex memory`, `claude codex sessions`

API coverage: 111 unique hits. No query hit the 100-row cap.

Verdict: strong direct competitors exist.

Feature comparison: public tools such as `arjunkmrm/recall`, CASS, Supermemory,
and Claude memory skills are broader than ours for cross-session, cross-agent,
BM25/semantic search. Our skill remains differentiated by exact current Codex
thread resolution, append-aware rollout indexing, episode/current-scope recall,
timeline/worklog extraction, mirror collapse, fail-closed behavior, and local
workspace opt-in scope.

Recommendation: keep `codex-thread-recall`. Integration candidates are BM25
ranking, phrase/boolean/prefix query syntax, CJK/trigram support, transcript
reader ergonomics, and broader optional importers. Do not deprecate unless we
are willing to give up current-thread-first semantic timeline/worklog behavior.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 7562 | [`obra/episodic-memory/remembering-conversations`](https://skills.sh/obra/episodic-memory/remembering-conversations) | High-adoption conversation memory workflow; not Codex rollout-specific. |
| 2886 | [`supermemoryai/claude-supermemory/super-search`](https://skills.sh/supermemoryai/claude-supermemory/super-search) | Cross-session memory search; strong adjacent. |
| 1760 | [`thedotmack/claude-mem/mem-search`](https://skills.sh/thedotmack/claude-mem/mem-search) | Persistent memory with timeline/detail retrieval; strong adjacent. |
| 1153 | [`steipete/clawdis/session-logs`](https://skills.sh/steipete/clawdis/session-logs) | Session log search/analyze workflow; direct adjacent. |
| 688 | [`dicklesworthstone/coding_agent_session_search/cass`](https://skills.sh/dicklesworthstone/coding_agent_session_search/cass) | Unified CLI/TUI across 11 agents; direct competitor for broad history search. |
| 412 | [`arjunkmrm/recall/recall`](https://skills.sh/arjunkmrm/recall/recall) | Direct competitor: BM25 full-text search across Claude Code and Codex sessions. |
| 328 | [`parcadei/continuous-claude-v3/recall-reasoning`](https://skills.sh/parcadei/continuous-claude-v3/recall-reasoning) | Memory reasoning; adjacent. |
| 285 | [`parcadei/continuous-claude-v3/recall`](https://skills.sh/parcadei/continuous-claude-v3/recall) | Semantic memory retrieval; adjacent. |
| 207 | [`volcengine/openviking/memory-recall`](https://skills.sh/volcengine/openviking/memory-recall) | Memory recall; adjacent. |
| 56 | [`gavdalf/total-recall/total-recall`](https://skills.sh/gavdalf/total-recall/total-recall) | Recall-oriented competitor. |

Notable false positives: Codex setup/plugin helpers, code context tools, goal
planners, and generic memory/project-memory prompts.

## 3. `everything-search`

Queries: `everything`, `file search`, `desktop search`, `windows search`,
`es.exe`

API coverage: 184 unique hits. `everything` returned exactly 100 and is capped,
but most of those are false positives from repo names.

Verdict: no meaningful direct alternative found.

Feature comparison: public hits mostly teach `fd`, `rg`, `rga`, RAG/document
search, or generic desktop automation. None found was a Windows Everything
`es.exe` wrapper with safe fallback behavior.

Recommendation: keep. Consider documenting how it differs from generic
file-search skills: this is global Windows filename/path discovery, not content
grep or RAG.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 152 | [`0xdarkmatter/claude-mods/file-search`](https://skills.sh/0xdarkmatter/claude-mods/file-search) | Generic `fd`/`rg` guidance; not Everything. |
| 84 | [`netresearch/file-search-skill/file-search`](https://skills.sh/netresearch/file-search-skill/file-search) | Strong generic file/content search decision guide; not Everything. |
| 332 | [`jezweb/claude-skills/google-gemini-file-search`](https://skills.sh/jezweb/claude-skills/google-gemini-file-search) | Gemini managed RAG; not local filesystem discovery. |
| 422 | [`elastic/agent-skills/elasticsearch-file-ingest`](https://skills.sh/elastic/agent-skills/elasticsearch-file-ingest) | File ingestion/search pipeline; not desktop filename search. |

Major false-positive cluster: `affaan-m/everything-claude-code/*` skills are
not Everything search skills.

## 4. `antigravity-cli`

The former `gemini-cli` public URL inspector was retired after its individual
account tier became unusable. `antigravity-cli` replaces it with a narrower
workflow: independent review of one explicit local packet through a
helper-owned, exact-model Antigravity runtime.

Verdict: partial alternatives exist. Official Google skills remain better for
Gemini API/application development, and public URL/video skills remain better
for evidence acquisition. This skill is differentiated by isolated OAuth and
runtime state, no general proxy surface, no tools, exact model attribution, and
fail-closed behavior on fallback.

Recommendation: keep for plan/design/code/evidence review. Route public-video
preparation to `yt-dlp-ffmpeg`, and do not restore broad URL inspection here.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 17274 | [`jimliu/baoyu-skills/baoyu-url-to-markdown`](https://skills.sh/jimliu/baoyu-skills/baoyu-url-to-markdown) | Strong public URL capture alternative; not Gemini-specific. |
| 15986 | [`jimliu/baoyu-skills/baoyu-danger-gemini-web`](https://skills.sh/jimliu/baoyu-skills/baoyu-danger-gemini-web) | Gemini Web API use; powerful but reverse-engineered and safety-sensitive. |
| 12618 | [`steipete/clawdis/summarize`](https://skills.sh/steipete/clawdis/summarize) | High-install summarization; adjacent. |
| 10637 | [`google-gemini/gemini-skills/gemini-api-dev`](https://skills.sh/google-gemini/gemini-skills/gemini-api-dev) | Official, better for Gemini API development. |
| 5878 | [`google-gemini/gemini-cli/code-reviewer`](https://skills.sh/google-gemini/gemini-cli/code-reviewer) | Official Gemini CLI repo skill, but code-review focused. |
| 2567 | [`google-gemini/gemini-skills/gemini-interactions-api`](https://skills.sh/google-gemini/gemini-skills/gemini-interactions-api) | Official, better for agentic Gemini API use. |
| 2343 | [`google-gemini/gemini-skills/gemini-live-api-dev`](https://skills.sh/google-gemini/gemini-skills/gemini-live-api-dev) | Official, better for live audio/video apps. |
| 1069 | [`sickn33/antigravity-awesome-skills/youtube-summarizer`](https://skills.sh/sickn33/antigravity-awesome-skills/youtube-summarizer) | YouTube transcript/summarization; adjacent. |
| 849 | [`steipete/clawdis/gemini`](https://skills.sh/steipete/clawdis/gemini) | Lightweight Gemini CLI one-shot guidance; partial direct competitor. |
| 682 | [`google/skills/gemini-api`](https://skills.sh/google/skills/gemini-api) | Gemini API guidance; adjacent. |

## 5. `linkedin-cv`

Queries: `linkedin`, `linkedin profile`, `profile optimizer`,
`linkedin automation`, `resume linkedin`

API coverage: 159 unique hits. `linkedin` returned exactly 100 and is capped.

Verdict: partial alternatives exist.

Feature comparison: public skills are better for generic LinkedIn profile
optimization, content generation, lead generation, and automation. Our skill is
different: local browser/profile snapshot capture, one explicit accessible
profile at a time, read-only defaults, and comparison against the user's own
profile/CV without profile scraping or engagement actions.

Recommendation: keep, but reposition away from generic LinkedIn advice. We can
integrate profile-section formulas and recruiter-visibility checklists from
public optimizer skills while retaining the stricter local capture model.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 1391 | [`paramchoudhary/resumeskills/linkedin-profile-optimizer`](https://skills.sh/paramchoudhary/resumeskills/linkedin-profile-optimizer) | Better for profile optimization advice; no local capture. |
| 1274 | `code.deepline.com/linkedin-url-lookup` | URL lookup; detail page 404 during inspection, but search result is relevant. |
| 721 | [`claude-office-skills/skills/linkedin-automation`](https://skills.sh/claude-office-skills/skills/linkedin-automation) | LinkedIn marketing/B2B automation; not safe local CV capture. |
| 708 | [`kostja94/marketing-skills/linkedin-posts`](https://skills.sh/kostja94/marketing-skills/linkedin-posts) | Content posting; adjacent. |
| 627 | [`claude-office-skills/skills/resume-tailor`](https://skills.sh/claude-office-skills/skills/resume-tailor) | Resume tailoring; adjacent. |
| 445 | [`schwepps/skills/linkedin-personal-branding`](https://skills.sh/schwepps/skills/linkedin-personal-branding) | Personal branding; adjacent. |
| 225 | [`onewave-ai/claude-skills/linkedin-sales-navigator-alt`](https://skills.sh/onewave-ai/claude-skills/linkedin-sales-navigator-alt) | Sales navigator alternative; not CV capture. |
| 164 | [`onewave-ai/claude-skills/linkedin-post-optimizer`](https://skills.sh/onewave-ai/claude-skills/linkedin-post-optimizer) | Post optimization; adjacent. |
| 110 | [`sickn33/antigravity-awesome-skills/linkedin-automation`](https://skills.sh/sickn33/antigravity-awesome-skills/linkedin-automation) | Automation; likely broader and riskier. |

False-positive clusters: unrelated performance profiling, CRM automation,
marketing automation, and social-post generation.

## 6. `mail-domain-quarantine`

Queries: `mail quarantine`, `quarantine`, `phishing email`,
`domain reputation`, `outlook quarantine`, `young domain`

API coverage: 120 unique hits. No capped query.

Verdict: no meaningful direct alternative found.

Feature comparison: public results include generic email triage, suspicious
email analysis, Outlook connectors, Gmail triage, domain research, and phishing
education. None matched the combined workflow of local Outlook Classic mailbox
scanning, RDAP young-domain checks, cached DNS blocklists, report rotation,
dry-run by default, and explicitly confirmed quarantine moves.

Recommendation: keep. Consider optional integration with suspicious-email
analysis language, but do not replace the module.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 16575 | [`googleworkspace/cli/gws-gmail-triage`](https://skills.sh/googleworkspace/cli/gws-gmail-triage) | Gmail triage, not Outlook quarantine. |
| 580 | [`claude-office-skills/skills/email-classifier`](https://skills.sh/claude-office-skills/skills/email-classifier) | Generic email classification; partial. |
| 569 | [`claude-office-skills/skills/suspicious-email-analyzer`](https://skills.sh/claude-office-skills/skills/suspicious-email-analyzer) | Suspicious email analysis; partial. |
| 427 | [`sickn33/antigravity-awesome-skills/email-systems`](https://skills.sh/sickn33/antigravity-awesome-skills/email-systems) | Email systems guidance; adjacent. |
| 312 | [`sickn33/antigravity-awesome-skills/outlook-automation`](https://skills.sh/sickn33/antigravity-awesome-skills/outlook-automation) | Outlook automation, not domain-risk quarantine. |
| 205 | [`membranedev/application-skills/microsoft-outlook`](https://skills.sh/membranedev/application-skills/microsoft-outlook) | Cloud Outlook connector; partial. |
| 108 | [`openclaudia/openclaudia-skills/domain-research`](https://skills.sh/openclaudia/openclaudia-skills/domain-research) | Domain research; partial. |
| 97 | [`aibtcdev/skills/reputation`](https://skills.sh/aibtcdev/skills/reputation) | On-chain agent reputation, false positive for domain reputation. |

## 7. `yt-dlp-ffmpeg`

Queries: `yt-dlp`, `ffmpeg`, `video downloader`, `media download`,
`audio extraction`

API coverage: 133 unique hits. No capped query.

Verdict: strong direct competitors exist.

Feature comparison: public skills cover yt-dlp download UX, YouTube download,
FFmpeg editing, audio extraction, and platform-specific downloaders. Our skill
is broader as a single local wrapper for public media download plus `ffprobe`,
clip, extract-audio, remux, and transcode, with explicit refusal for private,
authenticated, local-network, or cookie-based sources.

Recommendation: keep if we value a single safety-gated local media interface.
Consider integrating list-formats, playlist controls, URL detection, and
metadata-only modes from public downloader skills.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 2674 | [`digitalsamba/claude-code-video-toolkit/ffmpeg`](https://skills.sh/digitalsamba/claude-code-video-toolkit/ffmpeg) | Strong FFmpeg/video editing alternative. |
| 2490 | [`composiohq/awesome-claude-skills/youtube-downloader`](https://skills.sh/composiohq/awesome-claude-skills/youtube-downloader) | YouTube download; direct partial. |
| 937 | [`openai/skills/transcribe`](https://skills.sh/openai/skills/transcribe) | Transcription, not media download/edit. |
| 778 | [`lwmxiaobei/yt-dlp-skill/yt-dlp`](https://skills.sh/lwmxiaobei/yt-dlp-skill/yt-dlp) | Direct yt-dlp downloader competitor. |
| 732 | [`davila7/claude-code-templates/video-downloader`](https://skills.sh/davila7/claude-code-templates/video-downloader) | Video downloader; direct partial. |
| 732 | [`sundial-org/awesome-openclaw-skills/ffmpeg-video-editor`](https://skills.sh/sundial-org/awesome-openclaw-skills/ffmpeg-video-editor) | FFmpeg editor; direct partial. |
| 482 | [`yizhiyanhua-ai/media-downloader/media-downloader`](https://skills.sh/yizhiyanhua-ai/media-downloader/media-downloader) | Media downloader; direct partial. |
| 371 | [`mapleshaw/yt-dlp-downloader-skill/yt-dlp-downloader`](https://skills.sh/mapleshaw/yt-dlp-downloader-skill/yt-dlp-downloader) | Direct yt-dlp downloader competitor. |
| 335 | [`serpdownloaders/skills/m3u8-downloader`](https://skills.sh/serpdownloaders/skills/m3u8-downloader) | Protocol-specific downloader; partial. |

False-positive cluster: many site-specific video downloaders that are not
general replacements.

## 8. `observable-reputation`

Queries: `url reputation`, `domain reputation`, `observable`, `osint`,
`threat intel`, `passive dns`

API coverage: 108 unique hits. No capped query.

Verdict: no meaningful direct alternative found.

Feature comparison: public hits cover brand reputation, on-chain agent
reputation, OSINT recon, threat-intel feed analysis, DNS administration, and
pentest reconnaissance. None matched passive URL/domain/IP security reputation
classification with explicit no-submit/no-scan/no-upload guardrails and
provider-key-tolerant results.

Recommendation: keep. Potential improvements: add optional STIX/IOC feed
normalization ideas from threat-intel skills, but preserve passive-only safety.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 2520 | [`apify/agent-skills/apify-brand-reputation-monitoring`](https://skills.sh/apify/agent-skills/apify-brand-reputation-monitoring) | Brand reputation monitoring, not security observable reputation. |
| 2478 | [`ljagiello/ctf-skills/ctf-osint`](https://skills.sh/ljagiello/ctf-skills/ctf-osint) | CTF OSINT; adjacent. |
| 460 | [`kostja94/marketing-skills/brand-protection`](https://skills.sh/kostja94/marketing-skills/brand-protection) | Brand protection; adjacent. |
| 229 | [`danielmiessler/personal_ai_infrastructure/osint`](https://skills.sh/danielmiessler/personal_ai_infrastructure/osint) | OSINT workflow; adjacent. |
| 220 | [`alirezarezvani/claude-skills/senior-security`](https://skills.sh/alirezarezvani/claude-skills/senior-security) | Security review; adjacent. |
| 108 | [`openclaudia/openclaudia-skills/domain-research`](https://skills.sh/openclaudia/openclaudia-skills/domain-research) | Domain research; partial. |
| 97 | [`aibtcdev/skills/reputation`](https://skills.sh/aibtcdev/skills/reputation) | On-chain agent reputation; false positive. |
| 69 | [`jd-opensource/joysafeter/pentest-osint-recon`](https://skills.sh/jd-opensource/joysafeter/pentest-osint-recon) | Active recon orientation; not passive-only classification. |
| 42 | [`mukul975/anthropic-cybersecurity-skills/analyzing-threat-intelligence-feeds`](https://skills.sh/mukul975/anthropic-cybersecurity-skills/analyzing-threat-intelligence-feeds) | Threat feed normalization; adjacent. |

## 9. `outlook-classic-mail`

Queries: `outlook`, `microsoft outlook`, `mailbox`, `email automation`,
`outlook classic`

API coverage: 65 unique hits. No capped query.

Verdict: partial alternatives exist.

Feature comparison: public alternatives mostly use Membrane, Rube/Composio,
Graph/M365, IMAP/SMTP, or generic email automation. They are better for cloud
Outlook/M365 and cross-agent connector workflows. Our module is stronger for
local Windows Outlook Classic COM, existing desktop profiles, local metadata
cache, queued COM access, folder discovery, response lookup, drafts, forwards,
and explicit move/send confirmations.

Recommendation: keep. Document the distinction clearly. Consider a future
optional Graph/Membrane fallback only if local Outlook Classic is unavailable.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 850 | [`boomsystel-code/openclaw-workspace/imap-smtp-email`](https://skills.sh/boomsystel-code/openclaw-workspace/imap-smtp-email) | IMAP/SMTP email, but no SKILL.md available in detail page. |
| 312 | [`sickn33/antigravity-awesome-skills/outlook-automation`](https://skills.sh/sickn33/antigravity-awesome-skills/outlook-automation) | Rube/Composio Outlook automation; strong cloud alternative. |
| 205 | [`membranedev/application-skills/microsoft-outlook`](https://skills.sh/membranedev/application-skills/microsoft-outlook) | Membrane Outlook connector; strong cloud alternative. |
| 100 | [`sickn33/antigravity-awesome-skills/outlook-calendar-automation`](https://skills.sh/sickn33/antigravity-awesome-skills/outlook-calendar-automation) | Calendar-specific; adjacent. |
| 87 | [`composiohq/awesome-claude-skills/outlook-automation`](https://skills.sh/composiohq/awesome-claude-skills/outlook-automation) | Rube/Composio mirror; cloud alternative. |
| 73 | [`refly-ai/refly-skills/outlook`](https://skills.sh/refly-ai/refly-skills/outlook) | Outlook connector; partial. |
| 56 | [`probichaux/clawdskills/m365-mail`](https://skills.sh/probichaux/clawdskills/m365-mail) | Microsoft Graph mail CLI; partial. |
| 49 | [`pietz/skills/m365`](https://skills.sh/pietz/skills/m365) | M365 workflow; adjacent. |

## 10. `whatsapp-wacli`

Queries: `whatsapp`, `whatsapp automation`, `whatsapp business`,
`whatsapp local`, `whatsapp chat`

API coverage: 35 unique hits. No capped query.

Verdict: strong direct competitors exist.

Feature comparison: Gokapso and Claude Office skills are much stronger for
WhatsApp Business API, templates, flows, webhooks, automation, and debugging.
`steipete/clawdis/wacli` is a direct local `wacli` competitor for auth, sync,
chat search, message search, and confirmed sends. Our module remains
differentiated only if the curated adapter's structured JSON, JID resolution,
backfill behavior, and safety model are materially better than the public
`wacli` skill.

Recommendation: highest-priority deprecation/integration review. Compare our
adapter against `steipete/clawdis/wacli` directly. Keep ours only if we need
the local PN-vs-LID resolution, JSON normalization, backfill logic, and explicit
confirmation semantics.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 1263 | [`gokapso/agent-skills/integrate-whatsapp`](https://skills.sh/gokapso/agent-skills/integrate-whatsapp) | Strong WhatsApp Business/API integration suite. |
| 987 | [`gokapso/agent-skills/automate-whatsapp`](https://skills.sh/gokapso/agent-skills/automate-whatsapp) | Strong workflow automation suite. |
| 979 | [`steipete/clawdis/wacli`](https://skills.sh/steipete/clawdis/wacli) | Direct local `wacli` competitor. |
| 812 | [`claude-office-skills/skills/whatsapp-automation`](https://skills.sh/claude-office-skills/skills/whatsapp-automation) | WhatsApp Business automation; adjacent/direct depending use case. |
| 787 | [`gokapso/agent-skills/observe-whatsapp`](https://skills.sh/gokapso/agent-skills/observe-whatsapp) | WhatsApp delivery/debug observability; adjacent. |
| 172 | [`bellopushon/whatsapp-cloud-api/whatsapp-cloud-api`](https://skills.sh/bellopushon/whatsapp-cloud-api/whatsapp-cloud-api) | WhatsApp Cloud API; adjacent. |
| 92 | [`gokapso/agent-skills/whatsapp-messaging`](https://skills.sh/gokapso/agent-skills/whatsapp-messaging) | Messaging; partial. |
| 92 | [`membranedev/application-skills/whatsapp`](https://skills.sh/membranedev/application-skills/whatsapp) | Membrane WhatsApp connector; adjacent. |
| 68 | [`goncy/skills/whatsapp-web-js`](https://skills.sh/goncy/skills/whatsapp-web-js) | `whatsapp-web.js` guidance; local/web automation alternative. |
| 18 | [`smithery.ai/wacli`](https://skills.sh/smithery.ai/wacli) | Low-install wacli mirror/variant. |

## 11. `xsoar-development`

Queries: `xsoar`, `cortex xsoar`, `demisto`, `soar`, `xsoar content`

API coverage: 66 unique hits. No capped query. `demisto` returned zero hits.

Verdict: partial alternatives exist.

Feature comparison: `membranedev/application-skills/cortex-xsoar` is a live
connector/action-discovery skill for Cortex XSOAR. `alphaonedev/openclaw-graph`
is generic SOAR incident response. Neither replaces our public XSOAR content
development skill, which focuses on artifact shape, exported YAML, packaged
scripts, command references, CommonServerPython/demistomock guardrails, and
private overlay support.

Recommendation: keep. Optionally document Membrane as a complement for live
XSOAR operations, but do not replace content-development guidance.

Relevant candidates:

| Installs | Candidate | Fit |
| ---: | --- | --- |
| 68 | [`membranedev/application-skills/cortex-xsoar`](https://skills.sh/membranedev/application-skills/cortex-xsoar) | Live XSOAR connector/action workflow; partial alternative. |
| 17 | [`alphaonedev/openclaw-graph/soar`](https://skills.sh/alphaonedev/openclaw-graph/soar) | Generic SOAR playbook/orchestration guidance; adjacent. |
| 99 | [`snowflake-labs/subagent-cortex-code/cortex-code`](https://skills.sh/snowflake-labs/subagent-cortex-code/cortex-code) | "Cortex" false-positive cluster, not XSOAR. |
| 34 | [`jezweb/claude-skills/basalt-cortex`](https://skills.sh/jezweb/claude-skills/basalt-cortex) | Cortex false positive. |

Large false-positive cluster: `xsoar content` matches generic content marketing
skills, not Cortex XSOAR content packs.

## Shortlist for follow-up decisions

1. `whatsapp-wacli`: compare directly with `steipete/clawdis/wacli`. This is
   the clearest possible deprecation candidate if the public skill covers our
   adapter's structured local behavior.
2. `codex-thread-recall`: do not deprecate, but consider integrating public
   recall search strengths: BM25, phrase/boolean/prefix syntax, CJK/trigram
   support, and transcript reader ergonomics.
3. `yt-dlp-ffmpeg`: keep, but consider adding list-formats, URL detection, and
   metadata-only flows from public yt-dlp skills.
4. `amazon-cli`: keep, but study BrowserAct product/review API skills for more
   stable structured extraction patterns.
