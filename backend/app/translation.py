from __future__ import annotations

import json
import os
import time
import urllib.request


# Every run records the policy-specific translator_id_for_policy() value, so a
# past run's translations stay attributable even after the default changes.
DEFAULT_TRANSLATION_POLICY = "visual_faithful"

_GEMINI_MODEL = "gemini-3.5-flash-lite"
_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"


TRANSLATION_POLICIES = {
    "visual_faithful" : {
        "label" : "Visual faithful",
        "description" : "Preserve every explicit visual detail while removing video-narration boilerplate.",
        "instructions" : (
            "Translate the following Vietnamese query into English for visual video retrieval.\n\n"
            "Requirements:\n"
            "- Return only the English translation.\n"
            "- Preserve every explicit visual detail precisely, including objects, people, actions, "
            "counts, colors, clothing, positions, text, weather, camera viewpoint, and temporal order.\n"
            "- Remove video-narration boilerplate such as 'the video begins with', 'the clip starts with', "
            "'the footage shows', 'the scene then changes to', and 'the video ends with'.\n"
            "- Express the visual content directly instead of describing the existence or structure of the video.\n"
            "- Preserve the sequence through sentence order rather than unnecessary phrases such as "
            "'the video then shows'.\n"
            "- Do not summarize, generalize, infer, explain, or add information.\n"
            "- Do not replace a specific detail with a broader description.\n"
            "- Do not guess a more specific object or technical term when the Vietnamese is ambiguous."
        ),
    },
    "scene_clauses" : {
        "label" : "Scene clauses",
        "description" : "Rewrite distinct scenes and actions as short chronological visual clauses.",
        "instructions" : (
            "Translate the following Vietnamese query into English and rewrite it as direct visual scene descriptions.\n\n"
            "Requirements:\n"
            "- Return only the English result.\n"
            "- Preserve all explicitly stated visual details exactly.\n"
            "- Represent each distinct scene, action, or moment as a short standalone clause or sentence.\n"
            "- Keep the clauses in the same chronological order as the Vietnamese query.\n"
            "- Do not use meta-video phrases such as 'the video begins with', 'the clip starts with', "
            "'the footage shows', 'then the scene changes', 'followed by a shot of', or 'the video ends with'.\n"
            "- Preserve exact counts, colors, clothing, objects, actions, spatial relationships, "
            "weather, camera viewpoint, and visible text.\n"
            "- Do not summarize or omit secondary details.\n"
            "- Do not infer or add information.\n"
            "- If the input contains a question, do not answer it."
        ),
    },
    "retrieval_compact" : {
        "label" : "Retrieval compact",
        "description" : "Produce a dense visual-search description with minimal narrative wording.",
        "instructions" : (
            "Translate the following Vietnamese query into a compact English visual-search description "
            "for image-video retrieval.\n\n"
            "Requirements:\n"
            "- Return only the English search description.\n"
            "- Prioritize concrete visible nouns, actions, attributes, counts, colors, clothing, "
            "locations, spatial relationships, camera viewpoints, weather, and visible text.\n"
            "- Preserve every discriminative visual detail from the Vietnamese query.\n"
            "- Remove narrative and meta-video language such as 'the video begins with', "
            "'the clip starts with', 'the footage shows', 'the scene changes to', and 'the video ends with'.\n"
            "- Remove conversational filler and unnecessary wording that does not describe visible content.\n"
            "- Use concise clauses separated by semicolons when appropriate.\n"
            "- Preserve chronological order.\n"
            "- Do not summarize away specific details.\n"
            "- Do not infer, explain, or add information.\n"
            "- If the input is a question, do not answer it; preserve the visual evidence needed to answer it."
        ),
    },
    "salience_first" : {
        "label" : "Salience first",
        "description" : "Move distinctive explicit visual cues earlier while preserving all details.",
        "instructions" : (
            "Translate the following Vietnamese query into English for visual retrieval, emphasizing "
            "the most distinctive explicitly stated visual evidence.\n\n"
            "Requirements:\n"
            "- Return only the English result.\n"
            "- Preserve all explicitly stated information.\n"
            "- Put highly discriminative visual details first when possible: unusual objects, exact counts, "
            "specific colors, clothing, distinctive actions, spatial relationships, visible text, and camera viewpoint.\n"
            "- Include the remaining visual details afterward.\n"
            "- Remove meta-video phrases such as 'the video begins with', 'the clip starts with', "
            "'the footage shows', 'the scene changes to', and 'the video ends with'.\n"
            "- Use direct visual descriptions rather than narration about the video.\n"
            "- Do not invent or infer which detail is present if it is not explicitly stated.\n"
            "- Do not remove details merely because they seem less important.\n"
            "- If the input contains a question, do not answer it."
        ),
    },
}


def normalize_translation_policy(policy : str | None) -> str :
    selected = (policy or DEFAULT_TRANSLATION_POLICY).strip()
    if (selected not in TRANSLATION_POLICIES) :
        raise ValueError(f"Unknown translation policy: {selected}")
    return selected


def translator_id_for_policy(policy : str | None) -> str :
    selected = normalize_translation_policy(policy)
    return f"gemini_3_5_flash_lite_vi_en_{selected}_v1"


def translation_policy_options() -> list[dict[str, str]] :
    return [
        {
            "id" : policy_id,
            "label" : str(policy["label"]),
            "description" : str(policy["description"]),
        }
        for policy_id, policy in TRANSLATION_POLICIES.items()
    ]


def _translation_prompt(text : str, policy : str) -> str :
    instructions = str(TRANSLATION_POLICIES[policy]["instructions"])
    return f"{instructions}\n\nVietnamese:\n{text}"


def translate_vi_to_en(
    text : str,
    timeout_s : float = 10.0,
    *,
    policy : str | None = None,
) -> tuple[str, float] :
    query = text.strip()
    if (not query) :
        raise ValueError("Translation text must not be empty")

    api_key = os.getenv("GEMINI_API_KEY")
    if (not api_key) :
        raise RuntimeError("GEMINI_API_KEY is not configured")

    selected_policy = normalize_translation_policy(policy)
    payload = {
        "contents" : [
            {
                "parts" : [
                    {"text" : _translation_prompt(query, selected_policy)}
                ]
            }
        ],
        "generationConfig" : {
            "temperature" : 0.0,
        },
    }
    request = urllib.request.Request(
        _GEMINI_URL,
        data = json.dumps(payload, ensure_ascii = False).encode("utf-8"),
        headers = {
            "Content-Type" : "application/json",
            "x-goog-api-key" : api_key,
        },
        method = "POST",
    )

    started = time.monotonic()
    with urllib.request.urlopen(request, timeout = timeout_s) as response :
        data = json.loads(response.read().decode("utf-8"))

    candidates = data.get("candidates") if isinstance(data, dict) else None
    if (not candidates) :
        raise RuntimeError("Gemini returned no translation")

    candidate = candidates[0]
    if (not isinstance(candidate, dict)) :
        raise RuntimeError("Gemini returned no translation")

    content = candidate.get("content")
    if (not isinstance(content, dict)) :
        raise RuntimeError("Gemini returned no translation")

    parts = content.get("parts")
    if (not isinstance(parts, list) or not parts) :
        raise RuntimeError("Gemini returned no translation")

    translated = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict)
    ).strip()

    if (not translated) :
        raise RuntimeError("Gemini returned an empty translation")

    elapsed_ms = (time.monotonic() - started) * 1000.0
    return translated, elapsed_ms
