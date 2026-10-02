import json
from llm import call_llm
from tools import TOOLS, execute_tool

SYSTEM_PROMPT = """You are a Recruiter Assistant Agent.
You help a recruiter find information about candidates and about the
CV collection itself, and you can prepare (but never directly save)
recruiter workflow actions.

Tools available:
- search_candidate_cvs(query): searches the actual CV documents for
  ONE specific skill, experience, or candidate. If the recruiter's
  question covers several candidates or several topics, call this
  tool multiple times (once per focused topic) and combine all the
  results into one final answer that covers everything asked.
- get_cv_statistics(): reports how many CVs are loaded and their
  filenames. Use this for questions about the collection itself
  (counts, file lists) -- not about candidate skills.
- propose_schedule_interview(candidate_name, interview_date,
  interview_time, notes): prepares a proposed action to schedule an
  interview. This never saves anything by itself.
- propose_status_change(candidate_name, new_status): prepares a
  proposed action to change a candidate's application status. This
  never saves anything by itself.

If a question needs both kinds of information, use both tools
before giving your final answer.

IMPORTANT: propose_schedule_interview and propose_status_change only
prepare a proposal for the recruiter to review -- they NEVER save
anything to the database themselves. Only the recruiter clicking
Approve in the web app actually saves the change. Never claim an
interview was scheduled or a status was changed until the recruiter
approves it -- always say it is a proposed action awaiting approval.

Never invent or guess candidate information that did not come from
a tool result.

If search_candidate_cvs reports that the CV evidence is weak or not
enough to answer confidently, report that to the recruiter honestly
-- do not add a candidate name or any detail that isn't in the tool
result.

You may also see earlier turns of this conversation above the
current question. Use them to understand follow-up questions (e.g.
"tell me more about her" refers to whoever was just discussed), but
still use the tools to verify any CV facts -- never answer a
follow-up from memory of the earlier conversation alone.

When you give your final answer, write it as plain, natural
sentences only. Never format it as a table, and never use pipe (|)
characters or table syntax. Keep it short and direct."""


def create_agent_state(goal):
    return {
        "goal": goal,
        "status": "running",
        "iteration": 0,
        "tools_used": [],
        "steps": [],
        "final_answer": None,
        "proposed_action": None,
    }


def run_agent(goal, conversation_history=None, max_iterations=8):
    """
    conversation_history: optional list of {"role": "user"/"assistant",
    "content": "..."} dicts from earlier turns in this conversation
    (Challenge 4). Pass None or [] for a fresh, standalone question.
    """
    state = create_agent_state(goal)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": goal})

    while state["iteration"] < max_iterations:
        state["iteration"] += 1

        response = call_llm(messages, tools=TOOLS)
        message = response.choices[0].message

        if message.tool_calls:
            # Record the assistant's tool-call request in the conversation
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name

                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result = execute_tool(tool_name, arguments)

                state["tools_used"].append(tool_name)
                state["steps"].append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result
                })

                if result.get("proposed_action"):
                    state["proposed_action"] = result["proposed_action"]

                # Send the tool's result back to the model as an observation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })

        else:
            # No more tool calls -- the model gave its final answer
            state["final_answer"] = message.content
            state["status"] = "completed"
            break
    else:
        state["status"] = "max_iterations_reached"
        state["final_answer"] = (
            state["final_answer"]
            or "Could not reach a final answer within the iteration limit."
        )

    return state


def get_all_sources(state):
    """Unique CV sources used across every search_candidate_cvs step."""
    sources = []
    for step in state["steps"]:
        for source in step["result"].get("sources", []):
            if source not in sources:
                sources.append(source)
    return sources


def get_all_evidence(state):
    """Every unique (source, snippet) pair across all search steps."""
    seen = set()
    evidence = []
    for step in state["steps"]:
        for item in step["result"].get("evidence", []):
            if item["source"] not in seen:
                seen.add(item["source"])
                evidence.append(item)
    return evidence