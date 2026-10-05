CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;
"""

CREATE_RUN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etl.etl_run (

    run_id UUID PRIMARY KEY,

    run_datetime TIMESTAMPTZ NOT NULL,

    source_file TEXT NOT NULL,

    status VARCHAR(30) NOT NULL,

    raw_row_count INTEGER,

    staging_row_count INTEGER,

    warehouse_row_count INTEGER,

    duplicate_count INTEGER,

    rejected_count INTEGER,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


CREATE_RAW_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw.source_sales (

    run_id UUID NOT NULL,

    source_row_number INTEGER NOT NULL,

    week TEXT,

    product TEXT,

    sales_units TEXT,

    cost_of_goods_sold_cogs TEXT,

    inventory_level TEXT,

    demand_forecast TEXT,

    price_per_unit TEXT,

    gross_profit TEXT,

    operating_profit TEXT,

    revenue TEXT,

    inventory_turnover_ratio TEXT,

    gross_profit_margin TEXT,

    revenue_growth TEXT,

    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""




CREATE_STAGING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS staging.sales (

    run_id UUID NOT NULL,

    source_row_number INTEGER NOT NULL,

    week INTEGER,

    product TEXT,

    sales_units BIGINT,

    cost_of_goods_sold_cogs NUMERIC(18, 6),

    inventory_level NUMERIC(18, 6),

    demand_forecast NUMERIC(18, 6),

    price_per_unit NUMERIC(18, 6),

    gross_profit NUMERIC(18, 6),

    operating_profit NUMERIC(18, 6),

    revenue NUMERIC(18, 6),

    inventory_turnover_ratio NUMERIC(18, 8),

    gross_profit_margin NUMERIC(18, 8),

    revenue_growth NUMERIC(18, 8),

    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_staging_run_product_week
        UNIQUE(run_id, product, week)
);
"""



CREATE_WAREHOUSE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS warehouse.dim_product (

    product_key BIGSERIAL PRIMARY KEY,

    product_name TEXT NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS warehouse.dim_week (

    week_key BIGSERIAL PRIMARY KEY,

    week_number INTEGER NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS warehouse.fact_sales (

    sales_key BIGSERIAL PRIMARY KEY,

    source_row_number INTEGER NOT NULL,

    product_key BIGINT NOT NULL
        REFERENCES warehouse.dim_product(product_key),

    week_key BIGINT NOT NULL
        REFERENCES warehouse.dim_week(week_key),

    sales_units BIGINT NOT NULL,

    unit_cogs NUMERIC(18, 6),

    inventory_level NUMERIC(18, 6),

    demand_forecast NUMERIC(18, 6),

    price_per_unit NUMERIC(18, 6),

    gross_profit NUMERIC(18, 6),

    operating_profit NUMERIC(18, 6),

    revenue NUMERIC(18, 6),

    inventory_turnover_ratio NUMERIC(18, 8),

    gross_profit_margin NUMERIC(18, 8),

    revenue_growth NUMERIC(18, 8),

    row_modified BOOLEAN NOT NULL DEFAULT FALSE,

    modified_columns JSONB,

    run_id UUID NOT NULL,

    CONSTRAINT uq_fact_sales_run_product_week
        UNIQUE(run_id, product_key, week_key)
);


CREATE TABLE IF NOT EXISTS warehouse.data_quality_issues (

    issue_key BIGSERIAL PRIMARY KEY,

    run_id UUID NOT NULL,

    source_row_number INTEGER,

    product TEXT,

    week INTEGER,

    column_name TEXT,

    issue_type TEXT NOT NULL,

    issue_detail TEXT,

    severity VARCHAR(20),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_fact_sales_run_id
    ON warehouse.fact_sales(run_id);


CREATE INDEX IF NOT EXISTS idx_quality_run_id
    ON warehouse.data_quality_issues(run_id);


CREATE INDEX IF NOT EXISTS idx_quality_issue_type
    ON warehouse.data_quality_issues(issue_type);
"""