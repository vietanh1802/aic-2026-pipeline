"""LLM-based keyword expansion (the "agent").

Given a natural-language query and a classified vocabulary, this asks a GitHub
Models chat model (``gpt-4.1`` by default) to return the vocabulary words that are
synonyms/close in meaning to the query, plus one distinctive "main" keyword. These
expanded keywords are then used by the keyword search in ``main.py``.

Credentials are read from the environment (see ``backend/.env.example``).
"""
import json
import os
from dotenv import load_dotenv
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

token = os.getenv("GITHUB_TOKEN")
if not token:
    raise RuntimeError("GITHUB_TOKEN is not set. Copy backend/.env.example to backend/.env and fill it in.")
endpoint = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference")
model = os.getenv("GITHUB_MODELS_MODEL", "gpt-4.1")

client = ChatCompletionsClient(
    endpoint=endpoint, 
    credential=AzureKeyCredential(token),
)

def generate_keywords(sentence: str, vocab_classified: list[str]):
    """Expand a query into related vocabulary words using the LLM.

    The vocabulary is split into three chunks and sent in three parallel-ish
    requests (to fit the model context); each request is forced to call the
    ``format_output`` tool and return ``{"vocab": [...], "main_keywords": [...]}``.
    The three responses are merged and de-duplicated.

    Args:
        sentence: The user's natural-language query.
        vocab_classified: The list of allowed vocabulary words to match against.

    Returns:
        A dict ``{"vocab": [...], "main_keywords": [...]}`` of matched words.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "format_output",
                "description": "Return the list of vocab from dictionary that are synonyms of words in input sentence",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vocab": {"type": "array", "items": {"type": "string"}},
                        "main_keywords" : {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["vocab", "main_keywords"],
                },
            },
        }
    ]

    system_prompt = (
        """You are a helpful assistant that only matches synonyms, or nearly same with the input,
         like animated = cartoon from the provided dictionary. you can generate synonyms top 3 popular first with each word in sentence
         then check whether if exist in dictionary provided. You also need to choose one unique or special keywords which can clarify between
         among many general one, like roles or name, remember just 1 keywords"""
    )

    user_message = """
    Dictionary: {}
    Sentence: {}
    Task: Check each word in sentence against all words in dictionary.
    If meaning is similar (synonym/close), return that dictionary word.
    Only return words that appear in dictionary, may be not in the sentence
    but near meaning with words in sentence but in dictionary, you can generate
    synonyms top 3 popular first with each word in sentence
    then check whether if exist in dictionary provided, pleasea parse all words the dictionary. You also need to choose
    one unique or special keywords in english in detected words above which can clarify between
    among many general one, like in advance B2 words,..., remember just 1 keywords"""
    
    s = vocab_classified

    response1 = client.complete(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message.format(vocab_classified[:len(s)//3], sentence)}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "format_output"}}
    )

    response2 = client.complete(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message.format(vocab_classified[len(s)//3:2*len(s)//3], sentence)}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "format_output"}}
    )

    response3 = client.complete(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message.format(vocab_classified[2*len(s)//3:], sentence)}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "format_output"}}
    )

    data1 = json.loads(response1.choices[0].message.tool_calls[0].function.arguments)
    data2 = json.loads(response2.choices[0].message.tool_calls[0].function.arguments)
    data3 = json.loads(response3.choices[0].message.tool_calls[0].function.arguments)
    data = {}
    data['vocab'] = list(set(data1['vocab'] + data2['vocab'] + data3['vocab']))
    data['main_keywords'] = list(set(data1['main_keywords'] + data2['main_keywords'] + data3['main_keywords']))
    return data
