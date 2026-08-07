"""Offline TF-IDF text similarity for Chinese and English action-card text.

The implementation intentionally uses only the Python standard library so the
course project can run without a network connection or a model download.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


_WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize English words and Chinese character bigrams deterministically."""

    if not isinstance(text, str):
        raise TypeError("文本必须是字符串")
    tokens: list[str] = []
    for fragment in _WORD_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", fragment):
            tokens.extend(fragment[index : index + 2] for index in range(len(fragment) - 1))
            if len(fragment) == 1:
                tokens.append(fragment)
        else:
            tokens.append(fragment)
    return tokens


def _tfidf_vectors(texts: Sequence[str]) -> list[dict[str, float]]:
    token_lists = [tokenize(text) for text in texts]
    document_frequency: Counter[str] = Counter()
    for tokens in token_lists:
        document_frequency.update(set(tokens))

    document_count = len(token_lists)
    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        if not tokens:
            vectors.append({})
            continue
        counts = Counter(tokens)
        length = len(tokens)
        vectors.append(
            {
                token: (count / length)
                * (math.log((1 + document_count) / (1 + document_frequency[token])) + 1)
                for token, count in counts.items()
            }
        )
    return vectors


def _cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    if not denominator:
        return 0.0
    numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
    return numerator / denominator


def text_similarity(left: str, right: str, *, corpus: Sequence[str] = ()) -> float:
    """Return TF-IDF cosine similarity on a human-readable 0--100 scale."""

    if not isinstance(corpus, Sequence) or isinstance(corpus, (str, bytes)):
        raise TypeError("语料库必须是文本序列")
    if any(not isinstance(text, str) for text in corpus):
        raise TypeError("语料库只能包含字符串")
    if not left.strip() or not right.strip():
        return 0.0
    left_vector, right_vector, *_ = _tfidf_vectors([left, right, *corpus])
    return round(max(0.0, min(100.0, _cosine(left_vector, right_vector) * 100)), 1)


def bidirectional_text_scores(
    user_a: Mapping[str, Any], user_b: Mapping[str, Any], *, corpus: Sequence[str] = ()
) -> dict[str, float]:
    """Score A's expectation against B's description and vice versa."""

    try:
        a_expectation = user_a["partner_expectation"]
        a_description = user_a["self_description"]
        b_expectation = user_b["partner_expectation"]
        b_description = user_b["self_description"]
    except KeyError as error:
        raise ValueError(f"用户画像缺少文本字段：{error.args[0]}") from error
    return {
        "a_to_b": text_similarity(str(a_expectation), str(b_description), corpus=corpus),
        "b_to_a": text_similarity(str(b_expectation), str(a_description), corpus=corpus),
    }


__all__ = ["bidirectional_text_scores", "text_similarity", "tokenize"]
