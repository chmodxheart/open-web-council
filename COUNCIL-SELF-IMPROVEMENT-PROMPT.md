# Meta-Prompt: Council of LLMs Self-Improvement

## Your Task

You are being consulted as part of a **Council of LLMs** system. Your task is to analyze the Council's own architecture, prompting strategies, and workflows, then suggest improvements to the prompts and techniques it uses.

## What is the Council of LLMs?

The Council of LLMs is a multi-model consultation system that implements **blind peer review** for AI responses. Here's how it works:

### Workflow

1. **Query Distribution**: User submits a question → System queries multiple LLMs in parallel
2. **Response Collection & Anonymization**: All responses are collected and assigned random anonymous IDs
3. **Blind Peer Evaluation**: Each model evaluates ALL anonymous responses (including its own, unknowingly)
4. **Score Aggregation**: Scores from all evaluators are aggregated per response
5. **Synthesis**: The highest-scoring response(s) and evaluations are sent to a lead model for final synthesis
6. **User Output**: Synthesized answer with optional transparency into scores, reasoning, and individual responses

### Key Innovation: Overlapped Execution

The system now uses **overlapped query and evaluation** for performance:
- As soon as Model A responds, evaluations start immediately
- Model B evaluates Model A's response while Model C is still thinking
- Model C eventually evaluates both A and B's responses
- Total time ≈ max(slowest query, slowest evaluation) instead of sequential phases

## Current Prompting Techniques

The Council uses different prompting techniques at different stages:

### Initial Query Phase (when models answer the user's question)

**Currently enabled by default:**
- ✅ **Hermeneutic Circle**: Apply Heidegger's parts/whole interplay when interpreting the question

**Available but disabled by default (to reduce timeout issues):**
- ❌ Chain-of-Thought: Step-by-step reasoning
- ❌ Verbalized Sampling: Show intermediate thinking process

### Evaluation Phase (when models critique anonymous responses)

**Currently enabled by default:**
- ✅ **Hermeneutic Circle**: Apply parts/whole analysis to the response being evaluated
- ✅ **Verbalized Sampling**: Show evaluation thought process
- ✅ **Socratic Questioning**: Probe assumptions, gaps, edge cases, and unanswered questions
- ✅ **Adversarial/Red Team Stance**: Actively look for flaws, weaknesses, and potential issues
- ✅ **Constitutional Principles**: Justify scores based on explicit quality principles

### Synthesis Phase (when lead model creates final answer)

**Currently enabled by default:**
- ✅ **Meta-Cognitive Reflection**: Reflect on uncertainty and confidence levels

## Current Prompts

### Initial Query System Message (when hermeneutic circle enabled)

```
You are responding to a user's query as part of a Council of LLMs consultation.
Provide a thorough, accurate, and helpful response.

**Hermeneutic Circle Approach:**
Apply Heidegger's theory of the hermeneutic circle in your response. Move iteratively between the parts and the whole of the question, considering how understanding each detail depends on the broader context and how the overall meaning emerges through that interplay. Show how specific details illuminate the larger picture and vice versa.

**Quality Standards:**
Ensure your response is factually accurate, clearly expressed, thorough in addressing all aspects of the question, and directly relevant to what was asked.
```

### Evaluation Prompt (excerpt - full version includes detailed rubric)

```
You are participating in a blind peer review of AI responses. Your task is to evaluate the following anonymous response objectively and critically.

**Hermeneutic Circle Approach:**
Apply Heidegger's theory of the hermeneutic circle in your evaluation. Move iteratively between specific details and the overall response, considering how each part contributes to the whole and how the whole illuminates the meaning of each part.

**Show Your Thinking:**
Reveal your evaluation thought process. Don't just assign scores—show how you arrived at them. What did you notice? What considerations did you weigh? What makes this response strong or weak?

**Socratic Examination:**
Probe the response deeply:
- What assumptions does it make?
- What questions does it leave unanswered?
- What could the user misunderstand?
- What edge cases or scenarios does it not address?

**Critical Red Team Analysis:**
Actively look for flaws, weaknesses, and potential issues:
- What could go wrong if someone followed this advice?
- Are there hidden assumptions or oversimplifications?
- What important caveats or warnings are missing?
- Where is this response potentially misleading or incomplete?

**Principle-Based Justification:**
Ground your scores in explicit quality principles. For each score, justify it by reference to specific criteria below. Don't just give a number—explain WHY based on observable qualities.

[...Detailed scoring rubric for Accuracy, Clarity, Completeness, Relevance follows...]

REASONING: [Provide a DETAILED analysis explaining your scores. Include:
  - Specific strengths you observed
  - Specific weaknesses or issues you identified
  - Evidence from the response supporting your scores
  - How you weighted different factors in your evaluation
  - Any important caveats or context
  Be thorough—several paragraphs are expected, not just 2-3 sentences.]
```

### Synthesis Prompt (excerpt)

```
You are the lead synthesizer for a Council of LLMs consultation. Your task is to create a comprehensive final answer by synthesizing insights from multiple AI responses and their peer evaluations.

**Meta-Cognitive Reflection:**
As you synthesize, reflect on:
- Where are you most confident in the combined insights?
- Where is there uncertainty or disagreement among responses?
- What caveats or limitations should the user be aware of?
- What assumptions are you making in your synthesis?

You have access to ALL responses (not just the highest-rated) along with their evaluation scores...

[...Instructions continue with guidance on learning from both good and bad approaches...]
```

## Your Task: Improve These Prompts

Please analyze the Council's prompting strategies and provide:

1. **Initial Query Improvements**
   - Should we enable more techniques by default (chain-of-thought, verbalized sampling)?
   - Are there better ways to phrase the hermeneutic circle instruction?
   - Are there other prompting techniques we should add for initial queries?
   - How can we balance quality with timeout constraints?

2. **Evaluation Improvements**
   - Are the current techniques (Socratic, adversarial, constitutional) the right ones?
   - Is the REASONING prompt effective, or can it be improved?
   - Should we add or remove any evaluation techniques?
   - How can we encourage even more detailed, substantive evaluations?

3. **Synthesis Improvements**
   - Is meta-cognitive reflection sufficient for synthesis?
   - What other techniques would help the synthesizer create better final answers?
   - How should the synthesizer weigh high-scoring vs. low-scoring responses?

4. **New Techniques to Consider**
   - Self-consistency sampling?
   - Tree-of-thought?
   - Least-to-most prompting?
   - Analogical reasoning?
   - Other techniques from the prompting literature?

5. **Systemic Improvements**
   - Should different phases use different techniques?
   - Should techniques be applied differently based on query type?
   - Are there meta-prompting strategies we're missing?

## Format Your Response

Please provide:

1. **Executive Summary**: 2-3 paragraphs on the biggest opportunities for improvement
2. **Specific Prompt Revisions**: Concrete, ready-to-use improved versions of the prompts
3. **Technique Recommendations**: Which techniques to enable/disable/add, with rationale
4. **Implementation Priority**: What should be changed first for maximum impact?

---

**Remember**: You are helping the Council improve itself. Be critical, creative, and evidence-based in your recommendations!
