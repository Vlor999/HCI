from typing import List, Tuple, Optional, Any
import chromadb
from chromadb.utils import embedding_functions


class ChromaVectorStore:
    def __init__(self, persist_dir: str = "chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection("questions")
        self.embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

    def add_questions(
        self, questions: List[str], metadatas: Optional[List[dict[str, Any]]] = None
    ) -> None:
        embeddings = self.embedder(questions)
        ids = [f"q_{i}" for i in range(len(questions))]
        if metadatas is None:
            metadatas = [{"source": "question"} for _ in questions]
        else:
            metadatas = [{**m} if m else {"source": "question"} for m in metadatas]
        self.collection.add(
            embeddings=embeddings, documents=questions, metadatas=metadatas, ids=ids
        )

    def query(self, query: str, n_results: int = 3) -> List[Tuple[str, float]]:
        embedding = self.embedder([query])
        results = self.collection.query(query_embeddings=embedding, n_results=n_results)
        docs = results.get("documents", [[]])[0]
        scores = results.get("distances", [[]])[0]
        return list(zip(docs, scores))
