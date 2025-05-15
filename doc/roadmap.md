# Human-Robot Communication with LLMs: Project Roadmap

## 🎯 Objective

To bridge the communication gap between humans and robots by integrating a Large Language Model (LLM) into a robot system. The goal is to make the robot capable of **explaining its actions, decisions, and use of low-level perception data** in natural language to build **trust and interpretability**.

---

## 📋 Roadmap

### 1. 📚 Extend the RAG System

- Structure your documents used in the RAG (robot manuals, perception logs, decision trees).
- Enrich the corpus with **annotated scenarios** showing natural language explanations of actions.
- Include **temporal context**: explain sequences of actions.
- Prompt engineering: improve prompt templates for consistent, accurate explanations.

### 2. 🧠 Lightweight Fine-Tuning (if needed)

If the LLM doesn't understand specific robotic context:

- Use tools like **QLoRA + Hugging Face Transformers**.
- Build a dataset with input-output pairs:
  ```
  Input: "Why did you turn left?"
  Output: "I turned left because the lidar detected an obstacle on the right at 0.5 meters."
  ```
- Use Colab or a local GPU for training a small model if compute is limited.

### 3. 🏗️ Integration Framework Design

Start outlining a clear architecture:

- **Perception Layer** -> Raw sensor data (lidar, camera, etc.)
- **Decision Layer** -> Planning module or logic
- **Explanation Layer** -> RAG or LLM generating natural language

Add interfaces and consider:
- Latency for real-time use
- Error detection or fallback mechanisms
- Model confidence scoring (optional)

### 4. 💬 HRI Prototype Interface

Build a simple user interface to:
- Input queries
- Show explanations
- Optionally show raw perception info used in the explanation

CLI, web-based, or robot tablet interface – start simple.

**Done**

### 5. 📊 Evaluation Preparation

Design how you'll evaluate the system:
- Use scenario-based evaluations
- Ask users to rate explanation clarity and trust
- Log failures or incoherent outputs

Plan an A/B test if you compare RAG-only vs fine-tuned LLM.

---

## ✅ Immediate Next Steps

| Task | Action |
|------|--------|
| RAG Improvement | Enrich documents and refine prompts |
| Integration Design | Map flow from sensors → logic → LLM |
| Dataset | Build sample explanations for fine-tuning |
| UI | Create minimal interface for querying |
| Evaluation | Draft criteria and test scenarios |

---

## TODO?

- [] Generate datasets or prompts
- [] Fine-tuning
- [] Review code
- [] Evaluation
Integration with RAG
  All these models are great for:
  * Embedding queries and documents using a local vector store like chromadb.
  * Responding with context-aware answers when provided retrieved passages.
  If you're building a pipeline:
  1. Use a sentence-transformer (like bge-small-en or all-MiniLM-L6-v2) for embeddings.
  2. Retrieve the top relevant documents.
  3. Pass those as context to your local LLM via Ollama's prompt.

  Use RAG chunking strategy with LangChain/LlamaIndex to overcome context window limits

---

## Tips for Integration
Use embedding of perception info into a prompt-friendly format (structured JSON, summarized text, etc.).

Pair with a retriever or contextual memory module if the robot needs to refer to prior actions or sensory inputs.

Prioritize low-latency quantized variants for real-time interaction scenarios.
