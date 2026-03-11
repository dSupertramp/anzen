"""
Anzen integrations — drop-in connectors for popular frameworks.
"""

from anzen.integrations._base import extract_text
from anzen.integrations.anthropic import wrap_anthropic
from anzen.integrations.azure_openai import wrap_azure_openai
from anzen.integrations.cohere import wrap_cohere
from anzen.integrations.gemini import wrap_gemini
from anzen.integrations.groq import wrap_groq
from anzen.integrations.mistral import wrap_mistral
from anzen.integrations.ollama import wrap_ollama
from anzen.integrations.openai import wrap_openai

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
