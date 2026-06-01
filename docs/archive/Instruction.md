# Migrate Entire QuizGenApp Pipeline from qwen3:1.7b to qwen3:4b

## Background

The project currently uses:

```text
qwen3:1.7b
```

for all LLM-powered stages:

* Curator
* Pedagogue Stage A
* Pedagogue Stage B
* Pedagogue Stage C
* Adversary
* Explainer (if enabled)

Recent runs show instability:

* JSON parse failures
* Explanation generation failures
* Missing answers
* Missing explanations
* Inconsistent outputs across identical runs

The system owner has already installed:

```text
qwen3:4b
```

via Ollama.

The objective is to migrate the entire project to qwen3:4b as the new default model.

---

# Required Changes

## 1. Locate All Hardcoded Model References

Search the entire codebase for:

```python
"qwen3:1.7b"
```

Replace all occurrences with:

```python
"qwen3:4b"
```

Check:

* config files
* constants
* environment defaults
* CLI defaults
* Ollama provider
* fallback logic
* test files

---

## 2. Update Default Model Configuration

Find the global configuration source.

Examples:

```python
DEFAULT_MODEL
MODEL_NAME
OLLAMA_MODEL
```

Change default value:

```python
qwen3:4b
```

The system should start using qwen3:4b even when the user does not specify a model.

---

## 3. Verify Runtime Model Detection

Current logs show:

```text
LLMProvider: Model 'qwen3:1.7b' is available
```

After migration it must become:

```text
LLMProvider: Model 'qwen3:4b' is available
```

Verify:

```python
ollama list
```

or equivalent provider checks.

---

## 4. Add Automatic Fallback

If qwen3:4b is unavailable:

```text
fallback order:
```

```python
[
    "qwen3:4b",
    "qwen3:1.7b"
]
```

Pseudo-code:

```python
try:
    use("qwen3:4b")
except:
    use("qwen3:1.7b")
```

Log clearly:

```text
Primary model unavailable.
Falling back to qwen3:1.7b
```

---

## 5. Add Startup Validation

At application startup:

Validate:

```python
qwen3:4b
```

exists in Ollama.

If missing:

```python
raise RuntimeError(...)
```

with message:

```text
qwen3:4b is not installed.

Run:

ollama pull qwen3:4b
```

unless fallback mode is enabled.

---

## 6. Improve Generation Parameters for qwen3:4b

Review all Ollama generation settings.

Current settings optimized for 1.7B may not be ideal.

Evaluate:

```python
temperature
top_p
top_k
num_predict
repeat_penalty
```

Recommended defaults:

```python
temperature = 0.2
top_p = 0.9
repeat_penalty = 1.1
```

for stable JSON generation.

The goal is deterministic quiz generation.

---

## 7. Reduce Hallucination

For:

* Pedagogue Stage B
* Pedagogue Stage C
* Adversary

Add stricter instructions:

```text
Use ONLY the provided source excerpt.

Do not use external knowledge.

If the answer cannot be supported by the source,
mark the question as unsupported.
```

qwen3:4b should perform better but prompts should still be strengthened.

---

## 8. Logging Improvements

At startup log:

```text
================================================
ACTIVE MODEL CONFIGURATION
================================================
Primary Model : qwen3:4b
Fallback Model: qwen3:1.7b
================================================
```

Before every Ollama call:

```text
Using model: qwen3:4b
```

This makes future debugging easier.

---

## 9. Validation

Run:

```bash
python main.py --mode fast --num 5
```

and

```bash
python main.py --mode accuracy --num 5
```

Verify:

* qwen3:4b is actually used
* no references to qwen3:1.7b remain
* pipeline completes successfully
* quiz exports correctly

---

# Deliverables

Provide:

1. List of modified files.
2. Before/after code snippets.
3. Startup log showing qwen3:4b loaded.
4. Verification that all stages use qwen3:4b.
5. Any additional recommendations for improving JSON reliability.

Do not redesign the architecture.

Only perform a clean migration from qwen3:1.7b to qwen3:4b while preserving existing functionality.
