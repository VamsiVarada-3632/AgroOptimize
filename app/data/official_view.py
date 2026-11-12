"""Official-data view: the four frames the profile builder consumes (crop, land, rainfall, water),
assembled ONLY from the official database (app/datasets). Columns without an official source are NaN -
never filled with an estimate. Every frame row carries `data_source` naming the dataset(s) it came from.

  crop     one row per (district, season, crop): official yield/area/production + TNAU dose + MSP/CACP cost
  land     one row per (district, season): irrigation share + Soil Health Card class shares/fertility index
  rainfall one row per (district, month): official actual/normal mm and % deviation (IMD)
  water    one row per (district, month): capacity-weighted reservoir storage % (where a reservoir is mapped)
"""
from __future__ import annotations
from functools import lru_cache
from typing import Dict, List

import numpy as np
import pandas as pd

from app.datasets import reference as ref
from app.datasets import service as svc

SRC_CROP = "Official: TN Season & Crop Report 2024-25 (area/yield/production); TNAU Crop Production Guide 2020 (NPK); CACP/MSP notification KMS 2024-25 (MSP, cost)"
SRC_SOIL = "Official: Soil Health Card portal (sample counts), TN Season & Crop Report (irrigation)"
SRC_RAIN = "Official: IMD district rainfall, TN Season & Crop Report 2024-25"
SRC_WATER = "Official: TN Water Resources Dept. daily reservoir levels"
MONTH_ORDER = ["June", "July", "August", "September", "October", "November", "December", "January", "February", "March", "April", "May"]
CLASS_SCORE = {"Low": 0.0, "Medium": 0.5, "High": 1.0}    # fertility index: share-weighted class score (documented rule)


def _district_rows() -> pd.DataFrame:
    d = svc.districts()
    return d[d.is_state == 0].reset_index(drop=True)


def locations() -> List[str]:
    """Official display names of every district that has crop statistics."""
    out = []
    for _, r in _district_rows().iterrows():
        if not svc.crop_stats(r.norm_name).empty:
            out.append(str(r["name"]))
    return out


def class_shares(row: dict, prefix: str, classes=("low", "medium", "high")) -> dict:
    vals = {c: float(row[f"{prefix}_{c}"]) for c in classes}
    tot = sum(vals.values())
    return {c: (v / tot if tot else np.nan) for c, v in vals.items()}


def soil_summary(district: str) -> dict | None:
    """Soil Health Card summary for a district: class shares, dominant class, fertility index (0-100)."""
    row = svc.soil_health(district)
    if row is None:
        return None
    out = {"samples_tested": int(max(sum(row[f"{p}_{c}"] for c in cs) for p, cs in
                                    {"n": ("high", "medium", "low"), "p": ("high", "medium", "low"), "k": ("high", "medium", "low")}.items())),
           "cycle": row["cycle"]}
    scores = []
    for p in ("n", "p", "k", "oc"):
        sh = class_shares(row, p)
        out[f"{p}_shares"] = sh
        out[f"{p}_status"] = max(sh, key=lambda k: sh[k]).capitalize()
        scores.append(sum(CLASS_SCORE[k.capitalize()] * v for k, v in sh.items()))
    ph = {c: float(row[f"ph_{c}"]) for c in ("acidic", "neutral", "alkaline")}
    out["ph_shares"] = {k: v / sum(ph.values()) for k, v in ph.items()}
    out["fertility_index"] = round(100.0 * float(np.mean(scores)), 2)
    return out


@lru_cache(maxsize=1)
def frames() -> Dict[str, pd.DataFrame]:
    return {"crop": _crop_frame(), "land": _land_frame(), "rainfall": _rain_frame(), "water": _water_frame()}


def clear_cache() -> None:
    frames.cache_clear()


# ------------------------------------------------------------------------------------------ crop
def _crop_frame() -> pd.DataFrame:
    agro, msp = svc.agronomy_table(), svc.msp_table()
    kms = msp[msp.marketing_season == ref.MARKETING_SEASON]
    price: dict = {}
    for crop, g in kms.groupby("crop"):
        g = g.copy()
        g["rank"] = g.variety.map(lambda v: ref.COST_VARIETY_PREFERENCE.index(v) if v in ref.COST_VARIETY_PREFERENCE else 99)
        g = g[g.cost_rs_qtl.notna()].sort_values("rank") if g.cost_rs_qtl.notna().any() else g.sort_values("rank")
        price[crop] = g.iloc[0]
    groups = {r.norm_name: r.crop_group for r in svc._q("select norm_name, crop_group from crop").itertuples()}
    rows = []
    for _, d in _district_rows().iterrows():
        cs = svc.crop_stats(d.norm_name)
        if cs.empty:
            continue
        pv = cs.pivot_table(index=["crop", "season"], columns="measure", values="value_std", aggfunc="first")
        for crop in sorted(cs.crop.unique()):
            def area(s):
                try:
                    v = pv.loc[(crop, s), "area"]
                    return float(v) if pd.notna(v) else np.nan
                except KeyError:
                    return np.nan
            total, irr = area("Total"), area("Irrigated")
            for season in ("Kharif", "Rabi"):
                key = ref.RICE_SEASON_CROSSWALK[season] if crop == "rice" else season
                try:
                    y = float(pv.loc[(crop, key), "yield"]); p = pv.loc[(crop, key), "production"]
                except KeyError:
                    continue
                if not (y > 0):
                    continue
                unit = cs[(cs.crop == crop) & (cs.measure == "yield")].unit_std.iloc[0]
                share = irr / total if total and total > 0 and pd.notna(irr) else np.nan
                dose, rule = ref.pick_dose(agro, crop, d.norm_name, season, 0.0 if np.isnan(share) else share)
                pr = price.get(crop)
                rows.append({
                    "Location": d["name"], "Year": ref.REPORT_YEAR_START, "Season": season, "Crop_Name": crop,
                    "Crop_Type": groups.get(crop), "Yield_Kg_Ha": y if unit == "kg_per_ha" else np.nan, "Yield_Unit": unit,
                    "Area_Ha": total, "Irrigated_Area_Ha": irr, "Irrigated_Share": share,
                    "Production_Tonnes": float(p) if pd.notna(p) else np.nan,
                    "Fertilizer_N_Kg_Ha": None if dose is None else dose.n_kg_ha,
                    "Fertilizer_P_Kg_Ha": None if dose is None else dose.p_kg_ha,
                    "Fertilizer_K_Kg_Ha": None if dose is None else dose.k_kg_ha,
                    "Dose_Rule": rule, "Dose_Source": None if dose is None else f"{dose.source_url} p.{int(dose.printed_page)} (pdf p.{int(dose.pdf_page)})",
                    "MSP_Rs_Qtl": np.nan if pr is None else pr.msp_rs_qtl,
                    "Cost_Rs_Qtl": np.nan if pr is None else pr.cost_rs_qtl,
                    "Price_Source": None if pr is None else f"{pr.source_file}" + (f" p.{int(pr.source_page)}" if pd.notna(pr.source_page) else ""),
                    "Water_Req_mm": np.nan, "Pesticide_Cost_Rs_Ha": np.nan, "Labor_Days_Ha": np.nan,
                    "Crop_Duration_Days": np.nan, "Sowing_Month": None, "Harvest_Month": None,
                    "data_source": SRC_CROP,
                })
    df = pd.DataFrame(rows)
    df["Revenue_Rs_Ha"] = df.Yield_Kg_Ha / 100.0 * df.MSP_Rs_Qtl          # yield (q/ha) x MSP (Rs/q)
    df["Cost_Rs_Ha"] = df.Yield_Kg_Ha / 100.0 * df.Cost_Rs_Qtl           # yield (q/ha) x CACP cost (Rs/q)
    df["Revenue_Rs_Lakh"] = df.Revenue_Rs_Ha * df.Area_Ha / 1e5         # district potential revenue at MSP (not reported revenue)
    return df


# ------------------------------------------------------------------------------------------ land
def _land_frame() -> pd.DataFrame:
    rows = []
    for _, d in _district_rows().iterrows():
        lu = svc.land_use(d.norm_name) if True else {}
        net, gross = lu.get("Net area sown"), lu.get("Gross area sown")
        soil = soil_summary(d.norm_name)
        for season in ("Kharif", "Rabi"):
            r = {"Location": d["name"], "Year": ref.REPORT_YEAR_START, "Season": season,
                 "Net_Area_Sown_Ha": net, "Gross_Area_Sown_Ha": gross, "Soil_Type": None, "Avg_Soil_pH": np.nan,
                 "Organic_Carbon_Percent": np.nan, "Irrigation_Percent": np.nan, "data_source": SRC_SOIL}
            if soil:
                r.update({"N_Status": soil["n_status"], "P_Status": soil["p_status"], "K_Status": soil["k_status"],
                          "OC_Status": soil["oc_status"], "Soil_Fertility_Index": soil["fertility_index"],
                          "Soil_Samples_Tested": soil["samples_tested"]})
            else:
                r.update({"N_Status": None, "P_Status": None, "K_Status": None, "OC_Status": None,
                          "Soil_Fertility_Index": np.nan, "Soil_Samples_Tested": np.nan})
            rows.append(r)
    df = pd.DataFrame(rows)
    # irrigation share of the district's cropped area = sum of crop irrigated area / sum of crop total area
    cf = _crop_area_share()
    df["Irrigation_Percent"] = df.Location.map(cf)
    return df


def _crop_area_share() -> dict:
    out = {}
    for _, d in _district_rows().iterrows():
        cs = svc.crop_stats(d.norm_name)
        a = cs[(cs.measure == "area") & (cs.season.isin(["Total", "Irrigated"]))]
        a = a[~a.crop.isin(["total", "total cereals", "total pulses", "foodgrains", "total foodgrains"])]
        t, i = a[a.season == "Total"].value_std.sum(), a[a.season == "Irrigated"].value_std.sum()
        out[d["name"]] = round(min(100.0, i / t * 100.0), 2) if t else np.nan
    return out


# ------------------------------------------------------------------------------------------ rainfall
def _rain_frame() -> pd.DataFrame:
    rows = []
    for _, d in _district_rows().iterrows():
        r = svc.rainfall(d.norm_name)
        r = r[r.is_total == 0]
        for x in r.itertuples():
            m = pd.Timestamp(x.month_start)
            rows.append({"Location": d["name"], "Year": ref.REPORT_YEAR_START, "Month": m.strftime("%B"), "Month_Start": x.month_start,
                         "IMD_Season": x.imd_season, "Monthly_Rainfall_mm": x.actual_mm, "Normal_Rainfall_mm": x.normal_mm,
                         "Deviation_Percent": x.pct_deviation, "Humidity_Percent": np.nan, "Max_Temp_C": np.nan,
                         "Min_Temp_C": np.nan, "data_source": SRC_RAIN})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ water
def _water_frame() -> pd.DataFrame:
    rows = []
    for _, d in _district_rows().iterrows():
        gw = svc.groundwater(d.norm_name)
        gw = gw[gw.is_yearly_average == 0] if not gw.empty else gw
        for m in MONTH_ORDER:
            start_year = ref.REPORT_YEAR_START if m in MONTH_ORDER[:7] else ref.REPORT_YEAR_START + 1
            mm = MONTH_ORDER.index(m) + 6 if MONTH_ORDER.index(m) < 7 else MONTH_ORDER.index(m) - 6
            s = pd.Timestamp(year=start_year, month=mm, day=1); e = s + pd.offsets.MonthEnd(0)
            st = svc.district_storage_pct(d.norm_name, s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))
            lvl = np.nan
            if not gw.empty:
                hit = gw[pd.to_datetime(gw.month_start) == s]
                lvl = float(hit.level_m_bgl.iloc[0]) if not hit.empty and pd.notna(hit.level_m_bgl.iloc[0]) else np.nan
            rows.append({"Location": d["name"], "Year": ref.REPORT_YEAR_START, "Month": m, "Storage_Percent": np.nan if st is None else st,
                         "Groundwater_Level_m_bgl": lvl, "Groundwater_Status": None, "Deficit_Surplus_MCM": np.nan,
                         "data_source": SRC_WATER})
    return pd.DataFrame(rows)
