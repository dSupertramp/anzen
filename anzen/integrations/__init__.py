"""
Anzen integrations — drop-in connectors for popular frameworks.

LLM wrappers (wrap_* → BaseAdapter + *Completions):
  - anzen.integrations.openai       (OpenAI)
  - anzen.integrations.azure_openai (Azure OpenAI)
  - anzen.integrations.anthropic    (Anthropic)
  - anzen.integrations.gemini       (Google Gemini)
  - anzen.integrations.ollama       (Ollama)
  - anzen.integrations.groq         (Groq)
  - anzen.integrations.mistral      (Mistral AI)
  - anzen.integrations.cohere       (Cohere)

Framework callbacks:
  - anzen.integrations.langchain  (LangChain CallbackHandler)
  - anzen.integrations.llamaindex (LlamaIndex observer)
"""

from anzen.integrations._base import extract_text
from anzen.integrations.openai import wrap_openai
from anzen.integrations.azure_openai import wrap_azure_openai
from anzen.integrations.anthropic import wrap_anthropic
from anzen.integrations.gemini import wrap_gemini
from anzen.integrations.ollama import wrap_ollama
from anzen.integrations.groq import wrap_groq
from anzen.integrations.mistral import wrap_mistral
from anzen.integrations.cohere import wrap_cohere

__all__ = [
    "extract_text",
    "wrap_openai",
    "wrap_azure_openai",
    "wrap_anthropic",
    "wrap_gemini",
    "wrap_ollama",
    "wrap_groq",
    "wrap_mistral",
    "wrap_cohere",
]
