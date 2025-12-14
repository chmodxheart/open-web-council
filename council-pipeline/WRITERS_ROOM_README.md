# LLM Writer's Room

A creative writing-focused variant of the Council of LLMs system, specifically designed to produce human-like, emotionally resonant prose while avoiding common LLM artifacts.

## Overview

The Writer's Room uses the same multi-LLM peer review architecture as the Council, but with evaluation criteria and prompts specifically tailored for creative writing:

**Creative Writing Evaluation Criteria:**
1. **Voice Authenticity** (25%) - Human-like voice, avoids LLM artifacts
2. **Emotional Resonance** (20%) - Shows don't tell, evokes feelings
3. **Originality & Risk-Taking** (20%) - Avoids clichés, uses fresh metaphors
4. **Style Consistency** (15%) - Matches brief, maintains unified voice
5. **Narrative Coherence** (15%) - Clear structure, smooth flow
6. **LLM Artifact Avoidance** (5%) - Explicit penalty for AI-sounding phrases

## How It Works

1. **Query Distribution** - Multiple models generate creative content
2. **Anonymization** - Strip model identifiers for unbiased review
3. **Peer Evaluation** - Models evaluate each other's writing using creative criteria
4. **Score Aggregation** - Rank outputs by voice, emotion, and originality
5. **Synthesis** - Lead model synthesizes the best creative choices into a polished final draft

## Key Differences from Council

### Prompting
- **Generation**: Emphasizes concrete sensory details, showing vs. telling, taking creative risks
- **Evaluation**: Looks for human-like voice, emotional impact, fresh metaphors vs. generic correctness
- **Synthesis**: Focuses on maintaining voice authenticity and combining the best creative moments

### Scoring
The Writer's Room maps creative criteria to the existing `EvaluationScores` schema:
- `voice_authenticity` → accuracy field
- `emotional_resonance` → clarity field
- `originality` → completeness field
- `avg(style_consistency, narrative_coherence, llm_artifact_avoidance)` → relevance field

This maintains compatibility with the existing schema while evaluating creative writing-specific qualities.

### Output Labels
- "Writer's Room Session" instead of "Council Discussion"
- "Writer's Room Final Draft" instead of "Council Response"
- Editorial/creative writing terminology throughout

## Usage

Import `writers_room_orchestrator.json` into Open WebUI just like the Council orchestrator.

### Configuration Tips

1. **Model Selection**: Use creative/diverse models. GPT-4, Claude, and Gemini work well together.

2. **Temperature**: Higher temperatures (0.8-1.0) often produce more interesting creative writing.

3. **Context Management** (future enhancement):
   - Story Bible: Voice examples, do/don't lists, character sheets
   - Session context: Recent scene recaps
   - Prompt-local: Specific scene instructions

4. **Prompting Techniques**:
   - Enable Hermeneutic Circle for literary fiction that weaves part/whole
   - Enable Chain of Thought for narrative development
   - Enable Verbalized Sampling to encourage creative exploration

## Example Workflow

**User Prompt:**
```
Write a 300-word opening scene for a noir detective story.
First-person POV, wry voice, late night in a downtown office.
Show the character's weariness through concrete details, not abstract statements.
```

**What Happens:**
1. 4 models generate different takes on the scene
2. All models evaluate all scenes for voice, emotion, originality, etc.
3. Scores are aggregated (e.g., Model A gets 8.2/10, Model B gets 7.5/10...)
4. Lead model (highest scoring or selected) synthesizes the best:
   - Takes the most vivid sensory details
   - Chooses the freshest metaphors
   - Maintains the most consistent voice
   - Avoids LLM-isms like hedging or generic transitions

**Output:** A polished scene that reads like one human author wrote it, drawing on the creative strengths of multiple models.

## Future Enhancements

Based on the Council synthesis feedback, consider:

1. **Story Bible Integration**
   - Per-project voice samples and style rules
   - Character sheets with speech patterns
   - World/canon consistency tracking

2. **Session Memory**
   - Narrative recap of recent scenes
   - Emotional arc tracking
   - Contradiction avoidance

3. **Specialized Model Roles**
   - "Stylist" for rich prose and metaphor
   - "Structuralist" for pacing and coherence
   - "Voice-police" for adherence to brief
   - "Risk-taker" for originality

4. **LLM Artifact Detector**
   - Dedicated pass to identify and penalize AI patterns
   - Maintain list of banned/discouraged patterns
   - Optional revision step to remove artifacts

5. **Rubric Calibration**
   - Human scoring benchmarks
   - Iterative rubric refinement
   - Per-dimension weight tuning based on output quality

## Technical Notes

- Compatible with existing Council schemas and infrastructure
- Uses creative-specific prompts but maintains workflow structure
- Can be deployed alongside Council for different use cases
- Token tracking and cost estimation work identically

## Files

- `writers_room_orchestrator.py` - Main source file
- `bundled_writers_room_orchestrator.py` - Self-contained version with schemas inlined
- `writers_room_orchestrator.json` - Open WebUI import file

## Credits

Based on the Council of LLMs system by chmodxheart.
Adapted for creative writing based on feedback about human-like prose generation.
