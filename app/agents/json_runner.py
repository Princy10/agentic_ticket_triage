import time
import logging
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent

logger = logging.getLogger("json_runner")

T = TypeVar("T", bound=BaseModel)


def _extract_first_json_object(text: str) -> str:
    s = (text or "").strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("Aucun '{' trouvé, pas de JSON.")

    in_str = False
    escape = False
    depth = 0

    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]

    raise ValueError("JSON incomplet: '}' manquant.")


async def run_json_agent(
    agent: Agent,
    prompt: str,
    model: Type[T],
    *,
    temperature: float = 0.2,
    max_tokens: int = 220,
) -> T:
    t0 = time.perf_counter()
    raw = (await agent.run(prompt, model_settings={"temperature": temperature, "max_tokens": max_tokens})).output
    logger.info("agent raw done in %.2fs", time.perf_counter() - t0)

    # 1) parse + validate
    try:
        js = _extract_first_json_object(raw)
        return model.model_validate_json(js)
    except Exception as e1:
        # 2) repair
        repair_prompt = (
            "Ton output précédent n'était pas un JSON valide. "
            "Corrige et renvoie UNIQUEMENT un JSON objet valide, sans texte.\n"
            f"Erreur: {str(e1)}\n"
            f"Output précédent:\n{raw}"
        )

        t1 = time.perf_counter()
        raw2 = (await agent.run(repair_prompt, model_settings={"temperature": 0.0, "max_tokens": max_tokens})).output
        logger.info("agent repair done in %.2fs", time.perf_counter() - t1)

        try:
            js2 = _extract_first_json_object(raw2)
            return model.model_validate_json(js2)
        except ValidationError as ve:
            raise ValueError(f"Validation Pydantic impossible: {ve}")
        except Exception as e2:
            raise ValueError(f"Parsing JSON impossible: {e2}")
