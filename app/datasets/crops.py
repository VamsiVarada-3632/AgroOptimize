"""crops_by_district.csv and crops_state_series.csv."""
from __future__ import annotations
import pandas as pd
from app.datasets.base import CleanResult, OfficialDataset, DataValidationError
from app.datasets.normalize import crop_key, district_key
from app.datasets.units import to_std

KNOWN_MEASURES = {"area", "production", "yield"}


def _std_columns(df: pd.DataFrame, res: CleanResult) -> pd.DataFrame:
    std = [to_std(m, u, v) for m, u, v in zip(df["measure"], df["unit"], df["value"])]   # raises on unknown unit
    df["unit_std"] = [s[0] for s in std]
    df["value_std"] = [s[1] for s in std]
    return df


class CropsByDistrict(OfficialDataset):
    name = "crops_by_district"
    filename = "crops_by_district.csv"
    table = "crop_stat"
    required_columns = ("report_year", "crop", "group", "measure", "season_or_split", "unit", "district", "value", "printed_page")

    def validate_raw(self, df):
        issues = super().validate_raw(df)
        bad = set(df["measure"].unique()) - KNOWN_MEASURES
        if bad:
            raise DataValidationError(f"crops_by_district: unknown measures {bad}")
        return issues

    def _clean(self, df, res):
        n_null = int(df["value"].isna().sum())
        if n_null:
            res.add("info", "null_values_kept", f"{n_null} values not reported in the source are kept as NULL (never zero-filled)", n_null)
        neg = df["value"] < 0
        if neg.any():
            res.add("error", "negative_removed", "negative values removed", int(neg.sum()))
            df = df[~neg].copy()
        df = _std_columns(df.copy(), res)
        out = pd.DataFrame({
            "district": df["district"].map(district_key), "crop": df["crop"].map(crop_key),
            "crop_label": df["crop"], "crop_group": df["group"],
            "season": df["season_or_split"], "measure": df["measure"],
            "unit_raw": df["unit"], "value_raw": df["value"], "unit_std": df["unit_std"], "value_std": df["value_std"],
            "printed_page": df["printed_page"].astype(int)})
        self._consistency(out, res)
        return out

    @staticmethod
    def _consistency(out, res):
        """production = area x yield on the 'All seasons' rows of mass-unit crops (rounding tolerance 10 %)."""
        piv = out[out.season.isin(["Total", "All seasons"]) & out.unit_std.isin(["ha", "tonne", "kg_per_ha"])].pivot_table(
            index=["district", "crop"], columns="measure", values="value_std", aggfunc="first")
        if {"area", "production", "yield"} <= set(piv.columns):
            p = piv.dropna()
            p = p[p["production"] > 0]
            rel = (p["area"] * p["yield"] / 1000.0 - p["production"]).abs() / p["production"]
            bad = int((rel > 0.10).sum())
            res.add("warning" if bad else "info", "production_vs_area_x_yield",
                    f"{bad} of {len(p)} district-crop rows differ by more than 10% between production and area x yield", bad)

    def import_to_db(self, engine, dataset_id, res):
        f = res.frame.rename(columns={"crop_label": "_l", "crop_group": "_g"}).drop(columns=["_l", "_g"])
        f.insert(0, "dataset_id", dataset_id)
        f.to_sql("crop_stat", engine, if_exists="append", index=False)
        return len(f)


class CropsStateSeries(OfficialDataset):
    name = "crops_state_series"
    filename = "crops_state_series.csv"
    table = "state_crop_series"
    required_columns = ("report_year", "crop", "year", "measure", "unit", "value", "printed_page")
    AGGREGATES = {"foodgrains", "total cereals", "total pulses"}

    def _clean(self, df, res):
        df = df.copy()
        df["year_start"] = df["year"].str.slice(0, 4).astype(int)
        if (df["value"] <= 0).any():
            res.add("error", "non_positive_removed", "non-positive values removed", int((df["value"] <= 0).sum()))
            df = df[df["value"] > 0]
        std = [to_std(m, u, v) for m, u, v in zip(df["measure"], df["unit"], df["value"])]
        out = pd.DataFrame({
            "crop": df["crop"].map(crop_key), "year_start": df["year_start"], "measure": df["measure"],
            "unit_raw": df["unit"], "value_raw": df["value"],
            "unit_std": [s[0] for s in std], "value_std": [s[1] for s in std], "printed_page": df["printed_page"].astype(int)})
        res.add("info", "aggregates_kept", "aggregate rows (foodgrains, total cereals/pulses) kept; use AGGREGATE_CROPS to exclude them from crop-level statistics")
        return out


AGGREGATE_CROPS = CropsStateSeries.AGGREGATES
