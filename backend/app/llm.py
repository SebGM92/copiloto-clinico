"""Cliente del modelo de lenguaje."""
from app import config


def generate(prompt: str, context: list[str]) -> str:
    # TODO: conectar con el proveedor de LLM (config.ANTHROPIC_MODEL)
    raise NotImplementedError
