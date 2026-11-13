from __future__ import annotations
import pandas as pd
from app.datasets.base import OfficialDataset
from app.datasets.normalize import district_key

class Irrigation(OfficialDataset):
    name, filename, table = "irrigation", "irrigation.csv", "irrigation"
    required_columns = ("report_year", "district", "table", "group", "item", "measure", "unit", "value", "printed_page")

    def _clean(self, df, res):
        df = df.copy()
        neg = df["value"] < 0
        if neg.any():
            res.add("error", "negative_removed", "negative values removed", int(neg.sum())); df = df[~neg]
        n = int(df["value"].isna().sum())
        if n:
            res.add("info", "null_values_kept", f"{n} values not reported are kept NULL", n)
        out = pd.DataFrame({"district": df["district"].map(district_key), "tbl": df["table"], "grp": df["group"], "item": df["item"],
                            "measure": df["measure"], "unit": df["unit"], "value": df["value"], "printed_page": df["printed_page"].astype(int)})
        pct = out[out.unit == "%"]
        bad = int(((pct.value < 0) | (pct.value > 100.0)).sum())
        if bad:
            res.add("warning", "percent_out_of_range", f"{bad} source-reported percentages above 100 (kept as printed; consumers clamp to 100)", bad)
        return out
