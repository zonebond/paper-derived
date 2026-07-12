# Paper Derived

Derive structured development documents from templates and input materials.

[中文文档](README.zh-CN.md)

## Overview

**Engine CLI + Agent Tools.** The engine does NOT call LLMs — Agent tools do.

```
┌──────────────────────────────────────────────┐
│  Agent Tools                                  │
│  Claude Code / OpenCode / Pi Agent / Codex   │
│  · Run paper-derived commands to get prompts  │
│  · Execute prompts with their own LLM        │
│  · Return LLM responses to paper-derived     │
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│  paper-derived (Engine CLI)                   │
│  · Build prompts                             │
│  · Parse LLM responses                       │
│  · Store templates / assets                  │
│  · No LLM calls, no API keys                 │
└──────────────────────────────────────────────┘
```

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Forward Registration** | Sample doc → analyze → generate four-module template prompt |
| **Reverse Generation** | Input materials + template → generate target document |
| **Template** | Four-module composite prompt (Extraction + Structure + Style + Validation) |
| **Input Asset** | Registered source material with summary and entity list |
| **DocumentTree** | Output artifact — recursive Section tree with ID, status, lineage |
| **Preflight** | Pre-generation check: does input cover all Section dependencies? |
| **Extract** | Pull structured fields from input; user can review and correct |
| **Validate** | Run template validation instruction against generated doc |

## Usage Pattern

Every command has two modes:

### 1. Build prompt
```bash
paper-derived template register sample.md -n api-design
# → {"system": "...", "user": "..."}
```
Agent executes this prompt with its own LLM and saves the response.

### 2. Parse response
```bash
paper-derived template register sample.md -n api-design --parse response.json
# → parses LLM response, saves template, outputs Template JSON
```

## Agent Workflow Example

Registering an API design template with Claude Code:

```
1. paper-derived template register ./samples/api-design-v1.md -n api-design
   → returns {"system": "...", "user": "..."}

2. Agent executes the prompt with its own LLM
   → saves LLM response to /tmp/response.json

3. paper-derived template register ./samples/api-design-v1.md -n api-design --parse /tmp/response.json
   → {"id": "api-design", "name": "API Design", "extraction_prompt": "...", ...}
```

Full document generation pipeline:

```
preflight → extract → generate → validate → revise
(each step: build prompt → Agent calls LLM → parse response)
```

## Install

### CLI

```bash
git clone <this-repo>
cd paper-derived
uv sync
uv run paper-derived --help
```

Or download a pre-built binary from Releases.

### Agent Skill

```bash
cd paper-derived/skill
./install.sh --adapter claude                        # Claude Code (user-level)
./install.sh --adapter claude --project-dir ./proj   # Claude Code (project-level)
./install.sh --adapter copilot --project-dir ./proj  # GitHub Copilot
./install.sh --adapter opencode                       # OpenCode
```

## Dependencies

- Python >= 3.10
- click >= 8.0
- Zero LLM SDK dependencies

## Project Structure

```
cli/
└── paper_derived/
    ├── cli.py              # CLI entry point
    ├── llm.py              # JSON parsing only (no LLM calls)
    ├── storage.py          # Local file storage
    ├── engine/             # Engine: build_*_prompt() + parse_*_result()
    ├── models/             # Data models: Template, DocumentTree, InputAsset ...
    ├── prompts/            # 7 prompt templates (.md)
    └── mcp/               # MCP Server (18 tools)

skill/
├── SKILL.md                # Agent orchestration manual
├── references/             # Reference docs
├── examples/               # Workflow examples
└── install.sh              # Multi-platform install script

scripts/
└── build-cli.sh            # PyInstaller build script
```
