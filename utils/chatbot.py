import os
from typing import List, Tuple

import numpy as np
import streamlit as st

try:
    import openai
    HAVE_CHATBOT = True
except Exception:  # pragma: no cover - gracefully handle missing dependency
    openai = None
    HAVE_CHATBOT = False

DOCS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")


def _load_docs(path: str = DOCS_PATH) -> List[Tuple[str, str]]:
    """Load plain text documents from the docs directory."""
    docs: List[Tuple[str, str]] = []
    if not os.path.isdir(path):
        return docs
    for name in os.listdir(path):
        file_path = os.path.join(path, name)
        if os.path.isfile(file_path):
            with open(file_path, "r", encoding="utf-8") as fh:
                docs.append((name, fh.read()))
    return docs


def _embed(text: str) -> np.ndarray:
    """Create an embedding for the given text using OpenAI."""
    response = openai.Embedding.create(model="text-embedding-ada-002", input=text)
    return np.array(response["data"][0]["embedding"], dtype=float)


@st.cache_resource(show_spinner=False)
def _indexed_docs():
    """Return documents and their embeddings, cached for reuse."""
    docs = _load_docs()
    if not docs:
        return [], []
    embeddings = [_embed(content) for _, content in docs]
    return docs, embeddings


def ask(question: str) -> str:
    """Answer a question using local documents and OpenAI completion."""
    if not HAVE_CHATBOT:
        return "OpenAI package is not installed. Please install dependencies to use chat."
    if not os.getenv("OPENAI_API_KEY"):
        return "OpenAI API key not found. Set OPENAI_API_KEY to enable chat."

    docs, embeddings = _indexed_docs()
    if not docs:
        return "No reference documents are available for answering questions."

    query_vec = _embed(question)
    sims = [float(np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb))) for emb in embeddings]
    best_doc, context = docs[int(np.argmax(sims))]

    prompt = (
        "Use the following document excerpt to answer the question.\n"
        f"Document: {best_doc}\n\n{context}\n\nQuestion: {question}"
    )
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return completion["choices"][0]["message"]["content"]
