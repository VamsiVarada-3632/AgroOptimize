"""SQLAlchemy schema of the official-data database (migration 0001).

Every fact table carries `dataset_id` -> dataset_registry so any figure shown
to a user can be traced to a file, report year and hash."""
from sqlalchemy import (Column, Date, Float, ForeignKey, Integer, MetaData, String, Table, Text, Boolean)

metadata = MetaData()

dataset_registry = Table("dataset_registry", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False),
    Column("filename", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("report_year", String),
    Column("rows_raw", Integer), Column("rows_clean", Integer),
    Column("imported_at", String, nullable=False),
    Column("notes", Text))

ingestion_log = Table("ingestion_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("level", String), Column("code", String), Column("message", Text), Column("rows", Integer))

district = Table("district", metadata,
    Column("norm_name", String, primary_key=True),
    Column("name", String, nullable=False), Column("code", Integer), Column("is_state", Boolean, nullable=False))

crop = Table("crop", metadata,
    Column("norm_name", String, primary_key=True), Column("name", String, nullable=False), Column("crop_group", String))

# one row per (district, crop, season, measure) with raw and standardised value
crop_stat = Table("crop_stat", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("crop", String, nullable=False),
    Column("season", String, nullable=False),            # Total/Irrigated/Unirrigated (area) or All seasons/Kharif/Rabi/rice sub-season
    Column("measure", String, nullable=False),           # area / production / yield
    Column("unit_raw", String), Column("value_raw", Float),
    Column("unit_std", String), Column("value_std", Float),   # ha | tonne | kg_per_ha | nuts | nuts_per_ha
    Column("printed_page", Integer))

state_crop_series = Table("state_crop_series", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("crop", String, nullable=False), Column("year_start", Integer, nullable=False),
    Column("measure", String, nullable=False), Column("unit_raw", String), Column("value_raw", Float),
    Column("unit_std", String), Column("value_std", Float), Column("printed_page", Integer))

land_use = Table("land_use", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("category", String, nullable=False),
    Column("measure", String, nullable=False), Column("unit", String), Column("value", Float), Column("printed_page", Integer))

irrigation = Table("irrigation", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("tbl", String), Column("grp", String), Column("item", String),
    Column("measure", String), Column("unit", String), Column("value", Float), Column("printed_page", Integer))

rainfall = Table("rainfall", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("imd_season", String, nullable=False),
    Column("period", String, nullable=False), Column("month_start", Date),   # NULL for season / whole-year totals
    Column("is_total", Boolean, nullable=False),
    Column("actual_mm", Float), Column("normal_mm", Float), Column("pct_deviation", Float), Column("printed_page", Integer))

groundwater = Table("groundwater", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("period", String, nullable=False),
    Column("month_start", Date), Column("is_yearly_average", Boolean, nullable=False),
    Column("level_m_bgl", Float), Column("printed_page", Integer))

reservoir = Table("reservoir", metadata,
    Column("slug", String, primary_key=True), Column("name", String, nullable=False),
    Column("basin_group", String), Column("full_depth_ft", Float))

reservoir_reading = Table("reservoir_reading", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("slug", String, ForeignKey("reservoir.slug"), nullable=False), Column("date", Date, nullable=False),
    Column("capacity_mcft", Float), Column("level_ft", Float), Column("storage_mcft", Float),
    Column("storage_pct", Float), Column("over_capacity", Boolean),
    Column("inflow_cusecs", Float), Column("outflow_cusecs", Float),
    Column("last_year_level_ft", Float), Column("last_year_storage_mcft", Float))

district_reservoir_map = Table("district_reservoir_map", metadata,
    Column("district", String, nullable=False), Column("slug", String, nullable=False),
    Column("basis", String, nullable=False))

# Filled by the MSP extractor / scrapers (migration 0001 creates them empty).
msp = Table("msp", metadata,
    Column("crop", String, nullable=False), Column("variety", String), Column("marketing_season", String, nullable=False),
    Column("msp_rs_qtl", Float, nullable=False), Column("cost_rs_qtl", Float), Column("margin_pct", Float),
    Column("source_file", String, nullable=False), Column("source_page", Integer), Column("verified", Boolean, nullable=False))

agronomy_reference = Table("agronomy_reference", metadata,
    Column("crop", String, nullable=False), Column("condition", String, nullable=False),
    Column("water_req_mm", Float), Column("n_kg_ha", Float), Column("p_kg_ha", Float), Column("k_kg_ha", Float),
    Column("s_kg_ha", Float), Column("duration_days", Integer), Column("pdf_page", Integer), Column("printed_page", Integer),
    Column("evidence", String), Column("note", String),
    Column("source_url", String, nullable=False), Column("retrieved_at", String, nullable=False))

# Soil Health Card portal: number of tested samples per class, per district and cycle (counts as published).
soil_health = Table("soil_health", metadata,
    Column("dataset_id", Integer, ForeignKey("dataset_registry.id")),
    Column("district", String, nullable=False), Column("cycle", String, nullable=False), Column("district_code", Integer),
    Column("n_High".lower(), Integer),
    Column("n_Medium".lower(), Integer),
    Column("n_Low".lower(), Integer),
    Column("p_High".lower(), Integer),
    Column("p_Medium".lower(), Integer),
    Column("p_Low".lower(), Integer),
    Column("k_High".lower(), Integer),
    Column("k_Medium".lower(), Integer),
    Column("k_Low".lower(), Integer),
    Column("S_Sufficient".lower(), Integer),
    Column("S_Deficient".lower(), Integer),
    Column("OC_High".lower(), Integer),
    Column("OC_Medium".lower(), Integer),
    Column("OC_Low".lower(), Integer),
    Column("pH_Acidic".lower(), Integer),
    Column("pH_Neutral".lower(), Integer),
    Column("pH_Alkaline".lower(), Integer),
    Column("EC_Saline".lower(), Integer),
    Column("EC_NonSaline".lower(), Integer),
    Column("Fe_Sufficient".lower(), Integer),
    Column("Fe_Deficient".lower(), Integer),
    Column("Zn_Sufficient".lower(), Integer),
    Column("Zn_Deficient".lower(), Integer),
    Column("Cu_Sufficient".lower(), Integer),
    Column("Cu_Deficient".lower(), Integer),
    Column("B_Sufficient".lower(), Integer),
    Column("B_Deficient".lower(), Integer),
    Column("Mn_Sufficient".lower(), Integer),
    Column("Mn_Deficient".lower(), Integer),
    Column("last_processed", String),
    Column("source_url", String, nullable=False), Column("retrieved_at", String, nullable=False))
