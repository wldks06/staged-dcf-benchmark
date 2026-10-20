"""Fallback recipes for pulling one input out of tagged filing data.

An input has an ordered list of recipes and the first complete one wins. A recipe
is a signed sum of terms. A term names one concept or several alternatives (first
present wins) and may be optional. The same structure serves SEC tags and DART
account ids: only the lookup function differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Protocol, TypeVar


class HasValue(Protocol):
    value: float


F = TypeVar("F", bound=HasValue)


@dataclass(frozen=True)
class Term:
    concepts: tuple[str, ...]
    sign: int = 1
    optional: bool = False


@dataclass(frozen=True)
class Recipe:
    terms: tuple[Term, ...]


def T(*concepts: str, sign: int = 1, optional: bool = False) -> Term:
    return Term(tuple(concepts), sign, optional)


def R(*terms: Term | str) -> Recipe:
    """A recipe. A bare string is a required single-concept term."""
    return Recipe(tuple(t if isinstance(t, Term) else T(t) for t in terms))


@dataclass
class Part(Generic[F]):
    concept: str
    sign: int
    fact: F


@dataclass
class Match(Generic[F]):
    value: float
    recipe_index: int
    parts: list[Part[F]]


def resolve(recipes: list[Recipe], lookup: Callable[[str], F | None]) -> Match[F] | None:
    """The first recipe whose required terms are all present, or None."""
    for index, recipe in enumerate(recipes):
        parts: list[Part[F]] = []
        complete = True
        for term in recipe.terms:
            found = None
            for concept in term.concepts:
                fact = lookup(concept)
                if fact is not None:
                    found = Part(concept, term.sign, fact)
                    break
            if found is not None:
                parts.append(found)
            elif not term.optional:
                complete = False
                break
        if complete and parts:
            return Match(sum(p.sign * p.fact.value for p in parts), index, parts)
    return None
