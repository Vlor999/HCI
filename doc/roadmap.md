# Human-Robot Communication with LLMs: Project Roadmap

## 🎯 Objective

To bridge the communication gap between humans and robots by integrating a Large Language Model (LLM) into a robot system. The goal is to make the robot capable of **explaining its actions, decisions, and use of low-level perception data** in natural language to build **trust and interpretability**.

---

## TODO?

- [] Fine-tuning
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
