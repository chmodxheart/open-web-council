# Council of LLMs

A multi-LLM consultation system with anonymous peer review for [Open WebUI](https://github.com/open-webui/open-webui).

## Overview

Council of LLMs enables consultation across multiple language models with unbiased peer evaluation and intelligent synthesis. Inspired by academic peer review processes, the system:

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

**Version**: 0.6.0 (Synthesis Mode & Cost Tracking Release)
**Status**: Fully Functional - Ready for Use
**Last Updated**: 2025-12-06

### What's Working

- Multi-model query distribution (parallel)
- Response anonymization with blind peer review
- Real model-based evaluations with detailed reasoning
- Score parsing and aggregation
- Real LLM-powered synthesis
- Streaming output support
- Configurable prompting techniques
- De-anonymized user output (transparent after evaluation)
- Detailed error messages
- **NEW**: Synthesis mode toggle (full/highest_rated/none)
- **NEW**: Token usage tracking per model and phase
- **NEW**: Cost estimation with per-model pricing

## Quick Start

### Prerequisites

- Python 3.11+
- Open WebUI running with Pipelines support
- At least 3 LLM models configured in Open WebUI

### Installation

1. **Download** `council_orchestrator.json` from `council-pipeline/`

2. **Import into Open WebUI**:
   - Navigate to Admin Panel -> Functions
   - Click "Import Function"
   - Upload `council_orchestrator.json`

3. **Configure**:
   - Set `MODELS_TO_QUERY` in the Valves panel (e.g., `gpt-4,claude-3-opus,gemini-pro`)

4. **Use**:
   - Select "Council of LLMs" from the model dropdown
   - Ask your question
   - Receive a synthesized answer from multiple LLMs

### Minimum Configuration

Set `MODELS_TO_QUERY` in Orchestrator Valves:
```
gpt-4,claude-3-opus,gemini-pro
```

Models should match the model IDs available in your Open WebUI instance.

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

### Configuration Options (28 Valves)

**Model Configuration**:
- `MODELS_TO_QUERY`: Comma-separated model list
- `LEAD_SYNTHESIZER`: Auto (highest-scoring) or designated model
- `MIN_MODELS_REQUIRED`: Minimum threshold (default: 2)

**Evaluation Weights** (must sum to 1.0):
- `EVALUATION_WEIGHT_ACCURACY`: 0.3
- `EVALUATION_WEIGHT_CLARITY`: 0.25
- `EVALUATION_WEIGHT_COMPLETENESS`: 0.25
- `EVALUATION_WEIGHT_RELEVANCE`: 0.2

**Prompting Techniques** (all toggleable):
- Hermeneutic Circle (parts/whole interplay)
- Chain of Thought (step-by-step reasoning)
- Verbalized Sampling (show thinking process)
- Socratic Questioning (probe assumptions)
- Adversarial Stance (red team analysis)
- Constitutional Principles (principle-based justification)
- Meta-Cognitive Reflection (uncertainty awareness)

**Performance**:
- `TIMEOUT_SECONDS`: Per-model timeout (default: 60)
- `DEBUG_MODE`: Enable detailed logging

**Output**:
- `SHOW_INDIVIDUAL_RESPONSES`: Show all model responses
- `SHOW_EVALUATION_SCORES`: Show score breakdown
- `SHOW_DETAILED_EVALUATIONS`: Show full evaluation reasoning

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
- Set `MODELS_TO_QUERY` in Orchestrator Valves with valid model IDs

**Models timing out**
- Increase `TIMEOUT_SECONDS` (default: 60)
- Check that models are responding in Open WebUI directly

**Evaluation scores not parsing**
- Enable `DEBUG_MODE` to see raw evaluation responses
- Adjust score parsing regex patterns in Valves if needed

**Import fails**
- Ensure you're importing the JSON file, not the Python file
- Check Open WebUI version supports Functions/Pipelines

## Contributing

Contributions welcome! This is an open-source project under the Open WebUI ecosystem.

### Development Setup

```bash
# Clone this repository
git clone https://github.com/chmodxheart/open-web-council.git
cd open-web-council

# Review the codebase
ls council-pipeline/

# Make changes to council_orchestrator.py
# Test by importing into Open WebUI
```

### Development Scripts Credentials

The `council-pipeline/` directory includes utility scripts for managing functions via the Open WebUI API:
- `update_functions.py` - Auto-update functions in Open WebUI
- `check_valve_config.py` - Check current valve configuration
- `reset_models_valve.py` - Reset MODELS_TO_QUERY valve

**Credential Configuration**: These scripts support flexible credential management. See [`.env.example`](.env.example) for configuration options:
- Direct environment variables
- Command-based retrieval (1Password, AWS Secrets Manager, HashiCorp Vault, etc.)
- Default values (development only)

Example:
```bash
export OPENWEBUI_URL="https://your-openwebui-instance.com"
export OPENWEBUI_API_KEY="sk-your-api-key"

# OR using 1Password CLI
export OPENWEBUI_URL_COMMAND='op item get "OpenWebUI API Key" --fields label=url --reveal'
export OPENWEBUI_API_KEY_COMMAND='op item get "OpenWebUI API Key" --fields label=password --reveal'
```

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
