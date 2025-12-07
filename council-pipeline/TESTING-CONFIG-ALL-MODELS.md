# Council of LLMs - Comprehensive Testing Configuration

**Date**: 2025-12-05
**Purpose**: Full-scale testing with 19 free models
**Version**: v0.5.0+

## Testing Model List

### Premium Models (Free Tier)
1. `gpt-5.1`
2. `gpt-5.1-chat-latest`
3. `o3`
4. `anthropic/claude-sonnet-4.5`
5. `anthropic/claude-haiku-4.5`
6. `google/gemini-2.5-flash`
7. `minimax/minimax-m2`
8. `deepseek/deepseek-chat-v3.1`

### Groq-Hosted Models (Free)
9. `groq.moonshotai/kimi-k2-instruct`
10. `groq.llama-3.1-8b-instant`
11. `groq.llama-3.3-70b-versatile`
12. `groq.openai/gpt-oss-120b`
13. `groq.openai/gpt-oss-20b`
14. `groq.groq/compound`
15. `groq.groq/compound-mini`
16. `groq.meta-llama/llama-4-maverick-17b-128e-instruct`
17. `groq.meta-llama/llama-4-scout-17b-16e-instruct`
18. `groq.qwen/qwen3-32b`

### AWS Bedrock Models (Free)
19. `amazon/nova-2-lite-v1:free`

**Total**: 19 models

## Testing Scenarios

### Scenario 1: Small Council (3 Models - Baseline)
**Models**: `gpt-5.1`, `anthropic/claude-sonnet-4.5`, `google/gemini-2.5-flash`
**Purpose**: Verify core functionality with high-quality models
**Expected Time**: ~30-60s
**Token Usage**: ~3,000-5,000 tokens

### Scenario 2: Medium Council (5 Models - Recommended)
**Models**: `gpt-5.1`, `anthropic/claude-sonnet-4.5`, `google/gemini-2.5-flash`, `deepseek/deepseek-chat-v3.1`, `minimax/minimax-m2`
**Purpose**: Balanced quality vs. diversity
**Expected Time**: ~45-90s
**Token Usage**: ~5,000-8,000 tokens

### Scenario 3: Large Council (8 Premium Models)
**Models**: All 8 premium models listed above
**Purpose**: Maximum quality with diverse perspectives
**Expected Time**: ~60-120s
**Token Usage**: ~8,000-15,000 tokens

### Scenario 4: Groq Speed Test (10 Groq Models)
**Models**: All Groq models (groq.*)
**Purpose**: Test overlapped execution with fast inference
**Expected Time**: ~20-40s (Groq is extremely fast)
**Token Usage**: ~10,000-18,000 tokens

### Scenario 5: Full Council (All 19 Models - Stress Test)
**Models**: All models listed above
**Purpose**: Maximum diversity, stress test system limits
**Expected Time**: ~90-180s
**Token Usage**: ~20,000-35,000 tokens
**Evaluations**: 19 × 19 = **361 evaluations**

## Configuration Instructions

### Via Open WebUI UI

1. **Navigate to Admin Panel**:
   - Settings → Functions → Council of LLMs Orchestrator

2. **Configure Valves**:

   **For Scenario 1 (Baseline - 3 Models)**:
   ```
   MODELS_TO_QUERY = gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-2.5-flash
   LEAD_MODEL = gpt-5.1
   MIN_REQUIRED_RESPONSES = 3
   ```

   **For Scenario 2 (Recommended - 5 Models)**:
   ```
   MODELS_TO_QUERY = gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-2.5-flash,deepseek/deepseek-chat-v3.1,minimax/minimax-m2
   LEAD_MODEL = gpt-5.1
   MIN_REQUIRED_RESPONSES = 5
   ```

   **For Scenario 3 (Premium - 8 Models)**:
   ```
   MODELS_TO_QUERY = gpt-5.1,gpt-5.1-chat-latest,o3,anthropic/claude-sonnet-4.5,anthropic/claude-haiku-4.5,google/gemini-2.5-flash,minimax/minimax-m2,deepseek/deepseek-chat-v3.1
   LEAD_MODEL = gpt-5.1
   MIN_REQUIRED_RESPONSES = 8
   ```

   **For Scenario 4 (Groq Speed Test - 10 Models)**:
   ```
   MODELS_TO_QUERY = groq.moonshotai/kimi-k2-instruct,groq.llama-3.1-8b-instant,groq.llama-3.3-70b-versatile,groq.openai/gpt-oss-120b,groq.openai/gpt-oss-20b,groq.groq/compound,groq.groq/compound-mini,groq.meta-llama/llama-4-maverick-17b-128e-instruct,groq.meta-llama/llama-4-scout-17b-16e-instruct,groq.qwen/qwen3-32b
   LEAD_MODEL = groq.llama-3.3-70b-versatile
   MIN_REQUIRED_RESPONSES = 10
   ```

   **For Scenario 5 (Full Council - All 19 Models)**:
   ```
   MODELS_TO_QUERY = gpt-5.1,gpt-5.1-chat-latest,o3,anthropic/claude-sonnet-4.5,anthropic/claude-haiku-4.5,google/gemini-2.5-flash,minimax/minimax-m2,deepseek/deepseek-chat-v3.1,groq.moonshotai/kimi-k2-instruct,groq.llama-3.1-8b-instant,groq.llama-3.3-70b-versatile,groq.openai/gpt-oss-120b,groq.openai/gpt-oss-20b,groq.groq/compound,groq.groq/compound-mini,groq.meta-llama/llama-4-maverick-17b-128e-instruct,groq.meta-llama/llama-4-scout-17b-16e-instruct,groq.qwen/qwen3-32b,amazon/nova-2-lite-v1:free
   LEAD_MODEL = gpt-5.1
   MIN_REQUIRED_RESPONSES = 15
   ```

3. **Recommended Settings for Testing**:
   ```
   ENABLE_STREAMING = True
   SHOW_INDIVIDUAL_RESPONSES = True
   SHOW_EVALUATION_SCORES = True
   SHOW_REASONING = True
   DEBUG_MODE = True

   # Evaluation techniques (default: all True)
   EVAL_USE_SOCRATIC_QUESTIONING = True
   EVAL_USE_ADVERSARIAL_STANCE = True
   EVAL_USE_VERBALIZED_SAMPLING = True

   # Timeout settings
   QUERY_TIMEOUT = 60
   EVAL_TIMEOUT = 45
   SYNTHESIS_TIMEOUT = 60
   ```

## Test Query Examples

### 1. Technical Question (Tests Accuracy & Completeness)
```
What are the key differences between async/await and traditional callbacks in JavaScript, and when should each be used?
```

### 2. Creative Question (Tests Clarity & Creativity)
```
Explain quantum entanglement to a 10-year-old using an everyday analogy.
```

### 3. Complex Multi-Part Question (Tests Completeness & Structure)
```
Design a microservices architecture for an e-commerce platform. Include:
1) Service breakdown,
2) Communication patterns,
3) Data consistency strategies,
4) Deployment considerations.
```

### 4. Controversial/Nuanced Question (Tests Reasoning Quality)
```
What are the ethical considerations of using AI in hiring decisions? Present multiple perspectives.
```

### 5. Code Review Question (Tests Adversarial Evaluation)
```python
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)
```
Review this code and suggest improvements.

## Expected Outcomes by Scenario

### Scenario 1 (3 Models)
- **Response Quality**: High (all premium models)
- **Diversity**: Moderate (GPT, Claude, Gemini perspectives)
- **Evaluation Depth**: 9 evaluations (3×3)
- **Best For**: Quick, high-quality answers

### Scenario 2 (5 Models)
- **Response Quality**: High to Very High
- **Diversity**: High (adds Chinese models Deepseek, Minimax)
- **Evaluation Depth**: 25 evaluations (5×5)
- **Best For**: Balanced quality and diversity

### Scenario 3 (8 Premium Models)
- **Response Quality**: Very High
- **Diversity**: Very High (GPT variants, Claude variants, Gemini, Deepseek, Minimax)
- **Evaluation Depth**: 64 evaluations (8×8)
- **Best For**: Maximum quality consultations

### Scenario 4 (10 Groq Models)
- **Response Quality**: Moderate to High (smaller models, but diverse)
- **Diversity**: Extreme (Llama, Kimi, GPT-OSS, Qwen, Compound variants)
- **Evaluation Depth**: 100 evaluations (10×10)
- **Best For**: Speed testing, architectural validation

### Scenario 5 (19 Models)
- **Response Quality**: Mixed (premium + smaller models)
- **Diversity**: Maximum possible
- **Evaluation Depth**: 361 evaluations (19×19)
- **Best For**: Stress testing, edge case discovery

## Performance Benchmarks

### Expected Timing Breakdown (Scenario 5 - Full Council)

**Phase 1: Initial Queries** (~30-60s)
- Groq models: ~5-10s (extremely fast)
- Premium models: ~20-40s
- AWS Nova: ~10-20s

**Phase 2: Evaluation** (~60-90s)
- 361 evaluations with overlapped execution
- Groq evaluations complete first (~20s)
- Premium evaluations follow (~60s)

**Phase 3: Synthesis** (~10-20s)
- Lead model synthesizes from all 19 responses

**Total Expected Time**: ~100-170s (1.5-3 minutes)

### Token Usage Estimates (Scenario 5)

**Initial Queries**: ~8,000-12,000 tokens
- 19 models × ~400-600 tokens per response

**Evaluations**: ~15,000-25,000 tokens
- 361 evaluations × ~50-80 tokens per evaluation

**Synthesis**: ~2,000-4,000 tokens
- Synthesis includes all 19 responses + scores

**Total**: ~25,000-40,000 tokens

**Cost**: $0.00 (all free models)

## Monitoring & Debugging

### What to Watch For

1. **Model Failures**:
   - Check DEBUG_MODE output for timeout/error messages
   - Review "Failed (N)" section in error output
   - Verify model IDs are correct

2. **Quality Variations**:
   - Compare scores across model sizes (8B vs 70B vs GPT-5.1)
   - Look for consistent patterns in evaluation reasoning
   - Check if smaller models rate themselves higher/lower

3. **Performance Bottlenecks**:
   - Monitor which models are slowest to respond
   - Check if evaluations overlap properly
   - Look for timeout issues

4. **Evaluation Bias**:
   - Do models recognize their own work despite anonymization?
   - Are Groq models harder/easier on each other?
   - Do premium models consistently rate each other higher?

## Troubleshooting

### Issue: Some Models Timeout

**Solution**: Increase timeout values
```
QUERY_TIMEOUT = 90
EVAL_TIMEOUT = 60
```

### Issue: Too Many Evaluations Take Too Long

**Solution**: Reduce model count or disable some techniques
```
MIN_REQUIRED_RESPONSES = 10  # Allow 9 failures
EVAL_USE_SOCRATIC_QUESTIONING = False
EVAL_USE_ADVERSARIAL_STANCE = False
```

### Issue: Inconsistent Scores

**Solution**: Enable more evaluation techniques for rigor
```
EVAL_USE_VERBALIZED_SAMPLING = True
EVAL_USE_CONSTITUTIONAL_PRINCIPLES = True
```

### Issue: Model Not Found

**Verification**: Use the exact model ID from your Open WebUI models list
- Settings → Models → Copy the exact ID

## Data Collection

### What to Record

For each test scenario, document:

1. **Configuration**:
   - Which models were queried
   - Which prompting techniques were enabled
   - Timeout settings

2. **Results**:
   - Total time elapsed
   - Number of successful responses
   - Number of failed models (and why)
   - Top 3 ranked responses with scores

3. **Observations**:
   - Quality of final synthesis
   - Evaluation reasoning depth
   - Any surprising score patterns
   - Model behavior anomalies

4. **Token Usage**:
   - Reported at end of session
   - Compare to estimates above

## Next Steps After Testing

1. **Analyze Results**:
   - Which model combinations work best?
   - What's the sweet spot for quality vs. time?
   - Are there must-have models?

2. **Create Recommended Configs**:
   - "Fast & Free" (Groq models)
   - "Balanced Quality" (5-8 premium models)
   - "Maximum Insight" (12-15 mixed models)

3. **Document Issues**:
   - Models that consistently timeout
   - Evaluation biases discovered
   - Edge cases that break the system

4. **Optimize**:
   - Adjust default timeout values
   - Fine-tune prompting technique defaults
   - Update recommended MIN_REQUIRED_RESPONSES

---

**Testing Version**: v0.5.0+
**Total Models Available**: 19 (all free)
**Maximum Evaluations**: 361 (19×19)
**Estimated Maximum Cost**: $0.00
**Recommended Starting Point**: Scenario 2 (5 models)
