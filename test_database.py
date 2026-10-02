from database import (
    init_db,
    create_chat_session,
    get_chat_sessions,
    rename_chat_session,
    delete_chat_session,
    save_message,
    get_chat_history,
    add_recruiter_note,
    get_recruiter_notes,
    update_recruiter_note,
    delete_recruiter_note
)

init_db()

# --- Task 1: chat sessions ---
session_id = create_chat_session("Backend Candidates")
print("Created session id:", session_id)

sessions = get_chat_sessions()
print("All sessions:", sessions)

# --- Task 2: save messages under this session ---
save_message(str(session_id), "user", "Who has Python and FastAPI experience?")
save_message(str(session_id), "assistant", "Sara Haddad and Yousef Darwish have this experience.")

history = get_chat_history(str(session_id))
print("\nHistory for session", session_id, ":")
for msg in history:
    print(" ", msg["role"], ":", msg["content"])

# --- Task 6: rename session ---
rename_chat_session(session_id, "Backend Candidates - Updated")
sessions = get_chat_sessions()
print("\nSessions after rename:", sessions)

# --- Task 5: recruiter notes (add, update, delete) ---
add_recruiter_note("Sara Haddad", "Strong backend profile. Ask about deeper RAG experience.")
notes = get_recruiter_notes("Sara Haddad")
print("\nNotes for Sara Haddad:", notes)

note_id = notes["notes"][0]["id"]
update_recruiter_note(note_id, "Strong backend profile. Confirmed RAG experience in interview.")
notes_after_update = get_recruiter_notes("Sara Haddad")
print("Notes after update:", notes_after_update)

delete_recruiter_note(note_id)
notes_after_delete = get_recruiter_notes("Sara Haddad")
print("Notes after delete:", notes_after_delete)

# --- Task 6: delete session (and confirm its messages are gone too) ---
delete_chat_session(session_id)
sessions_after_delete = get_chat_sessions()
print("\nSessions after delete:", sessions_after_delete)

history_after_delete = get_chat_history(str(session_id))
print("History after session delete (should be empty):", history_after_delete)