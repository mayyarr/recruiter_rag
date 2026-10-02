import os
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-20b"

def call_llm(messages, tools=None):
    if tools:
        return client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

    return client.chat.completions.create(
        model=MODEL,
        messages=messages
    )