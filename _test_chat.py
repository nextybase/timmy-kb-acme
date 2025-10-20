from dotenv import load_dotenv

load_dotenv()
from openai import OpenAI

client = OpenAI()
models = [
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-mini",
    "gpt-4o-2024-08-06",
    "gpt-4.1-mini-2025-04-14",
]
for model_id in models:
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Ciao"}],
            max_tokens=5,
        )
        print(model_id, "OK")
    except Exception as exc:
        print(model_id, "->", exc)
