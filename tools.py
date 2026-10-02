import os
from rag import rag_query
from database import find_candidate_by_name, APPLICATION_STATUSES

DOCS_FOLDER = "docs"


def search_candidate_cvs(query):
    """
    Tool: searches the candidate CVs using the RAG system.

    Use ONE focused query per call -- if a recruiter question covers
    several candidates or topics, call this tool once per topic
    (Challenge 2: Multi-Search) instead of one broad query.

    Includes best_score so low-confidence answers can be detected
    (Challenge 1: Low-Confidence Retrieval).
    """
    try:
        answer, retrieved, sources, evidence, best_score = rag_query(query)
        return {
            "success": True,
            "answer": answer,
            "sources": sources,
            "evidence": [
                {"source": source, "snippet": evidence.get(source, "")}
                for source in sources
            ],
            "best_score": round(best_score, 3)
        }
    except Exception as e:
        return {
            "success": False,
            "answer": f"Error while searching CVs: {str(e)}",
            "sources": [],
            "evidence": [],
            "best_score": 0.0
        }


def get_cv_statistics():
    """
    Tool (Challenge 3): a plain Python tool, no RAG/embeddings
    involved. Reports how many CVs are currently loaded and their
    filenames -- for questions about the collection itself, not
    about candidate skills.
    """
    try:
        filenames = sorted(
            f for f in os.listdir(DOCS_FOLDER) if f.endswith(".pdf")
        )
        return {
            "success": True,
            "total_cvs": len(filenames),
            "filenames": filenames
        }
    except Exception as e:
        return {
            "success": False,
            "total_cvs": 0,
            "filenames": [],
            "error": str(e)
        }


def propose_schedule_interview(candidate_name, interview_date, interview_time, notes=""):
    """
    Tool (Part 3): بتحضّر اقتراح جدولة مقابلة -- بدون ما تلمس
    قاعدة البيانات أبدًا. الحفظ الفعلي بيصير بس لما الريكروتر يدوس
    Approve بالواجهة على الـ proposed_action يلي بترجعه هاي الدالة.
    """
    candidate = find_candidate_by_name(candidate_name)
    if not candidate:
        return {
            "success": False,
            "answer": f"I couldn't find a candidate named '{candidate_name}' on the dashboard.",
            "proposed_action": None,
        }

    return {
        "success": True,
        "answer": (
            f"I've prepared a proposed action to schedule an interview for "
            f"{candidate['name']} on {interview_date} at {interview_time}. "
            f"Please review and approve it below before anything is saved."
        ),
        "proposed_action": {
            "type": "schedule_interview",
            "candidate_id": candidate["id"],
            "candidate_name": candidate["name"],
            "interview_date": interview_date,
            "interview_time": interview_time,
            "notes": notes or "",
        },
    }


def propose_status_change(candidate_name, new_status):
    """
    Tool (Part 3): بتحضّر اقتراح تغيير حالة طلب توظيف -- بدون ما
    تلمس قاعدة البيانات. نفس نمط propose_schedule_interview.
    """
    candidate = find_candidate_by_name(candidate_name)
    if not candidate:
        return {
            "success": False,
            "answer": f"I couldn't find a candidate named '{candidate_name}' on the dashboard.",
            "proposed_action": None,
        }

    if new_status not in APPLICATION_STATUSES:
        return {
            "success": False,
            "answer": (
                f"'{new_status}' isn't a valid status. Use one of: "
                f"{', '.join(APPLICATION_STATUSES)}."
            ),
            "proposed_action": None,
        }

    return {
        "success": True,
        "answer": (
            f"I've prepared a proposed action to change {candidate['name']}'s "
            f"application status to {new_status}. Please review and approve "
            f"it below before anything is saved."
        ),
        "proposed_action": {
            "type": "status_change",
            "candidate_id": candidate["id"],
            "candidate_name": candidate["name"],
            "new_status": new_status,
        },
    }


# Tool definitions in the JSON schema format expected by Groq's
# OpenAI-compatible tool calling (matches how llm.py passes `tools=`
# to client.chat.completions.create).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_candidate_cvs",
            "description": (
                "Search the candidate CV documents to answer a recruiter "
                "question about ONE specific skill, experience, "
                "certification, or candidate. If the recruiter's question "
                "covers several topics or candidates, call this tool once "
                "per focused topic instead of one broad query, then "
                "combine the results yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A focused question about one candidate or one skill/topic."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cv_statistics",
            "description": (
                "Get statistics about the CV collection itself: how many "
                "CVs are currently loaded and their filenames. Use this "
                "for questions about the collection (counts, file lists) "
                "-- not for questions about candidate skills or experience."
            ),
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_schedule_interview",
            "description": (
                "Propose scheduling an interview for a candidate on the "
                "Recruiter Dashboard. This does NOT save anything to the "
                "database -- it only prepares a proposed action that the "
                "recruiter must review and approve in the web app. Use "
                "this whenever the recruiter asks to schedule, book, or "
                "set up an interview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_name": {
                        "type": "string",
                        "description": "The candidate's name as mentioned by the recruiter."
                    },
                    "interview_date": {
                        "type": "string",
                        "description": "Interview date, formatted YYYY-MM-DD."
                    },
                    "interview_time": {
                        "type": "string",
                        "description": "Interview time, e.g. '11:00 AM'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional extra notes about the interview."
                    }
                },
                "required": ["candidate_name", "interview_date", "interview_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_status_change",
            "description": (
                "Propose changing a candidate's application status "
                "(Applied, Screening, Interview, or Hold) on the "
                "Recruiter Dashboard. This does NOT save anything to the "
                "database -- it only prepares a proposed action that the "
                "recruiter must review and approve in the web app."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_name": {
                        "type": "string",
                        "description": "The candidate's name as mentioned by the recruiter."
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["Applied", "Screening", "Interview", "Hold"]
                    }
                },
                "required": ["candidate_name", "new_status"]
            }
        }
    }
]


def execute_tool(tool_name, arguments):
    """
    Connects a tool name (as requested by the model) to the actual
    Python function that implements it.
    """
    if tool_name == "search_candidate_cvs":
        query = arguments.get("query", "")
        return search_candidate_cvs(query)

    if tool_name == "get_cv_statistics":
        return get_cv_statistics()

    if tool_name == "propose_schedule_interview":
        return propose_schedule_interview(
            arguments.get("candidate_name", ""),
            arguments.get("interview_date", ""),
            arguments.get("interview_time", ""),
            arguments.get("notes", ""),
        )

    if tool_name == "propose_status_change":
        return propose_status_change(
            arguments.get("candidate_name", ""),
            arguments.get("new_status", ""),
        )

    return {
        "success": False,
        "answer": f"Unknown tool: {tool_name}",
        "sources": []
    }