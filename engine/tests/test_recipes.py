"""data/recipes.py: ordered fallback recipes over tagged facts."""

from __future__ import annotations

from dataclasses import dataclass

from dcfbench.data.recipes import Match, Part, R, Recipe, T, Term, resolve


@dataclass
class Fact:
    value: float


def lookup_in(values: dict[str, float]):
    """A lookup over a plain dict that also records which concepts were asked for."""
    asked: list[str] = []

    def lookup(concept: str):
        asked.append(concept)
        return Fact(values[concept]) if concept in values else None

    lookup.asked = asked
    return lookup


# --- building recipes ---------------------------------------------------------


def test_r_accepts_bare_strings_and_term_objects():
    recipe = R("Revenues", T("InterestExpense", sign=-1), T("A", "B", optional=True))
    assert recipe == Recipe((
        Term(("Revenues",), 1, False),
        Term(("InterestExpense",), -1, False),
        Term(("A", "B"), 1, True),
    ))


def test_t_defaults_to_a_required_positive_term():
    assert T("Revenues") == Term(("Revenues",), sign=1, optional=False)


# --- which recipe wins ----------------------------------------------------------


def test_first_complete_recipe_wins():
    recipes = [R("Revenues"), R("SalesRevenueNet")]
    match = resolve(recipes, lookup_in({"Revenues": 100.0, "SalesRevenueNet": 90.0}))
    assert match.value == 100.0
    assert match.recipe_index == 0
    assert [p.concept for p in match.parts] == ["Revenues"]


def test_recipe_index_reports_the_fallback_that_matched():
    recipes = [R("Revenues"), R("SalesRevenueNet"), R("RevenueOther")]
    assert resolve(recipes, lookup_in({"SalesRevenueNet": 90.0})).recipe_index == 1
    assert resolve(recipes, lookup_in({"RevenueOther": 80.0})).recipe_index == 2


def test_no_recipe_complete_gives_none():
    assert resolve([R("Revenues"), R("SalesRevenueNet")], lookup_in({"Other": 1.0})) is None
    assert resolve([], lookup_in({"Revenues": 1.0})) is None


def test_a_recipe_needs_all_of_its_required_terms():
    recipes = [R("LongTermDebtNoncurrent", "LongTermDebtCurrent"), R("DebtCurrent")]
    partial = {"LongTermDebtNoncurrent": 70.0, "DebtCurrent": 5.0}
    match = resolve(recipes, lookup_in(partial))
    # Half of the first recipe is not enough, and none of it leaks into the answer.
    assert match.recipe_index == 1
    assert match.value == 5.0
    assert [p.concept for p in match.parts] == ["DebtCurrent"]


def test_terms_are_summed():
    recipes = [R("LongTermDebtNoncurrent", "LongTermDebtCurrent")]
    facts = {"LongTermDebtNoncurrent": 70.0, "LongTermDebtCurrent": 30.0}
    match = resolve(recipes, lookup_in(facts))
    assert match.value == 100.0
    assert [(p.concept, p.sign, p.fact.value) for p in match.parts] == [
        ("LongTermDebtNoncurrent", 1, 70.0), ("LongTermDebtCurrent", 1, 30.0)]


def test_negative_sign_subtracts():
    recipes = [R("PretaxIncome", T("InterestIncome", sign=-1))]
    match = resolve(recipes, lookup_in({"PretaxIncome": 50.0, "InterestIncome": 8.0}))
    assert match.value == 42.0
    assert [p.sign for p in match.parts] == [1, -1]


# --- alternatives inside a term -------------------------------------------------


def test_first_present_alternative_wins():
    recipes = [R(T("InterestExpense", "InterestExpenseDebt"))]
    both = resolve(recipes, lookup_in({"InterestExpense": 9.0, "InterestExpenseDebt": 7.0}))
    assert both.value == 9.0
    assert both.parts[0].concept == "InterestExpense"
    second = resolve(recipes, lookup_in({"InterestExpenseDebt": 7.0}))
    assert second.value == 7.0
    assert second.parts[0].concept == "InterestExpenseDebt"
    assert second.recipe_index == 0


def test_alternatives_after_the_first_hit_are_not_looked_up():
    lookup = lookup_in({"A": 1.0, "B": 2.0})
    resolve([R(T("A", "B"))], lookup)
    assert lookup.asked == ["A"]


# --- optional terms -------------------------------------------------------------


def test_optional_term_is_skipped_when_absent():
    recipes = [R("LongTermDebt", T("CommercialPaper", optional=True))]
    match = resolve(recipes, lookup_in({"LongTermDebt": 100.0}))
    assert match.value == 100.0
    assert [p.concept for p in match.parts] == ["LongTermDebt"]


def test_optional_term_counts_when_present():
    recipes = [R("LongTermDebt", T("CommercialPaper", optional=True))]
    match = resolve(recipes, lookup_in({"LongTermDebt": 100.0, "CommercialPaper": 15.0}))
    assert match.value == 115.0
    assert len(match.parts) == 2


def test_recipe_of_only_optional_terms_all_absent_does_not_match():
    recipes = [R(T("A", optional=True), T("B", optional=True)), R("C")]
    match = resolve(recipes, lookup_in({"C": 3.0}))
    # An empty sum is not a value: the next recipe gets its turn.
    assert match.recipe_index == 1
    assert match.value == 3.0
    assert resolve(recipes[:1], lookup_in({"C": 3.0})) is None


def test_recipe_of_only_optional_terms_matches_on_any_one_of_them():
    recipes = [R(T("A", optional=True), T("B", optional=True, sign=-1))]
    assert resolve(recipes, lookup_in({"B": 4.0})).value == -4.0


def test_optional_parts_of_a_failed_recipe_are_dropped():
    recipes = [R(T("A", optional=True), "Missing"), R("B")]
    match = resolve(recipes, lookup_in({"A": 1.0, "B": 2.0}))
    assert match.recipe_index == 1
    assert [p.concept for p in match.parts] == ["B"]


# --- details ---------------------------------------------------------------------


def test_a_fact_worth_zero_is_still_present():
    recipes = [R("InventoryNet"), R("Fallback")]
    match = resolve(recipes, lookup_in({"InventoryNet": 0.0, "Fallback": 5.0}))
    assert match.recipe_index == 0
    assert match.value == 0.0


def test_match_keeps_the_fact_objects_for_provenance():
    fact = Fact(12.0)
    match = resolve([R("Revenues")], lambda concept: fact if concept == "Revenues" else None)
    assert isinstance(match, Match)
    assert match.parts == [Part("Revenues", 1, fact)]
    assert match.parts[0].fact is fact


def test_an_empty_recipe_never_matches():
    assert resolve([R()], lookup_in({"A": 1.0})) is None
