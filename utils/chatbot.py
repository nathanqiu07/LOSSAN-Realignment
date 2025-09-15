import os
import streamlit as st

# LangChain underwent major package restructuring after version 0.1.
# Try imports for the newer packages first, then fall back to the
# legacy paths for older versions. If any import fails, the chat
# feature is disabled gracefully.
HAVE_LANGCHAIN = False
try:  # New-style imports (langchain>=0.1)
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings, OpenAI
    from langchain_community.vectorstores import Chroma
    from langchain.chains import RetrievalQA
    from langchain_core.documents import Document
    HAVE_LANGCHAIN = True
except Exception:  # Fall back to pre-0.1 style
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain.embeddings.openai import OpenAIEmbeddings
        from langchain.vectorstores import Chroma
        from langchain.llms import OpenAI
        from langchain.chains import RetrievalQA
        from langchain.schema import Document
        HAVE_LANGCHAIN = True
    except Exception:
        HAVE_LANGCHAIN = False

DOCS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")


def _load_documents(path: str = DOCS_PATH):
    """Load text files from the docs directory as LangChain Documents."""
    documents = []
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            documents.append(Document(page_content=content, metadata={"source": filename}))
    return documents


@st.cache_resource(show_spinner=False)
def get_qa_chain():
    """Create a RetrievalQA chain backed by a Chroma vector store."""
    if not HAVE_LANGCHAIN:
        return None

    docs = _load_documents()
    if not docs:
        return None

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)
    embeddings = OpenAIEmbeddings()
    vectordb = Chroma.from_documents(splits, embeddings)
    llm = OpenAI(temperature=0)
    chain = RetrievalQA.from_chain_type(
        llm=llm, chain_type="stuff", retriever=vectordb.as_retriever()
    )
    return chain


def ask(question: str) -> str:
    """Return an answer to the user's question using the QA chain."""
    if not HAVE_LANGCHAIN:
        return "LangChain is not installed. Please install dependencies to use chat."

    chain = get_qa_chain()
    if chain is None:
        return "No documents available for answering questions."
    result = chain({"query": question})
    return result["result"]
