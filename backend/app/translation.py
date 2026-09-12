from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request


# Every run records the policy-specific translator_id_for_policy() value, so a
# past run's translations stay attributable even after the default changes.
DEFAULT_TRANSLATION_POLICY = "literal_v1"

_GEMINI_MODEL = "gemini-3.5-flash-lite"
_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"

# Ai thật sự dịch. Mọi policy cũ đều là Gemini nên thiếu khoá "provider" nghĩa
# là Gemini — không phải sửa lại sáu entry chỉ để khai thêm một giá trị mặc định.
PROVIDER_GEMINI = "gemini"
PROVIDER_GOOGLE_GTX = "google_gtx"

# Đúng endpoint mà nút Translate ở tab Search gọi (QueryInput/index.tsx). Đây là
# endpoint nội bộ của trang translate.google.com: không cần key, nhưng cũng
# không có hợp đồng nào — Google chặn hay đổi định dạng lúc nào cũng được.
_GOOGLE_GTX_URL = "https://translate.googleapis.com/translate_a/single"

# Gọi từ EC2 bằng User-Agent mặc định của urllib ("Python-urllib/3.x") rất dễ
# ăn 403. Giả trình duyệt để đi cùng đường với nút Translate trên web.
_GOOGLE_GTX_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


TRANSLATION_POLICIES = {
    "literal_v1" : {
        "label" : "Literal (baseline)",
        "description" : "Plain literal translation, no restructuring.",
        "instructions" : (
            "Translate the following Vietnamese text into English.\n"
            "Preserve the original meaning precisely.\n"
            "Do not explain or add information."
        ),
    },
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
    "literal_visual_v2" : {
        "label" : "Literal visual v2",
        "description" : "Literal translation that also protects specific visual wording from being generalized.",
        "instructions" : (
            "Translate the following Vietnamese query into English for visual video retrieval.\n\n"
            "Requirements:\n"
            "- Return only the English translation.\n"
            "- Preserve sentence order exactly as written.\n"
            "- Preserve subject-action-object relationships exactly as stated.\n"
            "- Preserve every explicit count, color, object, clothing item, spatial relation, "
            "temporal relation, camera/viewpoint detail, and visible text.\n"
            "- Preserve temporal connectors such as 'then', 'after that', 'next', 'finally' when "
            "they appear in the source -- do not remove them, they can mark distinct sub-scenes.\n"
            "- Do not summarize, compress, or merge separate observations into one broader concept "
            "(e.g. do not turn 'two students acting as presenters' into 'two student MCs').\n"
            "- Do not introduce more specific or technical vocabulary than the source uses "
            "(e.g. do not turn 'drum set' into 'acoustic drum kit').\n"
            "- Do not reorder details for salience or emphasis.\n"
            "- Do not infer, explain, or add information not stated.\n"
            "- Remove only truly empty wrapper phrases that describe the existence of the video "
            "rather than its visible content, such as 'đoạn video cho thấy', 'có thể thấy trong "
            "cảnh', 'cảnh quay ghi lại'. Do not remove anything else.\n"
            "- If the input contains a question, do not answer it, but preserve the full visual "
            "evidence description needed to answer it."
        ),
    },
    # Không phải một cách viết prompt — là một NGƯỜI DỊCH khác hẳn. Có mặt ở đây
    # vì suốt cuộc thi cả nhóm bấm nút Translate ở tab Search, tức là dịch bằng
    # Google chứ không phải Gemini. Thiếu lựa chọn này thì benchmark đang chấm
    # một hệ thống không ai dùng, và không tách được "ensemble tìm giỏi tới đâu"
    # khỏi "Gemini dịch khéo hơn Google tới đâu".
    "google_gtx_v1" : {
        "label" : "Google Translate (contest parity)",
        "description" : "Exactly what the Search tab's Translate button does — free gtx endpoint, no prompt.",
        "provider" : PROVIDER_GOOGLE_GTX,
        "translator_id" : "google_gtx_vi_en_v1",
    },
}


def normalize_translation_policy(policy : str | None) -> str :
    selected = (policy or DEFAULT_TRANSLATION_POLICY).strip()
    if (selected not in TRANSLATION_POLICIES) :
        raise ValueError(f"Unknown translation policy: {selected}")
    return selected


def provider_of_policy(policy : str | None) -> str :
    selected = normalize_translation_policy(policy)
    return str(TRANSLATION_POLICIES[selected].get("provider") or PROVIDER_GEMINI)


def translator_id_for_policy(policy : str | None) -> str :
    selected = normalize_translation_policy(policy)
    # Giữ nguyên chuỗi suy ra từ tên policy cho các policy Gemini: id này đã nằm
    # trong DB của những lần chạy trước, đổi là các run cũ không còn so được với
    # run mới. Người dịch không phải Gemini thì khai thẳng id của mình.
    explicit_id = TRANSLATION_POLICIES[selected].get("translator_id")
    if (explicit_id) :
        return str(explicit_id)
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


def _translate_google_gtx(query : str, timeout_s : float) -> str :
    """Cùng endpoint, cùng tham số với nút Translate ở tab Search, để con số
    benchmark nói đúng về thứ cả nhóm đã dùng trong lúc thi."""
    params = urllib.parse.urlencode({
        "client" : "gtx",
        "sl"     : "auto",
        "tl"     : "en",
        "dt"     : "t",
        "q"      : query,
    })
    request = urllib.request.Request(
        f"{_GOOGLE_GTX_URL}?{params}",
        headers = {"User-Agent" : _GOOGLE_GTX_USER_AGENT},
        method = "GET",
    )
    with urllib.request.urlopen(request, timeout = timeout_s) as response :
        data = json.loads(response.read().decode("utf-8"))

    # Trả về [[ ["câu đã dịch", "câu gốc", ...], ... ], ...] — câu dài bị cắt
    # thành nhiều đoạn, phải nối lại đúng như frontend đang làm.
    segments = data[0] if (isinstance(data, list) and data) else None
    if (not isinstance(segments, list) or not segments) :
        raise RuntimeError("Google Translate returned no translation")

    translated = "".join(
        str(segment[0] or "")
        for segment in segments
        if (isinstance(segment, list) and segment)
    ).strip()

    if (not translated) :
        raise RuntimeError("Google Translate returned an empty translation")
    return translated


def translate_vi_to_en(
    text : str,
    timeout_s : float = 10.0,
    *,
    policy : str | None = None,
) -> tuple[str, float] :
    query = text.strip()
    if (not query) :
        raise ValueError("Translation text must not be empty")

    # Tuyến Google không có key, nên phải rẽ TRƯỚC chỗ kiểm GEMINI_API_KEY —
    # nếu không thì chọn Google mà thiếu key Gemini vẫn hỏng cả lần chạy.
    if (provider_of_policy(policy) == PROVIDER_GOOGLE_GTX) :
        started = time.monotonic()
        translated = _translate_google_gtx(query, timeout_s)
        return translated, (time.monotonic() - started) * 1000.0

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
