import os
import re
import pickle
from pypdf import PdfReader
from llm import call_llm
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

folder_path = "docs"
INDEX_FILE = "rag_index.pkl"  # كاش الـ embeddings على القرص

CONFIDENCE_THRESHOLD = 0.20

# --- حالة الفهرس بالذاكرة (تتعبى مرة وحدة عند أول استخدام) ---
_embed_model = None
_all_chunks = []          # [{"source": filename, "text": chunk}, ...]
_chunk_embeddings = None  # numpy array
_indexed_files = set()    # أسماء الملفات اللي أصلاً متفهرسة


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def chunk_text(text, max_words=150, overlap=30):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + max_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks


def _display_name_from_filename(filename):
    """Turn a CV filename like 'Ahmad_Khalil.pdf' into 'Ahmad Khalil'."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\b(cv|resume|final|v\d+)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title()


def get_candidate_name_map():
    """{filename: 'First Last'} for every CV currently in the index."""
    return {f: _display_name_from_filename(f) for f in _indexed_files}


def match_candidate_sources(query):
    """يرجّع أسماء ملفات (sources) المرشحين المذكورين صراحة بالسؤال.

    بيقارن كل كلمة بالسؤال مع الاسم الأول/الأخير لكل مرشح متفهرس،
    مع سماحية بسيطة لفروقات إملائية شائعة (مثلاً Sara/Sarah) عن طريق
    مطابقة البادئة (startswith) بالاتجاهين بدل التطابق الحرفي فقط.
    هاد بيسمح لنا نقيّد البحث الدلالي على سيرة مرشح محدد بدل البحث
    العام بكل الفهرس، يلي ممكن يجيب مقاطع من مرشح غلط اسمه ما انذكر.
    """
    q_words = re.findall(r"[A-Za-z]+", query.lower())
    matched = []

    for filename, name in get_candidate_name_map().items():
        name_parts = [p.lower() for p in name.split()]

        for q_word in q_words:
            if len(q_word) < 3:
                continue
            for part in name_parts:
                if len(part) < 3:
                    continue
                if q_word == part or q_word.startswith(part) or part.startswith(q_word):
                    matched.append(filename)
                    break
            else:
                continue
            break

    return matched


def _extract_pdf_text(path):
    reader = PdfReader(path)
    pdf_text = ""
    for page in reader.pages:
        pdf_text += (page.extract_text() or "") + "\n"
    return pdf_text


def _save_index():
    """يحفظ الفهرس الحالي بملف على القرص عشان ما نعيد بناء كل شي
    بالتشغيلة الجاية."""
    with open(INDEX_FILE, "wb") as f:
        pickle.dump(
            {
                "all_chunks": _all_chunks,
                "chunk_embeddings": _chunk_embeddings,
                "indexed_files": _indexed_files,
            },
            f,
        )


def _load_index_from_disk():
    global _all_chunks, _chunk_embeddings, _indexed_files
    if not os.path.exists(INDEX_FILE):
        return False
    try:
        with open(INDEX_FILE, "rb") as f:
            data = pickle.load(f)
        _all_chunks = data["all_chunks"]
        _chunk_embeddings = data["chunk_embeddings"]
        _indexed_files = data["indexed_files"]
        return True
    except Exception as e:
        print("Could not load rag_index.pkl, will rebuild:", e)
        return False


def _build_index_from_folder():
    """يبني الفهرس من الصفر بقراءة كل PDFs الموجودة بمجلد docs."""
    global _all_chunks, _chunk_embeddings, _indexed_files

    all_texts = []
    os.makedirs(folder_path, exist_ok=True)
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            path = os.path.join(folder_path, filename)
            pdf_text = _extract_pdf_text(path)
            all_texts.append((filename, pdf_text))

    all_chunks = []
    for filename, text in all_texts:
        for chunk in chunk_text(text):
            all_chunks.append({"source": filename, "text": chunk})

    _all_chunks = all_chunks
    _indexed_files = {filename for filename, _ in all_texts}

    if all_chunks:
        model = _get_embed_model()
        chunk_texts = [c["text"] for c in all_chunks]
        _chunk_embeddings = model.encode(chunk_texts)
    else:
        _chunk_embeddings = None

    _save_index()
    print(f"RAG index built: {len(_all_chunks)} chunks from {len(_indexed_files)} CVs")


def load_or_build_index():
    """تُستدعى مرة وحدة عند تشغيل السيرفر (من app.py).
    تحاول تحمّل الفهرس من القرص، وإذا مش موجود أو أسماء الملفات
    اختلفت عن الفهرس المحفوظ، تعيد البناء من الصفر."""
    loaded = _load_index_from_disk()

    if not loaded:
        _build_index_from_folder()
        return

    # تحقق: هل فيه ملفات بمجلد docs مش موجودة بالفهرس المحفوظ؟
    os.makedirs(folder_path, exist_ok=True)
    current_files = {f for f in os.listdir(folder_path) if f.endswith(".pdf")}
    missing = current_files - _indexed_files

    if missing:
        print(f"Found {len(missing)} new CV(s) not in saved index, adding them...")
        for filename in missing:
            _add_single_pdf(filename)


def _add_single_pdf(filename):
    """يضيف ملف PDF واحد (موجود أصلاً بمجلد docs) للفهرس القائم
    بدون إعادة بناء باقي الفهرس. يُستخدم داخليًا من load_or_build_index
    ومن add_pdf_to_index."""
    global _all_chunks, _chunk_embeddings, _indexed_files

    path = os.path.join(folder_path, filename)
    pdf_text = _extract_pdf_text(path)
    new_chunks = [
        {"source": filename, "text": chunk} for chunk in chunk_text(pdf_text)
    ]

    if not new_chunks:
        _indexed_files.add(filename)
        return

    model = _get_embed_model()
    new_embeddings = model.encode([c["text"] for c in new_chunks])

    _all_chunks.extend(new_chunks)
    _indexed_files.add(filename)

    if _chunk_embeddings is None:
        _chunk_embeddings = new_embeddings
    else:
        import numpy as np
        _chunk_embeddings = np.vstack([_chunk_embeddings, new_embeddings])


def add_pdf_to_index(filename):
    """تُستدعى من app.py بعد ما يوصل السيفي الجديد لمجلد docs.
    بتضيفه للفهرس القائم وبتحفظ الفهرس المحدث على القرص."""
    if filename in _indexed_files:
        return {"success": False, "message": f"{filename} already indexed"}

    _add_single_pdf(filename)
    _save_index()
    return {
        "success": True,
        "message": f"{filename} added to index",
        "total_cvs": len(_indexed_files),
    }


def retrieve_chunks(question, top_k=3, allowed_sources=None):
    """allowed_sources: لو انبعتت (لستة أسماء ملفات)، البحث الدلالي بيصير
    بس ضمن مقاطع هالملفات، بدل كل الفهرس. مفيدة لما السؤال بيذكر اسم
    مرشح محدد، حتى ما يرجع مقاطع من مرشح تاني بالغلط."""
    if not _all_chunks or _chunk_embeddings is None:
        return []

    if allowed_sources:
        indices = [
            i for i, c in enumerate(_all_chunks) if c["source"] in allowed_sources
        ]
        if not indices:
            return []
        chunks_subset = [_all_chunks[i] for i in indices]
        embeddings_subset = _chunk_embeddings[indices]
    else:
        chunks_subset = _all_chunks
        embeddings_subset = _chunk_embeddings

    model = _get_embed_model()
    query_embedding = model.encode([question])

    similarities = cosine_similarity(query_embedding, embeddings_subset)[0]
    k = min(top_k, len(chunks_subset))
    top_indices = similarities.argsort()[-k:][::-1]

    results = []
    for index in top_indices:
        results.append(
            {
                "score": float(similarities[index]),
                "source": chunks_subset[index]["source"],
                "text": chunks_subset[index]["text"],
            }
        )
    return results


def get_unique_sources(retrieved):
    unique_sources = []
    for result in retrieved:
        if result["source"] not in unique_sources:
            unique_sources.append(result["source"])
    return unique_sources


def trim_snippet(text, max_chars=260):
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def get_evidence_by_source(retrieved):
    evidence = {}
    for result in retrieved:
        if result["source"] not in evidence:
            evidence[result["source"]] = trim_snippet(result["text"])
    return evidence


def _answer_from_retrieved(question, retrieved):
    """منطق توليد الجواب من مقاطع مسترجعة (threshold + استدعاء
    الـ LLM) -- مشترك بين rag_query (البحث العام) وrag_query_scoped
    (شات مقيّد على مرشح واحد من صفحة البروفايل تبعه)."""
    best_score = max((r["score"] for r in retrieved), default=0.0)

    if best_score < CONFIDENCE_THRESHOLD:
        answer = "The CV evidence is weak or not enough to answer confidently."
        return answer, retrieved, [], {}, best_score

    context = ""
    for result in retrieved:
        context += f"""
SOURCE: {result["source"]}
{result["text"]}
"""

    messages = [
        {
            "role": "system",
            "content": """You are a Recruiter CV Assistant.
Answer ONLY using the CV context provided.
Do not use outside knowledge.
Do not invent:
- skills
- experience
- education
- certifications
- projects
If the answer cannot be found in the provided CV context,
say:
Not found in the CV documents.
Mention the candidate names when possible.
Write the answer as plain sentences only -- never as a markdown
table and never using pipe (|) characters or table formatting.
Keep it short and direct.""",
        },
        {
            "role": "user",
            "content": f"""Context:
{context}

Question:
{question}""",
        },
    ]

    response = call_llm(messages)
    answer = response.choices[0].message.content

    sources = get_unique_sources(retrieved)
    evidence = get_evidence_by_source(retrieved)

    return answer, retrieved, sources, evidence, best_score


def rag_query(question, top_k=3):
    matched_sources = match_candidate_sources(question)

    if len(matched_sources) >= 2:
        # سؤال مقارنة بين مرشحين (أو أكتر) مذكورين بالاسم: منجيب مقاطع
        # لكل مرشح لحاله بدل بحث عام واحد على كل الفهرس -- هيك منضمن
        # إن كل مرشح مذكور فعليًا موجود بالسياق يلي رح يوصل للـ LLM،
        # بدل ما نتيجة مرشح واحد تسيطر على أفضل top_k وتخلي التاني غايب.
        retrieved = []
        for source in matched_sources:
            retrieved.extend(
                retrieve_chunks(question, top_k=top_k, allowed_sources=[source])
            )
    elif len(matched_sources) == 1:
        # مرشح واحد مذكور بالاسم: منقيّد البحث على سيرته هو بس، حتى ما
        # يرجع مقطع من مرشح تاني بالغلط (مثلاً قسم EDUCATION لمرشح تاني).
        retrieved = retrieve_chunks(
            question, top_k=top_k, allowed_sources=matched_sources
        )
    else:
        # ما فيه اسم مرشح واضح بالسؤال -- نفس السلوك القديم، بحث عام.
        retrieved = retrieve_chunks(question, top_k=top_k)

    return _answer_from_retrieved(question, retrieved)


def rag_query_scoped(question, allowed_sources, top_k=3):
    """متل rag_query، بس بيقيّد البحث سلفًا على مصادر محددة (cv_file
    وحدة عادة) بدل الاعتماد على استخراج اسم من نص السؤال -- مستخدمة
    من شات صفحة بروفايل المرشح (Part 2)، وين السياق أصلًا معروف
    (نحن جوا صفحة هالمرشح بالذات) وما في داعي نخمّن مين المقصود."""
    retrieved = retrieve_chunks(question, top_k=top_k, allowed_sources=allowed_sources)
    return _answer_from_retrieved(question, retrieved)


def print_answer_with_sources(question, top_k=3):
    answer, retrieved, sources, evidence, best_score = rag_query(question, top_k)
    print("Answer:")
    print(answer)
    print()
    print("Sources:")
    for source in sources:
        print(f"- {source}")
    print(f"\n(best retrieval score: {best_score:.3f})")