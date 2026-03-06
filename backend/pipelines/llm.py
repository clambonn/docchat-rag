from functools import lru_cache
from utils.config import settings

@lru_cache(maxsize=1)
def get_llm():
    if settings.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=settings.OPENAI_MODEL, openai_api_key=settings.OPENAI_API_KEY,
                          max_tokens=settings.MAX_ANSWER_TOKENS, temperature=0.1)
    elif settings.LLM_PROVIDER == "ollama":
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.1)
    else:
        from langchain_huggingface import HuggingFaceEndpoint
        return HuggingFaceEndpoint(repo_id=settings.HF_MODEL_ID, max_new_tokens=settings.MAX_ANSWER_TOKENS, temperature=0.1)
