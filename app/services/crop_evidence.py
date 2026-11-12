"""
Per-crop, source-cited recommendation evidence.

For every crop in a recommended plan this builds ten criteria - rainfall,
soil, water, budget, fertiliser, market price, MSP, duration, expected yield
and risks - from the official datasets only. Each criterion carries:

    status     supported | caution | concern | info | unavailable
    statement  one sentence written from the cited numbers
    source     [{dataset, file, detail}] naming the official dataset(s) used

Rules: no number is invented or estimated; a quantity the official data does
not publish is reported as "Official data unavailable" (never silently
dropped); TNAU guide text is quoted as printed. Statuses use only the
comparisons stated in the sentence itself (e.g. rainfall deviation sign,
MSP versus CACP cost) - nothing is inferred from crop agronomy that is not
in a dataset.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.datasets import soil_master as _sm
from app.datasets.agronomy_master import agronomy_for
from app.datasets.normalize import crop_key

UNAVAILABLE = "Official data unavailable"
YIELD_CUT_CAUTION_PCT = 20.0   # a reliability-check yield cut above this is flagged "caution"
MAX_QUOTE = 260   # TNAU text is quoted verbatim but cut to this length (marked with an ellipsis)

SRC_RAIN = {"dataset": "IMD district rainfall (TN Season & Crop Report 2024-25)", "file": "rainfall_by_district.csv"}
SRC_SOIL = {"dataset": "Soil Health Card portal (soilhealth.dac.gov.in)", "file": "soil_health_tn.csv / soil_master.csv"}
SRC_RESERVOIR = {"dataset": "TN Water Resources Dept daily reservoir levels", "file": "reservoir_daily.csv"}
SRC_IRRIG = {"dataset": "TN Season & Crop Report 2024-25 - irrigated/unirrigated area", "file": "irrigation.csv / crops_by_district.csv"}
SRC_STATS = {"dataset": "TN Season & Crop Report 2024-25 - district crop area, production, yield", "file": "crops_by_district.csv"}
SRC_MSP = {"dataset": "PIB Minimum Support Price notification with CACP cost of production (A2+FL)", "file": "msp_extracted.csv"}
SRC_TNAU = {"dataset": "TNAU Crop Production Guide", "file": "agronomy_master.csv / agronomy_tnau.csv"}


def _src(base: dict, detail: Optional[str] = None) -> dict:
    return {**base, **({"detail": detail} if detail else {})}


def _quote(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = " ".join(str(text).split())
    return t if len(t) <= MAX_QUOTE else t[:MAX_QUOTE].rstrip() + " ..."


def _crit(id_: str, label: str, status: str, statement: str, sources: List[dict], evidence: Optional[dict] = None) -> dict:
    return {"id": id_, "label": label, "status": status, "statement": statement, "sources": sources, "evidence": evidence or {}}


def _unavailable(id_: str, label: str, what: str, sources: List[dict]) -> dict:
    return _crit(id_, label, "unavailable", f"{UNAVAILABLE}: {what}", sources)


def _tnau_page(c: dict) -> str:
    return (c.get("sources") or {}).get("agronomy") or "TNAU Crop Production Guide"


def _master(crop: str):
    key = crop_key(crop)
    try:
        from app.datasets.agronomy_master import load_agronomy_master
        df = load_agronomy_master()
    except Exception:  # master missing/invalid -> every TNAU-only criterion reports unavailable
        return None
    for _, r in df.iterrows():
        if crop_key(str(r["crop"])) == key:
            return r
    return None


def _txt(m, col: str) -> Optional[str]:
    """Cell text of a master row, None for NULL/NaN/empty."""
    if m is None:
        return None
    v = m.get(col)
    return None if v is None or v != v or str(v).strip() == "" else str(v)


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- criteria

def _rainfall(rp: dict, m) -> dict:
    r = rp.get("rainfall") or {}
    dev, act, nor = _num(r.get("avg_deviation_percent")), _num(r.get("season_actual_mm")), _num(r.get("season_normal_mm"))
    need = _quote(_txt(m, "suitable_rainfall"))
    srcs = [_src(SRC_RAIN)] + ([_src(SRC_TNAU, "suitable rainfall, quoted as printed")] if need else [])
    if dev is None and act is None:
        return _unavailable("rainfall", "Rainfall suitability", f"no official {rp.get('season')} rainfall record for {rp.get('location')}.", srcs)
    parts = []
    if act is not None and nor is not None:
        parts.append(f"{rp.get('season')} rainfall in {rp.get('location')} was {act:.0f} mm against a normal of {nor:.0f} mm")
        if dev is not None:
            parts.append(f"({dev:+.1f}% from normal)")
    elif dev is not None:
        parts.append(f"{rp.get('season')} rainfall in {rp.get('location')} deviated {dev:+.1f}% from normal")
    stmt = " ".join(parts) + "."
    stmt += (f" TNAU guide for this crop: \"{need}\"." if need
             else f" The crop's own rainfall requirement: {UNAVAILABLE} (not printed in the TNAU guide extract).")
    status = "info" if dev is None else ("caution" if dev <= -20 else "supported" if dev >= -19.99 else "info")
    return _crit("rainfall", "Rainfall suitability", status, stmt, srcs,
                 {"season_actual_mm": act, "season_normal_mm": nor, "deviation_pct": dev, "tnau_rainfall": need})


def _soil(rp: dict, m, fzd: dict) -> dict:
    loc = rp.get("location") or ""
    try:
        sm = _sm.explanation_support(loc)
    except ValueError:
        sm = {"available": False, "text": f"Soil: {UNAVAILABLE}.", "evidence": None}
    s = rp.get("soil") or {}
    fert = _num(s.get("fertility_index"))
    srcs = [_src(SRC_SOIL)]
    stmt = sm["text"]
    if fert is not None:
        stmt = f"District Soil Health Card fertility index {fert:.0f}/100 (N {s.get('n_status')}, P {s.get('p_status')}, K {s.get('k_status')} dominant classes). " + stmt
    soil_need = _quote(_txt(m, "recommended_soil"))
    ph_need = _quote(_txt(m, "soil_ph"))
    if soil_need or ph_need:
        srcs.append(_src(SRC_TNAU, "recommended soil / pH, quoted as printed"))
        stmt += " TNAU guide: " + "; ".join(x for x in (f"soil \"{soil_need}\"" if soil_need else None, f"pH \"{ph_need}\"" if ph_need else None) if x) + "."
    else:
        stmt += f" The crop's soil and pH requirement: {UNAVAILABLE}."
    if not sm.get("available") and fert is None:
        return _unavailable("soil", "Soil suitability", f"no Soil Health Card record for {loc}.", srcs)
    label = (fzd or {}).get("soil_label")
    status = {"good": "supported", "medium": "caution", "poor": "concern"}.get(label, "info") if (fzd or {}).get("applied", True) else "info"
    return _crit("soil", "Soil suitability", status, stmt, srcs,
                 {"fertility_index": fert, "fuzzy_label": label, "soil_master": sm.get("evidence") if sm.get("available") else UNAVAILABLE,
                  "tnau_soil": soil_need, "tnau_ph": ph_need})


def _water(rp: dict, c: dict, d: dict, m, fzd: dict) -> dict:
    w = rp.get("water") or {}
    storage = _num(w.get("avg_storage_percent"))
    irr = _num(d.get("irrigated_share"))
    if irr is None and _num(c.get("rainfed_share")) is not None:
        irr = 1.0 - _num(c.get("rainfed_share"))
    srcs = [_src(SRC_IRRIG)]
    bits = []
    if irr is not None:
        bits.append(f"Officially {irr:.0%} of this crop's area in {rp.get('location')} is irrigated")
    else:
        bits.append(f"Irrigated share of this crop: {UNAVAILABLE}")
    applied = (fzd or {}).get("applied", True)
    if storage is not None and applied:
        srcs.append(_src(SRC_RESERVOIR))
        risk = _num((fzd or {}).get("irrigation_risk"))
        bits.append(f"reservoir storage averaged {storage:.0f}% of capacity" + (f" (irrigation risk {risk:.2f})" if risk is not None else ""))
    else:
        bits.append(f"reservoir level: {UNAVAILABLE} for this district/season")
    need = _quote(_txt(m, "water_requirement") or _txt(m, "irrigation_frequency"))
    if need:
        srcs.append(_src(SRC_TNAU, "water requirement / irrigation schedule, quoted as printed"))
        bits.append(f"TNAU guide: \"{need}\"")
    else:
        bits.append(f"the crop's water requirement: {UNAVAILABLE}")
    label = (fzd or {}).get("water_label")
    status = "info"
    if applied and storage is not None:
        status = {"high": "supported", "medium": "caution", "low": "concern"}.get(label, "info")
    return _crit("water", "Water availability", status, "; ".join(bits) + ".", srcs,
                 {"irrigated_share": irr, "reservoir_storage_pct": storage if applied else None, "fuzzy_label": label if applied else None,
                  "tnau_water": need})


def _budget(c: dict, d: dict, plan_cost: float, ctx_budget: Optional[float], budget_recorded: bool) -> dict:
    cost_q = _num(c.get("cost_rs_qtl"))
    tonnes = _num(d.get("expected_tonnes"))
    srcs = [_src(SRC_MSP, "cost of production per quintal"), _src(SRC_STATS, "yield")]
    if cost_q is None or tonnes is None:
        return _unavailable("budget", "Budget suitability", "no CACP cost of cultivation for this crop.", srcs)
    crop_cost = cost_q * 10 * tonnes          # Rs/qtl x quintals (1 t = 10 qtl), the same basis as the optimiser's cost objective
    share = 100 * crop_cost / plan_cost if plan_cost else None
    stmt = (f"CACP cost of production Rs {cost_q:,.0f}/quintal x {tonnes * 10:,.1f} quintals expected = Rs {crop_cost:,.0f}"
            + (f" ({share:.0f}% of the plan's Rs {plan_cost:,.0f})." if share is not None else "."))
    if not budget_recorded:
        stmt += f" Budget limit: {UNAVAILABLE} (run saved before budgets were recorded)."
        status = "info"
    elif ctx_budget:
        ok = plan_cost <= ctx_budget + 1e-6
        stmt += f" The whole plan is {'within' if ok else 'over'} your Rs {ctx_budget:,.0f} budget."
        status = "supported" if ok else "concern"
    else:
        stmt += " No budget limit was set for this plan."
        status = "info"
    return _crit("budget", "Budget suitability", status, stmt, srcs,
                 {"cost_rs_per_qtl": cost_q, "expected_quintals": round(tonnes * 10, 2), "crop_cost_rs": round(crop_cost, 0),
                  "plan_cost_rs": plan_cost, "budget_rs": ctx_budget})


def _fertiliser(c: dict, d: dict) -> dict:
    n, p, k = (_num(x) for x in (c.get("fert_n_kg_ha"), c.get("fert_p_kg_ha"), c.get("fert_k_kg_ha")))
    page = _tnau_page(c)
    srcs = [_src(SRC_TNAU, f"fertiliser dose - {page}")]
    if None in (n, p, k):
        return _unavailable("fertiliser", "Fertiliser requirement", "TNAU publishes no complete N-P-K dose for this crop.", srcs)
    mult = _num(d.get("fertilizer_multiplier"))
    stmt = f"TNAU recommends N {n:g} : P2O5 {p:g} : K2O {k:g} kg/ha ({c.get('dose_rule')})"
    if mult is not None:
        stmt += f"; this plan applies {mult:.2f} x that dose = {n * mult:.0f} : {p * mult:.0f} : {k * mult:.0f} kg/ha"
    stmt += "."
    return _crit("fertiliser", "Fertiliser requirement", "info", stmt, srcs,
                 {"recommended_npk_kg_ha": [n, p, k], "plan_multiplier": mult, "dose_rule": c.get("dose_rule")})


def _market() -> dict:
    return _unavailable("market_price", "Market price", "no official market (mandi) price dataset is loaded, so no current market price is "
                        "stated. The official price floor (MSP) is given separately.", [{"dataset": "Agmarknet mandi prices", "file": "not loaded"}])


def _msp(c: dict) -> dict:
    msp, cost = _num(c.get("msp_rs_qtl")), _num(c.get("cost_rs_qtl"))
    price_src = (c.get("sources") or {}).get("price")
    srcs = [_src(SRC_MSP, price_src)]
    if msp is None:
        return _unavailable("msp", "Minimum Support Price", "no MSP notified for this crop.", srcs)
    stmt = f"Notified MSP Rs {msp:,.0f}/quintal"
    status = "info"
    margin = None
    if cost is not None and cost > 0:
        margin = 100 * (msp / cost - 1)
        stmt += f" against CACP cost of production Rs {cost:,.0f}/quintal ({margin:+.0f}% margin, computed from these two official figures)"
        status = "supported" if margin > 0 else "concern"
    else:
        stmt += f"; CACP cost of production: {UNAVAILABLE}"
    return _crit("msp", "Minimum Support Price (MSP)", status, stmt + ".", srcs,
                 {"msp_rs_qtl": msp, "cost_rs_qtl": cost, "margin_pct": None if margin is None else round(margin, 1), "source_file": price_src})


def _duration(m) -> dict:
    dur = _quote(_txt(m, "duration"))
    srcs = [_src(SRC_TNAU, "duration, quoted as printed")]
    if not dur:
        return _unavailable("duration", "Cultivation duration", "TNAU guide extract has no duration for this crop.", srcs)
    return _crit("duration", "Cultivation duration", "info", f"TNAU guide: \"{dur}\".", srcs, {"tnau_duration": dur, "evidence_pages": _txt(m, "evidence_pages")})


def _yield(rp: dict, c: dict, d: dict, m, fzd: dict) -> dict:
    book = _num(d.get("book_yield_t_ha"))
    exp = _num(d.get("expected_yield_t_ha"))
    srcs = [_src(SRC_STATS, f"{rp.get('location')} yield")]
    if book is None:
        return _unavailable("yield", "Expected yield", "no official district yield for this crop.", srcs)
    applied = (fzd or {}).get("applied", True)
    stmt = f"Official {rp.get('location')} yield {book:.2f} t/ha"
    status = "supported"
    if applied and exp is not None:
        cut = 100 * (1 - exp / book) if book else 0.0
        stmt += f"; after the rainfall/water/soil reliability check the plan expects {exp:.2f} t/ha ({cut:.0f}% lower)"
        if cut > YIELD_CUT_CAUTION_PCT:
            status = "caution"
    else:
        stmt += "; the reliability check was not applied for this district/season (reservoir data unavailable), so the official yield is used unadjusted"
    ref = _quote(_txt(m, "expected_yield"))
    if ref:
        srcs.append(_src(SRC_TNAU, "expected yield, quoted as printed"))
        stmt += f". TNAU guide reference: \"{ref}\""
    return _crit("yield", "Expected yield", status, stmt + ".", srcs,
                 {"official_yield_t_ha": book, "plan_expected_yield_t_ha": exp if applied else book, "tnau_yield": ref})


def _risks(rp: dict, c: dict, d: dict, fzd: dict, criteria: Dict[str, dict]) -> dict:
    items: List[dict] = []
    r = rp.get("rainfall") or {}
    dev = _num(r.get("avg_deviation_percent"))
    rainfed = _num(c.get("rainfed_share"))
    if dev is not None and dev <= -20:
        items.append({"text": f"Rainfall was {dev:+.1f}% below normal" + (f" and {rainfed:.0%} of this crop's area is rainfed" if rainfed is not None else ""),
                      "sources": [_src(SRC_RAIN)] + ([_src(SRC_IRRIG)] if rainfed is not None else [])})
    if (fzd or {}).get("applied", True):
        risk = _num((fzd or {}).get("irrigation_risk"))
        if risk is not None and risk >= 0.5:
            items.append({"text": f"Irrigation risk is {risk:.2f} (reservoir storage low for the season)", "sources": [_src(SRC_RESERVOIR)]})
    else:
        items.append({"text": f"Reservoir level: {UNAVAILABLE} - yield could not be adjusted for water uncertainty", "sources": [_src(SRC_RESERVOIR)]})
    msp_ev = criteria["msp"]["evidence"]
    if msp_ev.get("margin_pct") is not None and msp_ev["margin_pct"] <= 0:
        items.append({"text": f"MSP is {msp_ev['margin_pct']:+.0f}% against CACP cost of production (no margin at the support price)", "sources": [_src(SRC_MSP)]})
    unavailable = [k for k, v in criteria.items() if v["status"] == "unavailable"]
    if unavailable:
        gap_src = [s for k in unavailable for s in criteria[k]["sources"]]
        items.append({"text": f"{UNAVAILABLE} for: " + ", ".join(criteria[k]["label"].lower() for k in unavailable) + " - these could not be checked",
                      "sources": gap_src})
    if not items:
        return _crit("risks", "Risks", "info", "No risk is flagged by the official datasets used here (this is not a guarantee of safety).",
                     [_src(SRC_RAIN), _src(SRC_RESERVOIR), _src(SRC_MSP)], {"items": []})
    status = "concern" if any(("below normal" in i["text"] or "no margin" in i["text"]) for i in items) else "caution"
    srcs: List[dict] = []
    for i in items:
        for s in i["sources"]:
            if s not in srcs:
                srcs.append(s)
    return _crit("risks", "Risks", status, "; ".join(i["text"] for i in items) + ".", srcs, {"items": items})


# --------------------------------------------------------------------------- entry point

def build_crop_evidence(rp: dict, fzd: dict, crop_rows: List[dict], candidates: Dict[str, dict], plan_cost: float,
                        budget_rs: Optional[float], budget_recorded: bool) -> List[dict]:
    """One entry per crop shown in the plan, each with the ten source-cited criteria."""
    out = []
    for d in crop_rows:
        c = candidates.get(d["crop"])
        if c is None:
            continue
        m = _master(d["crop"])
        crit: Dict[str, dict] = {}
        for item in (_rainfall(rp, m), _soil(rp, m, fzd), _water(rp, c, d, m, fzd), _budget(c, d, plan_cost, budget_rs, budget_recorded),
                     _fertiliser(c, d), _market(), _msp(c), _duration(m), _yield(rp, c, d, m, fzd)):
            crit[item["id"]] = item
        crit["risks"] = _risks(rp, c, d, fzd, crit)
        counts = {s: sum(1 for v in crit.values() if v["status"] == s) for s in ("supported", "caution", "concern", "info", "unavailable")}
        out.append({"crop": d["crop"], "share_pct": d["share_pct"], "area_ha": d["area_ha"],
                    "criteria": list(crit.values()), "status_counts": counts,
                    "headline": (f"{d['crop'].title()} ({d['share_pct']:.0f}% of land): {counts['supported']} supported, {counts['caution'] + counts['concern']} "
                                 f"to watch, {counts['unavailable']} with {UNAVAILABLE.lower()}.")})
    return out
