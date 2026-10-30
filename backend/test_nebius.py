import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["NEBIUS_API_KEY"],
    base_url=os.environ["NEBIUS_BASE_URL"]
)

response = client.chat.completions.create(
    model=os.environ["NEBIUS_MODEL"],
    messages=[
        {
            "role": "system",
            "content": "You are RASEGAN AI, a strict university examination evaluator. Award marks fairly. Explain mistakes and provide an improved answer."
        },
        {
            "role": "user",
            "content": """
            Question (10 marks):
            Explain the difference between supervised and unsupervised learning.

            Student answer:
            Supervised learning uses labelled data to train a model.
            Unsupervised learning uses unlabelled data to find patterns.
            """
        }
    ],
    max_tokens=700,
    temperature=0.2
)

print(response.choices[0].message.content)