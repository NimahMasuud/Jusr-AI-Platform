"""Urgency suggestions from clinician-written criteria (config/urgency_criteria.json).

Nothing here is a clinical opinion of ours. The criteria come from the clinical lead and are
DRAFT MOCK values for the demo. The helper only suggests. A clinician sets the urgency.
It never guesses: a value with no matching rule, no recognised unit, or no named sub-test is
reported under notEvaluated, and staff handle it by hand.
"""
import re
from typing import Any, Optional

SEVERITY = {"no_suggestion": 0, "routine": 1, "clinician_decides": 2, "urgent": 3}
NEG_WORDS = ("non reactive", "non-reactive", "nonreactive", "not detected")


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%/()]+", " ", (s or "").lower())).strip()


class Criteria:
    def __init__(self, data: dict):
        self.data = data
        self.index: dict[str, dict] = {}
        for t in data.get("tests", []):
            for n in t["names"]:
                self.index[norm_name(n)] = t
        self.ambiguous = {norm_name(k): v for k, v in data.get("ambiguousNames", {}).items()}

    @property
    def empty(self) -> bool:
        return not self.data.get("tests")


def _num_match(when: dict, x: float) -> bool:
    return ((("gt" not in when) or x > when["gt"]) and (("gte" not in when) or x >= when["gte"]) and
            (("lt" not in when) or x < when["lt"]) and (("lte" not in when) or x <= when["lte"]))


def _ratio_match(when: dict, r: float) -> bool:
    return ((("ratioGt" not in when) or r > when["ratioGt"]) and (("ratioGte" not in when) or r >= when["ratioGte"]) and
            (("ratioLt" not in when) or r < when["ratioLt"]) and (("ratioLte" not in when) or r <= when["ratioLte"]))


def _text_words(text: str) -> set[str]:
    t = (text or "").lower()
    for w in NEG_WORDS:
        t = t.replace(w, "negative")
    return set(re.findall(r"[a-z]+", t))


def _unit_factor(test: dict, unit: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """Returns (factor, note). A unit we do not recognise gives (None, reason): never guess."""
    if not unit:
        return 1.0, f"No unit was given, so {test['baseUnit']} was assumed."
    f = test["unitFactors"].get(unit.strip().lower().replace(" ", ""))
    if f is None:
        return None, f"The unit '{unit}' is not recognised for this test. A clinician must confirm the unit."
    return float(f), None


def evaluate(criteria: Criteria, results: list[dict]) -> dict[str, Any]:
    matched, not_evaluated, notes = [], [], []
    for item in results:
        name = item["test"]
        key = norm_name(name)
        if key in criteria.ambiguous:
            not_evaluated.append({"test": name, "why": criteria.ambiguous[key]})
            continue
        test = criteria.index.get(key)
        if test is None:
            not_evaluated.append({"test": name, "why": "No criterion has been supplied for this test."})
            continue
        kind, band_hit = test["kind"], None

        if kind == "numeric":
            if item.get("value") is None:
                not_evaluated.append({"test": name, "why": "The result value is missing. This is a data-quality task for the coordinator."})
                continue
            factor, note = _unit_factor(test, item.get("unit"))
            if factor is None:
                not_evaluated.append({"test": name, "why": note})
                continue
            if note:
                notes.append(f"{name}: {note}")
            x = item["value"] * factor
            band_hit = next((b for b in test["bands"] if _num_match(b["when"], x)), None)
            if band_hit is None:
                lo, hi = test["normalRange"]
                if lo <= x <= hi:
                    matched.append({"ruleId": f"{test['id']}-NORMAL", "test": name, "value": item["value"], "suggestion": "no_suggestion",
                                    "reason": f"Within the reference range ({test['referenceText']}). Nothing to act on.", "specialty": "None", "lookFor": ""})
                else:
                    not_evaluated.append({"test": name, "why": "The value is outside the reference range but no rule covers this band. A clinician decides."})
                continue
            shown = item["value"]

        elif kind == "qualitative":
            if not item.get("text"):
                not_evaluated.append({"test": name, "why": "The result text is missing. This is a data-quality task for the coordinator."})
                continue
            words = _text_words(item["text"])
            band_hit = next((b for b in test["bands"] if words & set(b["when"]["text"])), None)
            if band_hit is None:
                not_evaluated.append({"test": name, "why": f"The result '{item['text']}' is not recognised as positive or negative."})
                continue
            shown = item["text"]

        elif kind == "ratio_to_uln":
            if item.get("value") is None:
                not_evaluated.append({"test": name, "why": "The result value is missing. This is a data-quality task for the coordinator."})
                continue
            uln = item.get("upperLimit")
            if not uln:
                not_evaluated.append({"test": name, "why": "The lab's own upper limit of normal is needed. The listing does not give one."})
                continue
            ratio = item["value"] / uln
            band_hit = next((b for b in test["bands"] if _ratio_match(b["when"], ratio)), None)
            if band_hit is None:
                matched.append({"ruleId": f"{test['id']}-NORMAL", "test": name, "value": item["value"], "suggestion": "no_suggestion",
                                "reason": "At or below the lab's upper limit. Nothing to act on.", "specialty": "None", "lookFor": ""})
                continue
            shown = item["value"]
        else:
            not_evaluated.append({"test": name, "why": "Unknown rule type in the criteria file."})
            continue

        entry = {"ruleId": band_hit["id"], "test": name, "value": shown, "suggestion": band_hit["suggestion"],
                 "reason": band_hit["reason"], "specialty": band_hit["specialty"], "lookFor": band_hit["lookFor"]}
        if band_hit.get("confidential"):
            entry["confidential"] = True
        matched.append(entry)

    if not matched:
        return {"suggestion": None, "matched": [], "notEvaluated": not_evaluated, "notes": notes}
    top = max(matched, key=lambda m: SEVERITY[m["suggestion"]])["suggestion"]
    driving = [m for m in matched if m["suggestion"] == top]
    return {
        "suggestion": top,
        "matched": matched,
        "driving": driving,
        "notEvaluated": not_evaluated,
        "notes": notes,
        "specialties": sorted({m["specialty"] for m in driving if m["specialty"] not in ("", "None")}),
        "lookFor": sorted({m["lookFor"] for m in driving if m["lookFor"]}),
        "confidential": any(m.get("confidential") for m in matched),
    }
