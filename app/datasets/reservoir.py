from __future__ import annotations
import pandas as pd
from app.datasets.base import OfficialDataset

class ReservoirDaily(OfficialDataset):
    name, filename, table = "reservoir_daily", "reservoir_daily.csv", "reservoir_reading"
    required_columns = ("date", "reservoir_slug", "reservoir", "group", "full_depth_ft", "capacity_mcft", "level_ft",
                        "storage_mcft", "inflow_cusecs", "outflow_cusecs", "last_year_level_ft", "last_year_storage_mcft")

    def _clean(self, df, res):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if df["date"].isna().any():
            res.add("error", "bad_date", "unparseable dates removed", int(df["date"].isna().sum())); df = df.dropna(subset=["date"])
        df = df.drop_duplicates(subset=["reservoir_slug", "date"], keep="last")
        for c in ("level_ft", "storage_mcft", "capacity_mcft"):
            neg = df[c] < 0
            if neg.any():
                res.add("error", "negative_removed", f"negative {c} removed", int(neg.sum())); df = df[~neg]
        df["storage_pct"] = (df["storage_mcft"] / df["capacity_mcft"] * 100.0)
        over = df["storage_pct"] > 100.0
        if over.any():
            res.add("warning", "storage_exceeds_capacity",
                    f"{int(over.sum())} readings above 100% of capacity: pct clamped to 100, raw storage kept, flagged over_capacity", int(over.sum()))
        df["over_capacity"] = over
        df["storage_pct"] = df["storage_pct"].clip(upper=100.0)
        self.reservoirs = (df.sort_values("date").groupby("reservoir_slug")
                           .agg(name=("reservoir", "last"), basin_group=("group", "last"), full_depth_ft=("full_depth_ft", "last")).reset_index()
                           .rename(columns={"reservoir_slug": "slug"}))
        self.reservoirs["name"] = self.reservoirs["name"].str.replace(r"\*+$", "", regex=True).str.strip()
        changed = sorted(df.groupby("reservoir_slug").capacity_mcft.nunique().loc[lambda s: s > 1].index)
        res.add("info", "capacity_changes", "reservoirs whose capacity changes over time: " + (", ".join(changed) or "none"))
        return pd.DataFrame({"slug": df["reservoir_slug"], "date": df["date"].dt.date, "capacity_mcft": df["capacity_mcft"],
                             "level_ft": df["level_ft"], "storage_mcft": df["storage_mcft"], "storage_pct": df["storage_pct"],
                             "over_capacity": df["over_capacity"], "inflow_cusecs": df["inflow_cusecs"], "outflow_cusecs": df["outflow_cusecs"],
                             "last_year_level_ft": df["last_year_level_ft"], "last_year_storage_mcft": df["last_year_storage_mcft"]})

    def import_to_db(self, engine, dataset_id, res):
        self.reservoirs.to_sql("reservoir", engine, if_exists="append", index=False)
        return super().import_to_db(engine, dataset_id, res)
