# Quick Configuration Reference - Council of LLMs

**Purpose**: Copy-paste configurations for common testing scenarios
**Version**: v0.5.0+

## 🚀 Quick Start Configs (Copy-Paste Ready)

### Scenario 1: Baseline (3 Premium Models) ⚡ FASTEST QUALITY

```
MODELS_TO_QUERY = gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-2.5-flash
LEAD_MODEL = gpt-5.1
MIN_REQUIRED_RESPONSES = 3
```

**Expected Time**: 30-60s | **Evaluations**: 9 | **Quality**: ⭐⭐⭐⭐⭐

---

### Scenario 2: Recommended (5 Premium Models) ⭐ BEST BALANCE

```
MODELS_TO_QUERY = gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-2.5-flash,deepseek/deepseek-chat-v3.1,minimax/minimax-m2
LEAD_MODEL = gpt-5.1
MIN_REQUIRED_RESPONSES = 5
```

**Expected Time**: 45-90s | **Evaluations**: 25 | **Quality**: ⭐⭐⭐⭐⭐

---

### Scenario 3: Premium Plus (8 Premium Models) 🏆 MAXIMUM QUALITY

```
MODELS_TO_QUERY = gpt-5.1,gpt-5.1-chat-latest,o3,anthropic/claude-sonnet-4.5,anthropic/claude-haiku-4.5,google/gemini-2.5-flash,minimax/minimax-m2,deepseek/deepseek-chat-v3.1
LEAD_MODEL = gpt-5.1
MIN_REQUIRED_RESPONSES = 8
```

**Expected Time**: 60-120s | **Evaluations**: 64 | **Quality**: ⭐⭐⭐⭐⭐+

---

### Scenario 4: Groq Speed Test (10 Groq Models) 🏃 SPEED DEMON

```
MODELS_TO_QUERY = groq.moonshotai/kimi-k2-instruct,groq.llama-3.1-8b-instant,groq.llama-3.3-70b-versatile,groq.openai/gpt-oss-120b,groq.openai/gpt-oss-20b,groq.groq/compound,groq.groq/compound-mini,groq.meta-llama/llama-4-maverick-17b-128e-instruct,groq.meta-llama/llama-4-scout-17b-16e-instruct,groq.qwen/qwen3-32b
LEAD_MODEL = groq.llama-3.3-70b-versatile
MIN_REQUIRED_RESPONSES = 10
```

**Expected Time**: 20-40s | **Evaluations**: 100 | **Quality**: ⭐⭐⭐⭐

---

### Scenario 5: Full Council (All 19 Models) 💪 STRESS TEST

```
MODELS_TO_QUERY = gpt-5.1,gpt-5.1-chat-latest,o3,anthropic/claude-sonnet-4.5,anthropic/claude-haiku-4.5,google/gemini-2.5-flash,minimax/minimax-m2,deepseek/deepseek-chat-v3.1,groq.moonshotai/kimi-k2-instruct,groq.llama-3.1-8b-instant,groq.llama-3.3-70b-versatile,groq.openai/gpt-oss-120b,groq.openai/gpt-oss-20b,groq.groq/compound,groq.groq/compound-mini,groq.meta-llama/llama-4-maverick-17b-128e-instruct,groq.meta-llama/llama-4-scout-17b-16e-instruct,groq.qwen/qwen3-32b,amazon/nova-2-lite-v1:free
LEAD_MODEL = gpt-5.1
MIN_REQUIRED_RESPONSES = 15
```

**Expected Time**: 100-170s | **Evaluations**: 361 | **Quality**: ⭐⭐⭐⭐⭐ (diverse)

---

## 🔧 Recommended Base Settings for All Scenarios

```
ENABLE_STREAMING = True
SHOW_INDIVIDUAL_RESPONSES = True
SHOW_EVALUATION_SCORES = True
SHOW_REASONING = True
DEBUG_MODE = True

QUERY_TIMEOUT = 60
EVAL_TIMEOUT = 45
SYNTHESIS_TIMEOUT = 60

# Evaluation techniques (all enabled for testing)
EVAL_USE_HERMENEUTIC_CIRCLE = True
EVAL_USE_VERBALIZED_SAMPLING = True
EVAL_USE_SOCRATIC_QUESTIONING = True
EVAL_USE_ADVERSARIAL_STANCE = True
EVAL_USE_CONSTITUTIONAL_PRINCIPLES = True

# Query techniques (all enabled for testing)
QUERY_USE_HERMENEUTIC_CIRCLE = True
QUERY_USE_CHAIN_OF_THOUGHT = True
QUERY_USE_VERBALIZED_SAMPLING = True

# Synthesis techniques
SYNTH_USE_META_COGNITIVE = True
```

---

## 🎯 Test Questions (Copy-Paste Ready)

### Question 1: Technical (JavaScript Async)
```
What are the key differences between async/await and traditional callbacks in JavaScript, and when should each be used?
```

### Question 2: Creative Analogy (Quantum Physics)
```
Explain quantum entanglement to a 10-year-old using an everyday analogy.
```

### Question 3: Architecture Design (Multi-Part)
```
Design a microservices architecture for an e-commerce platform. Include: 1) Service breakdown, 2) Communication patterns, 3) Data consistency strategies, 4) Deployment considerations.
```

### Question 4: Ethics (Nuanced)
```
What are the ethical considerations of using AI in hiring decisions? Present multiple perspectives.
```

### Question 5: Code Review (Critical Analysis)
```python
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)
```
Review this code and suggest improvements.

### Question 6: Ethics (AI Use in Education)
```
Is it ethical to use AI to write college essays?
```

### Question 7: Debugging (Error Diagnosis)
```
My Python code throws 'KeyError' - help!
```

### Question 8: Technology Implications
```
What are interesting implications of quantum computing?
```

### Question 9: Political Philosophy (Loaded Question)
```
Why is libertarianism obviously wrong?
```

### Question 10: Meta-Evaluation
```
How should I evaluate AI responses to this question?
```

---

## 📊 Model ID Quick Reference

### Premium Models
- `gpt-5.1`
- `gpt-5.1-chat-latest`
- `o3`
- `anthropic/claude-sonnet-4.5`
- `anthropic/claude-haiku-4.5`
- `google/gemini-2.5-flash`
- `minimax/minimax-m2`
- `deepseek/deepseek-chat-v3.1`

### Groq Models
- `groq.moonshotai/kimi-k2-instruct`
- `groq.llama-3.1-8b-instant`
- `groq.llama-3.3-70b-versatile`
- `groq.openai/gpt-oss-120b`
- `groq.openai/gpt-oss-20b`
- `groq.groq/compound`
- `groq.groq/compound-mini`
- `groq.meta-llama/llama-4-maverick-17b-128e-instruct`
- `groq.meta-llama/llama-4-scout-17b-16e-instruct`
- `groq.qwen/qwen3-32b`

### AWS Bedrock
- `amazon/nova-2-lite-v1:free`

---

## ⚡ Performance Tuning Tips

### If Models Timeout
```
QUERY_TIMEOUT = 90
EVAL_TIMEOUT = 60
MIN_REQUIRED_RESPONSES = [N-3]  # Allow 3 failures
```

### If Evaluations Take Too Long
```
EVAL_USE_SOCRATIC_QUESTIONING = False
EVAL_USE_ADVERSARIAL_STANCE = False
```

### If You Want Faster Results (Quality Trade-off)
```
QUERY_USE_CHAIN_OF_THOUGHT = False
QUERY_USE_VERBALIZED_SAMPLING = False
```

### If You Want Maximum Rigor (Slower)
```
QUERY_USE_CHAIN_OF_THOUGHT = True
QUERY_USE_VERBALIZED_SAMPLING = True
EVAL_USE_SOCRATIC_QUESTIONING = True
EVAL_USE_ADVERSARIAL_STANCE = True
EVAL_USE_CONSTITUTIONAL_PRINCIPLES = True
```

---

## 🔍 How to Apply Configurations

### Method 1: Via Open WebUI UI
1. Navigate to **Admin Panel → Functions**
2. Find **Council of LLMs Orchestrator**
3. Click **⚙️ Settings** (gear icon)
4. Paste configuration values into Valves
5. Click **Save**

### Method 2: Via update_functions.py
Edit the JSON files before import to include your desired Valve values.

---

## 📈 What to Expect

### Scenario 1 (3 Models)
- ✅ Fast, high-quality results
- ✅ Good for quick consultations
- ⚠️ Less diversity in perspectives

### Scenario 2 (5 Models) ⭐ RECOMMENDED
- ✅ Best balance of quality, speed, diversity
- ✅ Adds Chinese models for global perspective
- ✅ Reasonable evaluation depth (25 evaluations)

### Scenario 3 (8 Models)
- ✅ Maximum quality from premium models
- ✅ GPT, Claude, Gemini, Deepseek, Minimax perspectives
- ⚠️ Slower (60-120s)
- ⚠️ More token usage

### Scenario 4 (10 Groq Models)
- ✅ Extremely fast (20-40s)
- ✅ Tests overlapped execution architecture
- ⚠️ More variable quality (smaller models)

### Scenario 5 (19 Models)
- ✅ Maximum diversity and stress testing
- ✅ 361 evaluations for robust scoring
- ⚠️ Longest time (100-170s)
- ⚠️ Highest token usage (~30k-40k)

---

**Quick Reference Version**: 1.0
**Compatible With**: Council v0.5.0+
**Last Updated**: 2025-12-05
