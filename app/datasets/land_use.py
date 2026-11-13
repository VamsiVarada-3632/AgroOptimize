from __future__ import annotations
import pandas as pd
from app.datasets.base import OfficialDataset
from app.datasets.normalize import district_key

# the 12 mutually exclusive categories that partition total geographical area (sub-items of non-agri uses excluded)
PARTITION = ["Forest", "Barren and unculturable area", "Land put to non-agricultural uses: total", "Cultivable waste",
             "Permanent pastures and other grazing lands", "Miscellaneous tree crops and groves not included in net area sown",
             "Current fallow", "Other fallow", "Net area sown"]

class LandUse(OfficialDataset):
    name, filename, table = "land_use", "land_use.csv", "land_use"
    required_columns = ("report_year", "district", "category", "measure", "unit", "value", "printed_page")

    def _clean(self, df, res):
        df = df.copy()
        neg = df["value"] < 0
        if neg.any():
            res.add("error", "negative_removed", "negative values removed", int(neg.sum())); df = df[~neg]
        out = pd.DataFrame({"district": df["district"].map(district_key), "category": df["category"], "measure": df["measure"],
                            "unit": df["unit"], "value": df["value"], "printed_page": df["printed_page"].astype(int)})
        a = out[out.measure == "area_ha"].pivot_table(index="district", columns="category", values="value", aggfunc="first")
        if "Total geographical area" in a:
            parts = a[[c for c in PARTITION if c in a]].sum(axis=1)
            rel = (parts - a["Total geographical area"]).abs() / a["Total geographical area"]
            bad = int((rel > 0.01).sum())
            res.add("warning" if bad else "info", "categories_sum_to_total",
                    f"{bad} of {len(a)} districts: land-use categories differ from total area by more than 1%", bad)
        return out
