"""Table I of the paper: evaluated questions by valuation set and tier, counted from the question files.

    python count_questions.py [--questions ../data/questions]

Only Levels 2 to 5 are evaluated (the 16 Level 1 "find the number" questions of QA_set_v2 ask for a figure
from a 10-K, which a model without tools or filings cannot look up). Tier names in the files map to the
paper as: basic L2 = Single, trap = Trap, half L4 = Half A, half L5 = Half B, basic L3 = Full TB (textbook
policy), complex L3 = Full PR (practitioner policy).
"""
import argparse, collections, json, os

GROUP = {("basic", 2): "Single", ("trap", 2): "Trap", ("half", 4): "Half A", ("half", 5): "Half B",
         ("basic", 3): "Full TB", ("complex", 3): "Full PR"}
COLS = ["Single", "Trap", "Half A", "Half B", "Full TB", "Full PR"]
SETS = [("QA_set_v2.json", None, "2025"), ("QA_set_ver03.json", "2019", "2019"),
        ("QA_set_ver03.json", "2022", "2022"), ("QA_set_ver03_newco.json", None, "Held-out")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "questions"))
    a = ap.parse_args()
    rows, total, firms_all = [], collections.Counter(), set()
    for fname, year, label in SETS:
        qs = json.load(open(os.path.join(a.questions, fname)))["questions"]
        n, firms = collections.Counter(), set()
        for q in qs:
            tier, level = q.get("tier", "basic"), int(q["level"])
            if "@" in tier:
                tier, y = tier.split("@")
                if year and y != year:
                    continue
            g = GROUP.get((tier, level))
            if g:
                n[g] += 1; firms.add(q["ticker"])
        total.update(n); firms_all |= firms
        rows.append((f"{label} ({len(firms)})", n))
    rows.append((f"Total ({len(firms_all)})", total))
    print("| Set (firms) | " + " | ".join(COLS) + " | Total |")
    print("|---|" + "---|" * (len(COLS) + 1))
    for label, n in rows:
        print(f"| {label} | " + " | ".join(str(n[c] or "") for c in COLS) + f" | {sum(n.values())} |")


if __name__ == "__main__":
    main()
