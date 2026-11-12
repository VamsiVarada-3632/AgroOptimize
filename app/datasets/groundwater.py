from __future__ import annotations
import pandas as pd
from app.datasets.base import OfficialDataset
from app.datasets.normalize import district_key

class Groundwater(OfficialDataset):
    name, filename, table = "ground_water_level", "ground_water_level.csv", "groundwater"
    required_columns = ("report_year", "district", "period", "level_m", "printed_page")

    def _clean(self, df, res):
        df = df.copy()
        df["is_yearly_average"] = df["period"].eq("Yearly average")
        df["month_start"] = pd.to_datetime(df["period"].where(~df["is_yearly_average"]), format="%b-%y", errors="coerce")
        bad = int((~df["is_yearly_average"] & df["month_start"].isna()).sum())
        if bad:
            res.add("error", "unparsed_period", "unparseable period", bad)
        imp = df["level_m"].notna() & ((df["level_m"] <= 0) | (df["level_m"] >= 100))
        if imp.any():
            res.add("error", "impossible_depth_removed", "depth to water outside (0,100) m removed", int(imp.sum()))
            df.loc[imp, "level_m"] = float("nan")
        n = int(df["level_m"].isna().sum())
        res.add("info", "null_levels_kept", f"{n} months with no reading kept NULL", n)
        return pd.DataFrame({"district": df["district"].map(district_key), "period": df["period"],
                             "month_start": df["month_start"].dt.date, "is_yearly_average": df["is_yearly_average"],
                             "level_m_bgl": df["level_m"], "printed_page": df["printed_page"].astype(int)})
