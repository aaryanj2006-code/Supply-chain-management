import os, json, re


def get_llm():
    """Returns a LangChain chat model for whichever provider key is set, else None."""
    try:
        model = os.getenv("LLM_MODEL")
        if os.getenv("GROQ_API_KEY"):
            from langchain_groq import ChatGroq
            return ChatGroq(model=model or "llama-3.3-70b-versatile", temperature=0.2)
        if os.getenv("OPENAI_API_KEY"):
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model or "gpt-4o-mini", temperature=0.2)
        if os.getenv("GOOGLE_API_KEY"):
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model or "gemini-2.0-flash", temperature=0.2)
    except Exception:
        return None
    return None


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}
