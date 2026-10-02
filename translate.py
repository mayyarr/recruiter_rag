import json
from llm import call_llm


def translate_texts(texts, target_lang="ar"):
    """
    Translates a list of strings using the same LLM used by the agent
    (see llm.py / call_llm). Returns a list of translated strings, in
    the same order and with the same length as the input.

    If anything goes wrong (bad JSON from the model, API error, etc.)
    the original texts are returned unchanged so the UI never breaks
    -- it just shows untranslated text instead of crashing.
    """
    if not texts:
        return []

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    language_name = "Arabic" if target_lang == "ar" else "English"

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a translation engine. Translate each numbered "
                f"line below into {language_name}. Keep candidate names, "
                f"filenames, and numbers unchanged. Preserve the meaning "
                f"exactly -- do not summarize or add anything.\n"
                f"Return ONLY a JSON array of strings, in the same order "
                f"as the input lines, with no markdown fences, no "
                f"numbering inside the strings, and no extra commentary."
            ),
        },
        {"role": "user", "content": numbered},
    ]

    try:
        response = call_llm(messages)
        content = response.choices[0].message.content.strip()

        # Some models wrap JSON in markdown code fences -- strip them
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()

        translations = json.loads(content)

        if isinstance(translations, list) and len(translations) == len(texts):
            return [str(t) for t in translations]

        print("Translation warning: unexpected shape, falling back to originals")
    except Exception as e:
        print("Translation error:", e)

    return texts