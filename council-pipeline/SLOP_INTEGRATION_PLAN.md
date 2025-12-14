# Slop Detection Integration Plan

## Overview

Integrate the [slop-forensics toolkit](https://github.com/sam-paech/slop-forensics) into the Writer's Room to detect and avoid LLM-generated "slop" - overused lexical patterns that make writing sound AI-generated.

## What is Slop?

From slop-forensics research:
- **Over-represented words**: e.g., "shimmered", "ethereal", "tendrils", "palpable"
- **Over-represented bigrams**: e.g., "heart pounding", "barely whisper", "eyes widened"
- **Over-represented trigrams**: e.g., "heart pounding chest", "felt strange sense"
- **Fantasy name patterns**: "Aelara", "Kael", "Xyloth", etc.

These patterns appear far more frequently in LLM outputs than in human creative writing.

## Integration Approaches

### Option 1: Proactive Prevention (Recommended)

**Add explicit slop warnings to prompts** to prevent generation in the first place.

#### Generation Prompt Addition:
```python
sections.append("\n**Avoid LLM Slop Patterns:**")
sections.append("Actively avoid these overused AI writing patterns:")
sections.append("- Physical reactions: 'heart pounding', 'breath hitched', 'eyes widened'")
sections.append("- Atmospheric words: 'shimmered', 'palpable', 'ethereal', 'tendrils'")
sections.append("- Over-descriptive verbs: 'beckoned', 'whispered', 'murmured', 'trembled'")
sections.append("- Fantasy names with X/Y/Z: 'Xyl-', 'Zeph-', 'Aeth-', 'Kael-'")
sections.append("- Adverb abuse: 'cautiously', 'carefully', 'slowly', 'gently'")
sections.append("- Use fresh, specific descriptions instead")
```

#### Evaluation Prompt Enhancement:
Update the "LLM_ARTIFACT_AVOIDANCE" criterion to explicitly check for slop:

```python
sections.append("6. **LLM_ARTIFACT_AVOIDANCE** (Doesn't Sound Like AI)")
sections.append("   - Check for slop patterns:")
sections.append("     * Overused verbs: shimmered, flickered, whispered, murmured, trembled")
sections.append("     * Physical clichés: heart pounding, breath hitched, eyes widened")
sections.append("     * Atmospheric words: palpable, ethereal, tendrils, cascade")
sections.append("     * Generic fantasy names: Aelara, Kael, Xyloth, Zephyr")
sections.append("   - Also check for: generic transitions, hedging, meta-commentary")
sections.append("   - PENALIZE heavily for slop density")
```

**Pros:**
- ✅ Prevents slop before it's generated
- ✅ No runtime overhead or dependencies
- ✅ Works immediately
- ✅ Models learn to avoid patterns proactively

**Cons:**
- ⚠️ Relies on models following instructions
- ⚠️ Must manually curate slop examples in prompts

### Option 2: Reactive Analysis

**Add post-generation slop detection** using slop-forensics code.

#### Implementation:
1. Copy slop list JSON files to Writer's Room data directory
2. Integrate `calculate_slop_index_new()` from slop-forensics
3. Add optional slop analysis after synthesis

```python
# In writers_room_orchestrator.py

SLOP_LISTS_PATH = Path(__file__).parent / "data" / "slop_lists"

def _calculate_slop_score(self, text: str) -> dict:
    """Calculate slop index using slop-forensics methodology"""
    # Load slop lists
    slop_words = self._load_slop_list('slop_list.json')
    slop_bigrams = self._load_slop_list('slop_list_bigrams.json')
    slop_trigrams = self._load_slop_list('slop_list_trigrams.json')

    # Tokenize
    tokens = nltk.word_tokenize(text.lower())

    # Count hits
    word_hits = sum(1 for t in tokens if t in slop_words)
    bigram_hits = sum(1 for bg in nltk.ngrams(tokens, 2)
                      if ' '.join(bg) in slop_bigrams)
    trigram_hits = sum(1 for tg in nltk.ngrams(tokens, 3)
                       if ' '.join(tg) in slop_trigrams)

    # Calculate weighted score (weights: 1, 2, 8)
    total_slop_score = word_hits + (2 * bigram_hits) + (8 * trigram_hits)
    slop_index = (total_slop_score / len(tokens)) * 1000 if tokens else 0

    return {
        'slop_index': round(slop_index, 2),
        'word_hits': word_hits,
        'bigram_hits': bigram_hits,
        'trigram_hits': trigram_hits,
        'total_words': len(tokens)
    }
```

#### Valve Configuration:
```python
ENABLE_SLOP_DETECTION: bool = Field(
    default=True,
    description="Run slop detection on final output"
)

SLOP_THRESHOLD_WARNING: float = Field(
    default=50.0,
    description="Slop index threshold for warning (typical: 30-60)"
)
```

#### Output:
```markdown
## 💡 Writer's Room Final Draft

[synthesized content]

---

**📊 Slop Analysis:**
- Slop Index: 42.3 (moderate)
- Pattern matches: 8 words, 3 bigrams, 1 trigram
- ⚠️ Warning: Contains moderate slop. Consider revising overused phrases.

Common slop detected:
- "heart pounding" (bigram)
- "shimmered" (word)
- "eyes widened" (bigram)
```

**Pros:**
- ✅ Quantitative feedback
- ✅ Identifies specific slop patterns
- ✅ Can track improvement over time
- ✅ Educational for users

**Cons:**
- ⚠️ Requires NLTK dependency
- ⚠️ Runtime overhead (minimal ~100ms)
- ⚠️ Reactive, not preventive

### Option 3: Hybrid Approach (Best)

**Combine both** for maximum effectiveness:

1. **Proactive**: Add slop warnings to generation and evaluation prompts
2. **Reactive**: Optionally analyze final output and show slop score
3. **Iterative**: If slop score is high, optionally trigger revision pass

#### Revision Flow:
```python
if slop_score > SLOP_THRESHOLD_WARNING:
    if self.valves.AUTO_REVISE_HIGH_SLOP:
        # Trigger revision
        revision_prompt = f"""
        The following text has a high slop index ({slop_score}).
        Rewrite it to remove these overused patterns while maintaining
        the same meaning and emotional impact:

        Specific patterns to replace:
        {detected_slop_patterns}

        Original text:
        {synthesis_text}
        """
        revised = await self._revision_pass(revision_prompt)
```

## Recommended Implementation

**Phase 1** (Quick win - no dependencies):
- ✅ Add slop pattern warnings to generation prompts
- ✅ Enhance LLM_ARTIFACT_AVOIDANCE evaluation criterion with specific slop examples
- ✅ Include top 20-30 most egregious slop patterns in prompt

**Phase 2** (Full integration):
- ✅ Copy slop list JSON files to `council-pipeline/data/slop_lists/`
- ✅ Add slop detection function (adapted from slop-forensics)
- ✅ Add ENABLE_SLOP_DETECTION valve
- ✅ Show slop analysis in output (optional, controlled by valve)

**Phase 3** (Advanced):
- ✅ Add AUTO_REVISE_HIGH_SLOP valve
- ✅ Implement revision pass for high-slop outputs
- ✅ Track slop reduction across rewrites

## Slop List Files Needed

From `/mnt/extra/repo/slop-forensics/data/`:
```
slop_list.json          # ~1000 overused words
slop_list_bigrams.json  # ~100 overused 2-word phrases
slop_list_trigrams.json # ~100 overused 3-word phrases
```

These should be copied to:
```
council-pipeline/data/slop_lists/
```

## Example Slop Patterns to Include in Prompts

### Top Slop Words (Highest Offenders):
- shimmered, flickered, glinted, gleamed
- whispered, murmured, breathed, rasped
- palpable, ethereal, arcane, eldritch
- trembled, quivered, shuddered, shivered
- tendrils, wisps, motes, tendrils
- beckoned, loomed, unfurled, coalesced

### Top Slop Bigrams:
- heart pounding, breath hitched
- eyes widened, eyes narrowed
- barely whisper, voice low
- mind racing, deep breath
- felt sense, could feel

### Top Slop Trigrams:
- heart pounding chest
- eyes wide disbelief
- breath hitched throat

## License & Attribution

The slop lists are from [slop-forensics](https://github.com/sam-paech/slop-forensics) by Samuel J. Paech (MIT License).

If using slop detection, add attribution:
```python
# Slop detection using lists from:
# Paech, Samuel J. (2025). Slop Forensics: A Toolkit for Generating & Analyzing
# Lexical Patterns in LLM Outputs. https://github.com/sam-paech/slop-forensics
```

## Next Steps

1. ✅ Implement Phase 1 (prompt-based prevention) - **immediate, no deps**
2. ⏳ Copy slop list files to council-pipeline
3. ⏳ Implement Phase 2 (reactive detection) - **requires NLTK**
4. ⏳ Test and tune slop threshold values
5. ⏳ Consider Phase 3 (auto-revision) based on user feedback

## Questions for User

1. Do you want **proactive** (prompts only), **reactive** (detection), or **both**?
2. Should slop detection be always-on or optional (valve)?
3. Should we auto-revise high-slop outputs, or just warn?
4. What slop index threshold should trigger warnings? (typical: 30-60)

---

**Status**: Planning complete
**Recommendation**: Start with Phase 1 (prompts), add Phase 2 later if users want quantitative feedback
