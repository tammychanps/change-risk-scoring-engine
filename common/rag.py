"""
RAG (Retrieval-Augmented Generation) utilities using FAISS.

Loads documents, splits into chunks, creates FAISS vectorstore,
and retrieves relevant context for LLM prompts.

Uses FAISS (in-memory) instead of ChromaDB because:
- These document sets are small (3-30 docs, <50KB total)
- No database server needed
- No Windows installation issues
- Same LangChain API as ChromaDB
"""

import os
from pathlib import Path
from typing import List, Optional

# Try to import FAISS + LangChain; graceful fallback if not installed
_faiss_available = None


def _check_faiss():
    global _faiss_available
    if _faiss_available is not None:
        return _faiss_available
    try:
        import faiss  # noqa: F401
        from langchain_community.vectorstores import FAISS  # noqa: F401
        _faiss_available = True
    except ImportError:
        _faiss_available = False
        print("[!] FAISS not installed. RAG features disabled.")
        print("  Run: pip install faiss-cpu langchain-community")
    return _faiss_available


def load_documents_from_folder(folder_path: str, glob_pattern: str = "*.md") -> List[dict]:
    """
    Load text documents from a folder.

    Returns list of dicts: [{"content": "...", "source": "filename.md"}, ...]
    """
    docs = []
    folder = Path(folder_path)
    if not folder.exists():
        print(f"  Warning: folder not found: {folder_path}")
        return docs
    for filepath in sorted(folder.glob(glob_pattern)):
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        if content.strip():
            docs.append({"content": content, "source": filepath.name})
    return docs


def load_documents_from_json(json_path: str, text_field: str = "description") -> List[dict]:
    """
    Load documents from a JSON array file.

    Each JSON object becomes a document. The `text_field` is used as the main text.
    Other fields are preserved as metadata.
    """
    import json
    docs = []
    filepath = Path(json_path)
    if not filepath.exists():
        print(f"  Warning: file not found: {json_path}")
        return docs
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        for item in data:
            text = str(item.get(text_field, ""))
            if not text.strip():
                # Try concatenating all string fields
                text = " ".join(str(v) for v in item.values() if isinstance(v, str))
            docs.append({"content": text, "source": json_path, "metadata": item})
    return docs


def create_retriever(documents: List[dict], k: int = 3) -> Optional[object]:
    """
    Create a FAISS retriever from a list of documents.

    Args:
        documents: List of {"content": str, "source": str} dicts
        k: Number of similar documents to retrieve

    Returns:
        A LangChain retriever, or None if FAISS is unavailable
    """
    if not _check_faiss() or not documents:
        return None

    try:
        from langchain_community.vectorstores import FAISS
        from langchain_community.embeddings import OllamaEmbeddings
        from langchain.schema import Document

        # Convert to LangChain Documents
        lc_docs = [
            Document(
                page_content=doc["content"],
                metadata={"source": doc.get("source", "unknown")}
            )
            for doc in documents
            if doc["content"].strip()
        ]

        if not lc_docs:
            return None

        # Create embeddings using Ollama
        from common.llm import OLLAMA_BASE_URL, OLLAMA_MODEL
        try:
            embeddings = OllamaEmbeddings(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
            )
            vectorstore = FAISS.from_documents(lc_docs, embeddings)
            return vectorstore.as_retriever(search_kwargs={"k": min(k, len(lc_docs))})
        except Exception as e:
            print(f"  RAG setup error (Ollama may not be running): {e}")
            return None
    except ImportError as e:
        print(f"  RAG import error: {e}")
        return None


def retrieve_context(retriever, query: str) -> str:
    """
    Retrieve relevant context for a query.

    Returns concatenated text from top-k similar documents,
    or empty string if retriever is None.
    """
    if retriever is None:
        return ""
    try:
        docs = retriever.invoke(query)
        if not docs:
            return ""
        context_parts = []
        for doc in docs:
            source = doc.metadata.get("source", "unknown")
            context_parts.append(f"[Source: {source}]\n{doc.page_content}")
        return "\n\n---\n\n".join(context_parts)
    except Exception as e:
        print(f"  RAG retrieval error: {e}")
        return ""
