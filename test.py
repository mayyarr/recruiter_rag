"""
test.py - Experiment runner for tuning the CV RAG system.

For each (max_words, overlap) chunk setting, it:
  1. Rebuilds chunks + embeddings from scratch (chunk settings affect the
     chunks themselves, so embeddings MUST be rebuilt every time they change).
  2. Runs every test question through retrieval at top_k = 1, 3, 5, 7.
  3. Prints the retrieved sources (with similarity scores) so you can
     manually judge relevance and irrelevance.

This does NOT auto-pick the "best" config for you -- relevance judgment
is done by you, reading the printed sources against what you know about
the CVs in your docs/ folder. That's intentional (see task step 6:
"Do not choose the best settings from one question only").
"""

import os
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

FOLDER_PATH = "docs"

TEST_QUESTIONS = [
    "Who has experience with RAG?",
    "Who has machine learning experience?",
    "Who has React experience?",
    "Who has FastAPI experience?",
    "Who has retrieval evaluation experience?",
    "Who has experience with human approval?",
    "Who has a Kubernetes certification?",
    "Who has experience with semantic search or embeddings?",
    "Who has worked with vector databases such as Qdrant, pgvector, or FAISS?",
    "Who has experience with CI/CD or deployment?",
    "Does Rami have production RAG or tool-using agent experience?",
    "Which candidates mention both Python and REST API experience?",
]

CHUNK_SETTINGS = [
    (100, 20),
    (150, 30),
    (200, 40),
    (250, 50),
]

TOP_K_VALUES = [1, 3, 5, 7]

embed_model = SentenceTransformer("all-MiniLM-L6-v2")


def load_cv_texts(folder_path):
    """Read every PDF once. This does NOT depend on chunk settings,
    so we only need to do it a single time."""
    all_texts = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            path = os.path.join(folder_path, filename)
            reader = PdfReader(path)
            pdf_text = ""
            for page in reader.pages:
                pdf_text += page.extract_text() + "\n"
            all_texts.append((filename, pdf_text))
    return all_texts


def chunk_text(text, max_words, overlap):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + max_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks


def build_chunks_and_embeddings(all_texts, max_words, overlap):
    """Rebuild chunks + embeddings for ONE chunk setting."""
    all_chunks = []
    for filename, text in all_texts:
        for chunk in chunk_text(text, max_words, overlap):
            all_chunks.append({"source": filename, "text": chunk})

    chunk_texts = [c["text"] for c in all_chunks]
    chunk_embeddings = embed_model.encode(chunk_texts)
    return all_chunks, chunk_embeddings


def retrieve_chunks(question, all_chunks, chunk_embeddings, top_k):
    query_embedding = embed_model.encode([question])
    similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]
    top_indices = similarities.argsort()[-top_k:][::-1]

    results = []
    for index in top_indices:
        results.append({
            "score": similarities[index],
            "source": all_chunks[index]["source"],
        })
    return results


def unique_sources(results):
    seen = []
    for r in results:
        if r["source"] not in seen:
            seen.append(r["source"])
    return seen


def run_experiments():
    print("Loading CV PDFs...")
    all_texts = load_cv_texts(FOLDER_PATH)
    print(f"Number of CVs: {len(all_texts)}\n")

    for max_words, overlap in CHUNK_SETTINGS:
        print("=" * 80)
        print(f"CHUNK SETTING: max_words={max_words}, overlap={overlap}")
        print("=" * 80)

        all_chunks, chunk_embeddings = build_chunks_and_embeddings(
            all_texts, max_words, overlap
        )
        print(f"Total chunks: {len(all_chunks)}\n")

        for question in TEST_QUESTIONS:
            print(f"Q: {question}")
            for top_k in TOP_K_VALUES:
                results = retrieve_chunks(
                    question, all_chunks, chunk_embeddings, top_k
                )
                sources = unique_sources(results)
                scores = [f"{r['score']:.2f}" for r in results]
                print(f"  top_k={top_k}: sources={sources} scores={scores}")
            print()


if __name__ == "__main__":
    run_experiments()