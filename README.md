# Council of LLMs

A suite of multi-LLM tools for [Open WebUI](https://github.com/open-webui/open-webui) featuring parallel querying, peer evaluation, and intelligent synthesis.

## Tools

This project provides four complementary tools:

1. **Council of LLMs** - Full pipeline with anonymous peer review and synthesis
2. **LLM Writer's Room** - Creative writing variant with human-like voice optimization
3. **LLM Roundtable** - Query multiple models simultaneously, see all responses
4. **LLM En Banc** - Have multiple models evaluate a response

## Overview

### Council of LLMs

The full Council enables consultation across multiple language models with unbiased peer evaluation and intelligent synthesis. Inspired by academic peer review processes, the system:

1. **Distributes** queries to multiple LLMs simultaneously
2. **Anonymizes** responses to prevent evaluation bias
3. **Evaluates** each response through anonymous peer review by all models
4. **Synthesizes** a final answer from the collective insights

```
User Query
    |
    v
[Query Distribution] --> Model A, Model B, Model C (parallel)
    |
    v
[Anonymization] --> Response A, Response B, Response C
    |
    v
[Anonymous Evaluation] --> All models evaluate all responses
    |
    v
[Score Aggregation] --> Rank responses by weighted scores
    |
    v
[Synthesis] --> Lead model creates final answer
    |
    v
User receives synthesized result with optional transparency
```

## Current Status

**Version**: 0.6.1 (Stability & Performance Update)
**Status**: Fully Functional - Production Ready
**Last Updated**: 2025-12-15

### What's Working

**Core Features**:
- ✅ Multi-model query distribution (parallel)
- ✅ Response anonymization with blind peer review
- ✅ Real model-based evaluations with detailed reasoning
- ✅ Score parsing and aggregation
- ✅ Real LLM-powered synthesis
- ✅ Streaming output support with progress indicators
- ✅ Configurable prompting techniques
- ✅ De-anonymized user output (transparent after evaluation)
- ✅ Detailed error messages

**Recent Improvements** (v0.6.1):
- ✅ **Separate evaluation models**: Configure different models for queries vs. evaluations
- ✅ **Extended timeouts**: Query and evaluation timeouts now support up to 360 seconds (6 minutes)
- ✅ **Fixed reverse mapping bug**: Resolved issue causing empty content in Individual Model Responses
- ✅ **Accurate evaluation counts**: Fixed evaluation progress display when using separate evaluator models
- ✅ **Anti-slop patterns**: Added warnings against rhetorical negations ("Not X, but Y") in creative writing
- ✅ **Verbalized sampling support**: Infrastructure for multiple response variants (experimental)

**Features from v0.6.0**:
- ✅ Synthesis mode toggle (full/highest_rated/none)
- ✅ Token usage tracking per model and phase
- ✅ Cost estimation with per-model pricing
- ✅ Configurable synthesis filtering (top-N, min-score threshold)

### LLM Writer's Room

A creative writing-focused variant of the Council system, specifically designed to produce human-like, emotionally resonant prose while avoiding common LLM artifacts. Uses the same peer review architecture but with creative writing-specific evaluation criteria:

- **Voice Authenticity** - Human-like voice, avoids LLM artifacts
- **Emotional Resonance** - Shows emotions through action/detail, not abstract statements
- **Originality & Risk-Taking** - Fresh metaphors, avoids clichés and safe choices
- **Style Consistency** - Maintains unified voice and matches creative brief
- **Narrative Coherence** - Clear structure without forced tidy endings
- **LLM Artifact Avoidance** - Explicitly penalizes AI-sounding patterns

Perfect for:
- Fiction writing (scenes, chapters, short stories)
- Creative copy with personality
- Dialogue that sounds natural
- Poetry and literary prose
- Any writing that needs to feel human-authored

See [Writer's Room Documentation](council-pipeline/WRITERS_ROOM_README.md) for details.

### LLM Roundtable

Query multiple models in parallel and see all responses side-by-side. Perfect for:
- Comparing different model perspectives
- Getting diverse creative ideas
- Seeing how models handle the same question

### LLM En Banc

Have multiple models evaluate and score a response. Great for:
- Quality-checking AI-generated content
- Getting peer review on answers
- Fact-checking and completeness assessment

## Quick Start

### Prerequisites

- Python 3.11+
- Open WebUI running with Pipelines support
- At least 2-3 LLM models configured in Open WebUI

### Installation

You can install using either the **automated script** (recommended) or **manual import**.

#### Option A: Automated Installation (Recommended)

Use the `update_functions.py` script to automatically install and update all tools:

```bash
cd council-pipeline/

# Set your Open WebUI credentials
export OPENWEBUI_URL="https://your-openwebui-instance.com"
export OPENWEBUI_API_KEY="sk-your-api-key"

# Install/update all functions
python update_functions.py
```

The script will:
- Automatically create/update all Council functions in Open WebUI
- Preserve your existing Valve configurations
- Show which functions were created vs. updated
- Handle errors gracefully with clear messages

**Credential Options**: See [`.env.example`](.env.example) for flexible credential management (direct env vars, 1Password CLI, AWS Secrets Manager, etc.)

#### Option B: Manual Import

Choose which tools you want to install:

**Council of LLMs (Full Pipeline)**:
1. Download `council_orchestrator.json` from `council-pipeline/`
2. Go to Admin Panel → Functions → Import Function
3. Upload the JSON file
4. Configure `MODELS_TO_QUERY` in Valves
5. Select "Council of LLMs" from model dropdown

**Writer's Room (Creative Writing)**:
1. Download `writers_room_orchestrator.json` from `council-pipeline/`
2. Import via Admin Panel → Functions
3. Configure valves for creative writing preferences
4. Select "LLM Writer's Room" from model dropdown

**LLM Roundtable (Parallel Query)**:
1. Download `llm_roundtable.json` from `council-pipeline/`
2. Import via Admin Panel → Functions
3. Configure `MODELS_TO_QUERY` valve
4. Use for parallel model comparison

**LLM En Banc (Response Evaluation)**:
1. Download `llm_en_banc.json` from `council-pipeline/`
2. Import via Admin Panel → Functions
3. Configure evaluator models
4. Paste responses to evaluate

**Complete Suite**:
- Download `council_llms_complete.json` to install all tools at once

### Updating Existing Installations

To update to the latest version:

**Using update_functions.py** (Recommended):
```bash
cd council-pipeline/
python update_functions.py
```

This automatically updates all functions while preserving your Valve configurations.

**Manual Update**:
1. Download the latest JSON files from `council-pipeline/`
2. In Open WebUI: Admin Panel → Functions → [Function Name] → Delete
3. Import the new JSON file
4. Reconfigure your Valves (they will be reset)

**Note**: The automated script preserves your settings; manual import requires reconfiguration.

### Default Configuration

All tools default to:
```
MODELS_TO_QUERY = gpt-5.1,o3,anthropic/claude-sonnet-4.5
```

Change this to match model IDs available in your Open WebUI instance.

## Features

### Core Functionality

- **Multi-Provider Support**: Works with any models configured in Open WebUI (OpenAI, Anthropic, Google, Ollama, etc.)
- **Anonymous Peer Review**: Responses are anonymized before evaluation to prevent bias
- **Configurable Evaluation**: 4 criteria with adjustable weights (accuracy, clarity, completeness, relevance)
- **Intelligent Synthesis**: Lead model synthesizes insights from all responses
- **Streaming Support**: Real-time output as the Council processes your query

### v0.5.0 Enhancements

- **Configurable Prompting Techniques**: 11 toggleable techniques for queries, evaluations, and synthesis
- **Detailed Evaluation Reasoning**: Multi-paragraph analysis instead of brief summaries
- **All Responses to Synthesis**: Synthesizer learns from both successes and failures
- **De-Anonymized Output**: See which model gave which response after evaluation
- **Better Error Messages**: Know exactly which models succeeded/failed and why

### Configuration Options

All tools are configured through **Valves** in the Open WebUI Admin Panel (Settings → Functions → [Function Name] → Valves).

#### Council of LLMs & Writer's Room Valves

**Model Configuration**:
- `MODELS_TO_QUERY`: Comma-separated model IDs (default: `gpt-5.1,o3,anthropic/claude-sonnet-4.5`)
- `EVALUATION_MODELS`: Models for evaluation (empty = use same as query models)
- `LEAD_SYNTHESIZER`: Synthesis model (`auto` for highest-scoring, or specific model ID)
- `MIN_MODELS_REQUIRED`: Minimum successful responses needed (default: 3)

**Evaluation Criteria Weights** (must sum to 1.0):

*Council (Technical Questions)*:
- `EVALUATION_WEIGHT_ACCURACY`: 0.30
- `EVALUATION_WEIGHT_CLARITY`: 0.25
- `EVALUATION_WEIGHT_COMPLETENESS`: 0.25
- `EVALUATION_WEIGHT_RELEVANCE`: 0.20

*Writer's Room (Creative Writing)*:
- `EVALUATION_WEIGHT_VOICE_AUTHENTICITY`: 0.25
- `EVALUATION_WEIGHT_EMOTIONAL_RESONANCE`: 0.20
- `EVALUATION_WEIGHT_ORIGINALITY`: 0.20
- `EVALUATION_WEIGHT_STYLE_CONSISTENCY`: 0.15
- `EVALUATION_WEIGHT_NARRATIVE_COHERENCE`: 0.15
- `EVALUATION_WEIGHT_LLM_ARTIFACT_AVOIDANCE`: 0.05

**Prompting Techniques** (toggleable for query/evaluation/synthesis):
- `QUERY_USE_HERMENEUTIC_CIRCLE`: Consider parts and whole together
- `QUERY_USE_CHAIN_OF_THOUGHT`: Step-by-step reasoning
- `QUERY_USE_VERBALIZED_SAMPLING`: Multiple response variants with probabilities
- `EVAL_USE_SOCRATIC_QUESTIONING`: Probe assumptions and implications
- `EVAL_USE_ADVERSARIAL_STANCE`: Critical red-team analysis
- `SYNTHESIS_USE_CONSTITUTIONAL_PRINCIPLES`: Principle-based synthesis
- `SYNTHESIS_USE_META_COGNITIVE_REFLECTION`: Acknowledge uncertainty

**Synthesis Configuration**:
- `SYNTHESIS_MODE`: `full` (synthesize from all), `highest_rated` (return best only), `none` (skip synthesis)
- `TOP_N_FOR_SYNTHESIS`: How many top responses to include (0 = all)
- `MIN_SCORE_FOR_SYNTHESIS`: Minimum score threshold (0-10, 0 = no filter)

**Performance & Timeouts**:
- `TIMEOUT_SECONDS`: Query timeout per model (5-360 seconds, default: 60)
- `EVAL_TIMEOUT_SECONDS`: Evaluation timeout (5-360 seconds, default: 90)
- `ENABLE_PARALLEL_REQUESTS`: Parallel queries (recommended: true)
- `DEBUG_MODE`: Enable detailed logging

**Output Display**:
- `SHOW_INDIVIDUAL_RESPONSES`: Display all model responses
- `SHOW_EVALUATION_SCORES`: Show score breakdown and rankings
- `SHOW_REASONING`: Show detailed evaluation reasoning
- `SHOW_PROGRESS`: Show progress indicators during processing
- `SHOW_TOKEN_USAGE`: Display token counts per model and phase
- `SHOW_COST_ESTIMATE`: Show estimated API costs

**Model-Specific Parameters** (advanced):
- `MODEL_PARAMS_JSON`: Per-model temperature/top_p/max_tokens as JSON
- `DEFAULT_TEMPERATURE`: Default temperature (0.0-2.0, default: 0.7)
- `DEFAULT_TOP_P`: Default nucleus sampling (0.0-1.0, default: 1.0)
- `DEFAULT_MAX_TOKENS`: Default max tokens (default: 2048)

## Project Structure

```
open-web-council/
|-- README.md                    # This file
|-- CLAUDE.md                    # AI assistant project guide
|-- QUICK-START.md               # Rapid setup guide
|-- council-pipeline/            # Main pipeline source
|   |-- council_orchestrator.py  # Core orchestrator (v0.5.0)
|   |-- council_orchestrator.json # Ready-to-import JSON
|   |-- schemas.py               # Data structures
|   |-- README.md                # Pipeline documentation
|   |-- V0.5.0-RELEASE-NOTES.md  # Latest release notes
|   `-- ...                      # Filters, actions, utilities
|-- docs/                        # Technical documentation
|   |-- phase-1-1-setup.md       # Phase 1 technical docs
|   |-- architecture-*.md        # Architecture decisions
|   |-- ROADMAP-UPDATED.md       # Development roadmap
|   `-- ...
|-- open web ui docs/            # Open WebUI documentation (reference)
`-- PHASE-*.md                   # Phase completion summaries
```

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1.1 | Complete | Foundation & Setup |
| 2.1 | Complete | Query Distribution & Anonymization |
| 2.2 | Complete | Evaluation & Synthesis Components |
| 2.3 | Complete | Full Integration |
| 2.4 | In Progress | Testing & Refinement |
| 3+ | Planned | Advanced Features |

## How It Works

### Example Session

**User**: "Explain quantum entanglement"

**Council Process**:

1. **Query Phase**: Sends query to GPT-4, Claude, and Gemini in parallel

2. **Anonymization**: Assigns anonymous IDs (response_a1b2, response_c3d4, response_e5f6)

3. **Evaluation Phase**: Each model evaluates all anonymous responses:
   - Accuracy: How factually correct?
   - Clarity: How well explained?
   - Completeness: How thorough?
   - Relevance: How on-topic?

4. **Score Aggregation**:
   ```
   gpt-4's response: 8.75/10 (highest)
   claude-3's response: 8.25/10
   gemini-pro's response: 7.50/10
   ```

5. **Synthesis**: Lead model combines insights from all responses

**Output** (with scores enabled):
```
[Synthesized Answer]
Quantum entanglement is a phenomenon where two or more particles
become correlated in such a way that the quantum state of one
particle cannot be described independently of the others...

[Evaluation Summary]
Rank 1 - gpt-4: 8.75/10
Rank 2 - claude-3: 8.25/10
Rank 3 - gemini-pro: 7.50/10
```

## Design Philosophy

This project applies **Heidegger's hermeneutic circle** to software architecture:

- **The Whole**: A peer-review LLM consultation system
- **The Parts**: Query distribution, anonymization, evaluation, synthesis
- **The Interplay**: Understanding each component requires grasping the whole system's purpose, while the system's meaning emerges from how the parts interact

Practically, this means:
- Each module is designed with awareness of its role in the larger workflow
- Configuration supports the entire process, not just individual steps
- Error handling preserves the integrity of the peer-review mechanism

## Token Usage

Council uses more tokens than single-model queries due to multiple phases:

- **Initial queries**: N models * query tokens
- **Evaluations**: N * (N-1) evaluation calls (each model evaluates others)
- **Synthesis**: 1 final synthesis call with all context

**v0.5.0 Increase**: ~40-60% more tokens than v0.4.0 due to detailed evaluation reasoning. This is a quality-for-tokens trade-off.

**Mitigation**:
- Configure `TIMEOUT_SECONDS` to limit long responses
- Use `MIN_MODELS_REQUIRED` to control minimum (default: 2)
- Toggle prompting techniques to reduce token usage if needed

## Troubleshooting

**"Council requires at least X models"**
- Set `MODELS_TO_QUERY` in Orchestrator Valves with valid model IDs from your Open WebUI instance
- Check that model IDs match exactly (case-sensitive)
- Verify models are active and responding in Open WebUI

**Models timing out**
- Increase `TIMEOUT_SECONDS` (default: 60, max: 360 seconds)
- Increase `EVAL_TIMEOUT_SECONDS` for evaluation phase (default: 90, max: 360 seconds)
- Check that models are responding normally in Open WebUI directly
- Some models (like O3) may need longer timeouts for complex reasoning

**Empty content in Individual Model Responses**
- Update to v0.6.1 or later (this was a bug in the reverse mapping code)
- Re-import the latest `writers_room_orchestrator.json` or `council_orchestrator.json`
- Or run `python update_functions.py` to auto-update

**Evaluation scores not parsing**
- Enable `DEBUG_MODE` to see raw evaluation responses
- Check that evaluation models are returning structured scores
- Some models may need prompting adjustments for consistent score formatting

**Wrong evaluation count displayed**
- Update to v0.6.1 or later (fixed evaluation count calculation)
- This was especially noticeable when using separate `EVALUATION_MODELS`

**Import fails**
- Ensure you're importing the `.json` file, not the `.py` file
- Check Open WebUI version supports Functions/Pipelines (v0.1.0+)
- Try importing individual files instead of `council_llms_complete.json`

**High token usage / API costs**
- Reduce the number of models in `MODELS_TO_QUERY`
- Use `SYNTHESIS_MODE: "highest_rated"` to skip synthesis
- Set `TOP_N_FOR_SYNTHESIS` to limit responses included in synthesis
- Use `MIN_SCORE_FOR_SYNTHESIS` to filter low-quality responses
- Disable verbose prompting techniques in Valves

## Contributing

Contributions welcome! This is an open-source project under the Open WebUI ecosystem.

### Development Setup

```bash
# Clone this repository
git clone https://github.com/chmodxheart/open-web-council.git
cd open-web-council/council-pipeline

# Review the codebase
ls -la

# Make changes to source files
vim council_orchestrator.py

# Regenerate JSON exports
python create_bundled_exports.py

# Deploy to Open WebUI
python update_functions.py
```

### Development Utilities

The `council-pipeline/` directory includes several utility scripts:

**Deployment & Updates**:
- `update_functions.py` - Auto-deploy/update all functions in Open WebUI via API
  - Creates new functions or updates existing ones
  - Preserves Valve configurations on updates
  - Handles all JSON files in the directory

**Build Tools**:
- `create_bundled_exports.py` - Generate all JSON exports from source files
  - Inlines schemas into bundled versions
  - Creates both individual and complete suite JSON files
  - Run this after modifying any `.py` source files

**Configuration Management**:
- `check_valve_config.py` - View current Valve values for all functions
- `reset_models_valve.py` - Reset MODELS_TO_QUERY to default value

**Credential Configuration**:

All scripts support flexible credential management via environment variables or command-based retrieval. See [`.env.example`](.env.example) for full configuration options.

**Quick Setup** (Direct Credentials):
```bash
export OPENWEBUI_URL="https://your-openwebui-instance.com"
export OPENWEBUI_API_KEY="sk-your-api-key"
python update_functions.py
```

**Advanced Setup** (1Password CLI):
```bash
export OPENWEBUI_URL_COMMAND='op item get "OpenWebUI" --fields url --reveal'
export OPENWEBUI_API_KEY_COMMAND='op item get "OpenWebUI" --fields api_key --reveal'
python update_functions.py
```

Supports: 1Password, AWS Secrets Manager, HashiCorp Vault, or any CLI tool that outputs credentials.

### Current Focus

- Phase 2.4: Testing with various model combinations
- Performance optimization
- User experience refinement

## References

- [Open WebUI](https://github.com/open-webui/open-webui)
- [Open WebUI Pipelines](https://github.com/open-webui/pipelines)
- [Open WebUI Documentation](https://docs.openwebui.com)

## License

MIT License

## Support

- **Issues**: [GitHub Issues](https://github.com/chmodxheart/open-web-council/issues)
- **Discussions**: Open WebUI Community
- **Documentation**: See `docs/` directory

---

**Built with the Open WebUI Pipelines framework**

*Primary Developer: @chmodxheart*
