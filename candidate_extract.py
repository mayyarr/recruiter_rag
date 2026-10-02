"""
Optional Challenge: استخراج بيانات المرشح الواقعية (اسم + إيميل) من
ملف الـ CV باستخدام الـ LLM -- بدون ما "يخترع" قيمة مش موجودة فعليًا
بالنص، وبدون ما يقرر أي شي متعلق بتقييم المرشح أو حالة التوظيف.
"""

import json

from llm import call_llm
from rag import _extract_pdf_text

MAX_CHARS = 6000  # كفاية لأي سيرة ذاتية عادية، وبيحمي من استهلاك توكنز زايد


def _clean_json_text(raw):
    """بعض الموديلات بترجع الـ JSON ملفوف بـ ```json ... ``` رغم
    التعليمات الصريحة بعدم فعل هيك -- هاد بيشيل الـ backticks لو موجودة."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return raw.strip()


def extract_candidate_info(pdf_path, filename):
    """بتقرا نص الـ PDF وبتطلب من الـ LLM يستخرج بس (اسم + إيميل)
    كمعلومات واقعية موجودة حرفيًا بالنص. لو أي قيمة مش موجودة
    بوضوح، بترجع None إلها بدل ما "تخترعها".

    بترجع dict: {"name": str|None, "email": str|None, "cv_file": filename}
    """
    text = _extract_pdf_text(pdf_path)
    text = text[:MAX_CHARS]

    messages = [
        {
            "role": "system",
            "content": (
                "You extract ONLY factual contact information from a CV. "
                "Return strict JSON with exactly these two keys: name, email. "
                "Use the candidate's full name exactly as written in the CV, "
                "and their email address exactly as written in the CV. "
                "If a value is not clearly present in the text, use null for "
                "that field -- never guess, invent, or infer a value that is "
                "not literally in the text. Do not evaluate the candidate, "
                "do not comment on their skills or fit, and do not include "
                "any key other than name and email. "
                "Return ONLY the JSON object, with no markdown formatting "
                "and no extra commentary."
            ),
        },
        {
            "role": "user",
            "content": f"CV text:\n{text}",
        },
    ]

    response = call_llm(messages)
    raw = response.choices[0].message.content or ""
    raw = _clean_json_text(raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}

    name = (data.get("name") or "").strip() or None
    email = (data.get("email") or "").strip() or None

    return {"name": name, "email": email, "cv_file": filename}
