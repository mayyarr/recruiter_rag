# 🧑‍💼 Recruiter RAG — AI CV Assistant

An AI assistant for recruiters that answers questions about candidates **directly from their CVs**. Ask *"Who has the most Python experience?"* or *"Compare Sara and Omar for a data role"* and get an answer grounded in the actual CV text, with sources.

Behind the chat, an agent can also schedule interviews and update candidate status, but only after the recruiter approves.

## How it works

```
Recruiter question
      │
   🤖 Agent (Groq LLM) picks the tools it needs
      │
      ├── search_candidate_cvs        → RAG: semantic search over CV chunks
      ├── get_cv_statistics           → overview of the indexed CVs
      ├── propose_schedule_interview  → waits for recruiter approval
      └── propose_status_change       → waits for recruiter approval
      │
   Answer + sources (and "not enough information" when confidence is low)
```

## Features

- **RAG over PDF CVs**: chunking + `all-MiniLM-L6-v2` embeddings + cosine similarity, cached on disk
- **Grounded answers with sources** and a confidence threshold to avoid made-up answers
- **Upload new CVs**: added to the index instantly
- **AI candidate extraction**: name, skills, and experience pulled from a CV into a profile
- **Recruiter dashboard**: candidates, status pipeline, assessments, interviews, notes
- **Human-in-the-loop**: interview scheduling and status changes need approval
- **Voice chat**, **translation**, and **PDF report export**
- **Multiple chat sessions** with login / sign-up

## Tech stack

Python · Flask · SQLite · Groq (`openai/gpt-oss-20b`) · sentence-transformers · scikit-learn · pypdf · ReportLab

## Getting started

```bash
git clone https://github.com/mayyarr/recruiter_rag.git
cd recruiter_rag
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

```powershell
$env:GROQ_API_KEY="your_groq_key"
python app.py
```

Open http://127.0.0.1:5000, sign up, and start asking about the sample CVs in `docs/`.

## Project structure

```
app.py               Flask routes (chat, dashboard, candidates, interviews, notes)
agent.py             agent loop
tools.py             agent tools (CV search, stats, interview/status proposals)
rag.py               PDF chunking, embeddings, retrieval
candidate_extract.py AI extraction of candidate info from a CV
database.py          SQLite schema and queries
translate.py         chat translation
pdf_export.py        PDF report export
docs/                sample CVs
templates/           UI pages
```

## Author

Mayar Husam Mohammad
