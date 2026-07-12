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
paper-derived template register sample.md -n api-design --out prompts/reg.md
# → {"status": "prompt_written", "prompt_file": "prompts/reg.md", "prompt_tokens": 8200}
```
`--out` writes the prompt as a plain-text file (`==== SYSTEM ====` / `==== USER ====`
sections) so a subagent can read and execute it without the prompt ever entering the
orchestrating agent's context. Omitting `--out` prints the full `{"system", "user"}`
JSON to stdout (legacy mode — floods the agent context, not recommended for orchestration).

### 2. Parse response
```bash
paper-derived template register sample.md -n api-design --parse response.json
# → parses LLM response, saves template, prints a compact registration summary
```
Commands whose parsed output is large (`input register`, `gen extract`, `gen generate`)
accept `-O <file>` to write the result to disk and print only a status summary.

## Agent Workflow Example

Registering an API design template with Claude Code:

```
1. paper-derived template register ./samples/api-design-v1.md -n api-design --out prompts/reg.md
   → {"status": "prompt_written", "prompt_file": "prompts/reg.md", "prompt_tokens": 8200}

2. Agent spawns a subagent that reads prompts/reg.md, executes it with its own LLM,
   and writes the raw response to responses/reg.json

3. paper-derived template register ./samples/api-design-v1.md -n api-design --parse responses/reg.json
   → {"status": "template_registered", "template_id": "api-design", "sections": 5, ...}
```

Full document generation pipeline:

```
preflight → extract → generate → validate → revise
(each step: build prompt → Agent calls LLM → parse response)
```

## Offline / Direct-Drive Mode

For offline environments with a local OpenAI-compatible provider (Ollama, vLLM,
LM Studio, llama.cpp server), the engine can call the LLM itself — no agent
orchestration, no orchestration context to overflow. Each call is a stateless
single prompt bounded by the session budget; interrupted runs resume from the
on-disk checkpoint.

```bash
# Execute any --out prompt file directly (replaces subagent execution)
paper-derived llm exec prompts/reg.md --api-base http://localhost:11434/v1 -m qwen2.5:14b -o responses/reg.json

# Drive the whole section-generation loop (next → prompt → call → parse → summarize)
paper-derived session run -s $SID --api-base http://localhost:11434/v1 -m qwen2.5:14b \
  --window 32768 -O output.md
```

`--window` shrinks the per-section budget to fit small context windows
(budget = min(current, window/2)). Parse failures retry with a format-repair
note; missing inputs and repeated failures stop with a report instead of
pushing through. See `skill/references/offline-mode.md` for the full offline
pipeline and small-model tuning table.

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
