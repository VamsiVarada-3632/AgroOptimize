from __future__ import annotations
import pandas as pd
from app.datasets.base import OfficialDataset
from app.datasets.normalize import district_key

class Rainfall(OfficialDataset):
    name, filename, table = "rainfall_by_district", "rainfall_by_district.csv", "rainfall"
    required_columns = ("report_year", "district", "season", "period", "actual_mm", "normal_mm", "pct_deviation", "printed_page")

    def _clean(self, df, res):
        df = df.copy()
        df = df[(df["actual_mm"].isna()) | (df["actual_mm"] >= 0)]
        df["is_total"] = df["period"].str.contains("total|Whole year", case=False, regex=True)
        df["month_start"] = pd.to_datetime(df["period"].where(~df["is_total"]), format="%b %Y", errors="coerce")
        bad_dates = int((~df["is_total"] & df["month_start"].isna()).sum())
        if bad_dates:
            res.add("error", "unparsed_period", "unparseable monthly period", bad_dates)
        out = pd.DataFrame({"district": df["district"].map(district_key), "imd_season": df["season"], "period": df["period"],
                            "month_start": df["month_start"].dt.date, "is_total": df["is_total"],
                            "actual_mm": df["actual_mm"], "normal_mm": df["normal_mm"], "pct_deviation": df["pct_deviation"],
                            "printed_page": df["printed_page"].astype(int)})
        calc = (out.actual_mm - out.normal_mm) / out.normal_mm * 100
        diff = (calc - out.pct_deviation).abs()
        bad = int((diff > 1.0).sum())
        res.add("warning" if bad else "info", "pct_deviation_recomputed",
                f"{bad} rows where printed % deviation differs from (actual-normal)/normal by more than 1 point", bad)
        # season totals must equal the sum of their months (rounding 2 mm)
        m = out[~out.is_total].groupby(["district", "imd_season"]).actual_mm.sum()
        t = out[out.is_total & (out.imd_season != "Whole year")].set_index(["district", "imd_season"]).actual_mm
        j = pd.concat([m, t], axis=1, keys=["m", "t"]).dropna()
        nbad = int(((j.m - j.t).abs() > 2.0).sum())
        res.add("warning" if nbad else "info", "season_totals_reconcile", f"{nbad} of {len(j)} season totals differ from the sum of months by more than 2 mm", nbad)
        return out
