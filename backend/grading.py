"""Server-side answer checking. Correct answers are never sent to the browser."""
import random
import re

CHOICE_TYPES = {"multiple_choice", "true_false"}
TEXT_TYPES = {"fill_blank", "short_answer"}
AI_TYPES = {"explain"}
ALL_TYPES = CHOICE_TYPES | TEXT_TYPES | AI_TYPES | {"rearrange"}

_EDGE_PUNCTUATION = " \t\n.,;:!?\"'`()[]{}"


def normalize(value) -> str:
    """Case-, whitespace- and edge-punctuation-insensitive form of an answer."""
    text = re.sub(r"\s+", " ", str(value)).strip(_EDGE_PUNCTUATION)
    return text.casefold()


def public_question(question) -> dict:
    """What the browser is allowed to see: prompt and choices, never the answer."""
    content = question.content or {}
    data = {"prompt": content.get("prompt", "")}
    if question.question_type in CHOICE_TYPES:
        data["options"] = list(content.get("options", []))
    elif question.question_type == "rearrange":
        chunks = list(content.get("chunks", []))
        random.shuffle(chunks)
        data["chunks"] = chunks
    return {"question_id": question.id, "type": question.question_type, "data": data}


def display_answer(question) -> str:
    answer = (question.content or {}).get("answer", "")
    if isinstance(answer, list):
        return " ".join(str(part) for part in answer)
    return str(answer)


def grade_locally(question, answer) -> bool:
    """Grades every type except "explain", which needs the AI."""
    content = question.content or {}
    correct = content.get("answer")
    qtype = question.question_type

    if qtype == "rearrange":
        if not isinstance(answer, list) or not isinstance(correct, list):
            return False
        return [normalize(a) for a in answer] == [normalize(c) for c in correct]

    if not isinstance(answer, str):
        return False
    return normalize(answer) != "" and normalize(answer) == normalize(correct)
