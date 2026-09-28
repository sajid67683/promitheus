"""Server-side answer checking. Correct answers are never sent to the browser before answering."""
import random
import re
from dataclasses import dataclass

CHOICE_TYPES = {"multiple_choice", "true_false"}
TEXT_TYPES = {"fill_blank", "short_answer"}
AI_TYPES = {"explain"}
ALL_TYPES = CHOICE_TYPES | TEXT_TYPES | AI_TYPES | {"rearrange"}

_EDGE_PUNCTUATION = " \t\n.,;:!?\"'`()[]{}"
_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+")


def normalize(value) -> str:
    """Case-, whitespace- and edge-punctuation-insensitive form of an answer."""
    text = re.sub(r"\s+", " ", str(value)).strip(_EDGE_PUNCTUATION)
    return text.casefold()


def _loose(value) -> str:
    """normalize() plus: no leading article, hyphens treated as spaces."""
    text = normalize(value).replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return _LEADING_ARTICLE.sub("", text)


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein distance (adjacent swaps count as one), stopping early past `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _typo_allowance(length: int) -> int:
    if length <= 3:
        return 0  # short words: "ATP" vs "ADP" is a different answer, not a typo
    if length <= 7:
        return 1
    if length <= 14:
        return 2
    return 3


@dataclass
class TextMatch:
    correct: bool
    typo: bool = False


def match_text(answer: str, accepted: list[str]) -> TextMatch:
    given = _loose(answer)
    if not given:
        return TextMatch(False)
    candidates = [_loose(a) for a in accepted if _loose(a)]
    if given in candidates:
        return TextMatch(True)
    for candidate in candidates:
        # Numbers must match exactly: "1945" vs "1946" is wrong, not a typo.
        if any(ch.isdigit() for ch in candidate):
            continue
        if _edit_distance(given, candidate, _typo_allowance(len(candidate))) <= _typo_allowance(len(candidate)):
            return TextMatch(True, typo=True)
    return TextMatch(False)


def accepted_answers(question) -> list[str]:
    content = question.content or {}
    answers = [content.get("answer", "")]
    answers += [a for a in content.get("alternatives", []) if isinstance(a, str)]
    return [a for a in answers if str(a).strip()]


def public_question(question) -> dict:
    """What the browser is allowed to see before answering: prompt and choices, never the answer."""
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


def grade_locally(question, answer) -> TextMatch:
    """Grades every type except "explain", which needs the AI."""
    content = question.content or {}
    correct = content.get("answer")
    qtype = question.question_type

    if qtype == "rearrange":
        if not isinstance(answer, list) or not isinstance(correct, list):
            return TextMatch(False)
        return TextMatch([normalize(a) for a in answer] == [normalize(c) for c in correct])

    if not isinstance(answer, str) or not normalize(answer):
        return TextMatch(False)
    if qtype in CHOICE_TYPES:
        return TextMatch(normalize(answer) == normalize(correct))
    return match_text(answer, accepted_answers(question))
