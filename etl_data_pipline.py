import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.types import Integer, Numeric, String, Boolean
from dotenv import load_dotenv


from pathlib import Path 
from datetime import datetime, timezone


def create_schemas(engine):
    # Create schemas
    with engine.begin() as conn:

        conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS etl;
        """))
        conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS raw;
        """))

        conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS staging;
        """))

        conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS warehouse;
        """))
        conn.execute(text(""" 
            CREATE TABLE IF NOT EXISTS etl.run_table ( run_id VARCHAR(50) PRIMARY KEY, run_datetime TIMESTAMPTZ NOT NULL, python_script_path TEXT NOT NULL, python_script_directory TEXT NOT NULL ); """)
            )

def populate_run_info(engine, run_id, run_datetime, script_path, script_directory):
    with engine.begin() as conn:
        conn.execute(text(
            """ INSERT INTO etl.run_table ( run_id, run_datetime, python_script_path, python_script_directory )
            VALUES ( :run_id, :run_datetime, :python_script_path, :python_script_directory )
            """),{
                "run_id": run_id, "run_datetime": run_datetime, "python_script_path": str(script_path), "python_script_directory": str(script_directory)
            })


def main():
    WEEK1_DATE ="2020-01-01"
    INP_FILE = "Sample_Data.xlsx"
    # ============================================================
    # 1. DATABASE CONFIGURATION
    # ============================================================
    load_dotenv()

    USER_NAME = os.getenv("USER_NAME")
    PASSWORD = os.getenv("PASSWORD")
    HOST = os.getenv("HOST")
    PORT = os.getenv("PORT")
    DB_NAME = os.getenv("DB_NAME")

    DATABASE_URL = rf"postgresql+psycopg2://{USER_NAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL)


    # ============================================================ 
    # 3. GENERATE RUN INFORMATION 
    #  ============================================================ 
    # Unique identifier for this ETL execution. 
    run_id = datetime.now(timezone.utc).strftime( "%Y%m%d%H%M%S%f" ) 
    run_datetime = datetime.now(timezone.utc) 


    script_path = Path(__file__).resolve() 
    # script_path  = Path.cwd()
    script_directory = script_path.parent

    create_schemas(engine)
    populate_run_info(engine, run_id, run_datetime, script_path, script_directory)
    
    
    # ============================================================
    # 3. EXPECTED COLUMNS
    # ============================================================

    EXPECTED_COLUMNS = [
    "Week",
    "Product",
    "Sales_Units",
    "Cost_of_Goods_Sold_COGS",
    "Inventory_Level",
    "Demand_Forecast",
    "Price_Per_Unit",
    "Gross_Profit",
    "Operating_Profit",
    "Revenue",
    "Inventory_Turnover_Ratio",
    "Gross_Profit_Margin",
    "Revenue_Growth"
    ]

    df = pd.read_excel(INP_FILE)

    print("Original shape:", df.shape)
    print("Original columns:")
    print(df.columns.tolist())

    # ============================================================
    # 5. RAW LAYER
    # ============================================================

    # Check columns before doing any transformation.
    if list(df.columns) != EXPECTED_COLUMNS:
        missing_columns = set(EXPECTED_COLUMNS) - set(df.columns)
        extra_columns = set(df.columns) - set(EXPECTED_COLUMNS)

        raise ValueError(
            f"Column validation failed.\n"
            f"Missing columns: {missing_columns}\n"
            f"Extra columns: {extra_columns}"
        )

    print("Column validation: PASSED")


    df["run_id"] = run_id
    # Save raw data exactly as received.
    # The raw layer is intentionally not type-converted.

    df.to_sql(
        name="sales_data",
        con=engine,
        schema="raw",
        if_exists="replace",
        index=False
    )

    print("Raw layer loaded successfully.")
    print("Raw rows:", len(df))


    
    # ============================================================
    # 6. STAGING LAYER
    # ============================================================
    staging_df = df.copy()
    # ------------------------------------------------------------
    # Standardize column names
    # ------------------------------------------------------------
    staging_df.columns = [
        "week",
        "product",
        "sales_units",
        "cost_of_goods_sold_cogs",
        "inventory_level",
        "demand_forecast",
        "price_per_unit",
        "gross_profit",
        "operating_profit",
        "revenue",
        "inventory_turnover_ratio",
        "gross_profit_margin",
        "revenue_growth",
        'run_id'
    ]

    # Convert empty strings to NULL/NaN
    staging_df = staging_df.replace(
    r"^\s*$",
    pd.NA,
    regex=True
    )
    numeric_columns = [
    "week",
    "sales_units",
    "cost_of_goods_sold_cogs",
    "inventory_level",
    "demand_forecast",
    "price_per_unit",
    "gross_profit",
    "operating_profit",
    "revenue",
    "inventory_turnover_ratio",
    "gross_profit_margin",
    "revenue_growth"
]

    for column in numeric_columns:
        staging_df[column] = pd.to_numeric(
            staging_df[column],
            errors="coerce"
        )


    # Product should remain a string.
    staging_df["product"] = staging_df["product"].astype("string")

    before_dedup = len(staging_df)

    staging_df = staging_df.drop_duplicates(
        subset=["week", "product"],
        keep="first"
    )

    after_dedup = len(staging_df)

    print(
        f"Removed {before_dedup - after_dedup} duplicate rows."
    )

    staging_df.to_sql(
    name="sales_data",
    con=engine,
    schema="staging",
    if_exists="replace",
    index=False,
    dtype={
        "week": Integer(),
        "product": String(100),
        "sales_units": Numeric(),
        "cost_of_goods_sold_cogs": Numeric(),
        "inventory_level": Numeric(),
        "demand_forecast": Numeric(),
        "price_per_unit": Numeric(),
        "gross_profit": Numeric(),
        "operating_profit": Numeric(),
        "revenue": Numeric(),
        "inventory_turnover_ratio": Numeric(),
        "gross_profit_margin": Numeric(),
        "revenue_growth": Numeric(),
        "run_id": String(50)
    }
    )

    print("Staging layer loaded successfully.")
    print("Staging rows:", len(staging_df))

    create_warehouse_tables(engine)


    # ============================================================
    # 7. WAREHOUSE LAYER
    # ============================================================
    # warehouse_df = staging_df.copy()
    warehouse_df = staging_df.drop( columns=["run_id"] ).copy()
    # ------------------------------------------------------------
    # Remove rows where Sales_Units is missing
    # ------------------------------------------------------------
    before_sales_filter = len(warehouse_df)
    warehouse_df = warehouse_df[
        warehouse_df["sales_units"].notna()
    ].copy()
    removed_sales_rows = (
    before_sales_filter - len(warehouse_df)
    )

    print(
        f"Removed {removed_sales_rows} rows "
        f"because Sales_Units was missing."
    )
    imputation_columns = [
    "cost_of_goods_sold_cogs",
    "inventory_level",
    "demand_forecast",
    "price_per_unit",
    "gross_profit",
    "operating_profit",
    "revenue",
    "inventory_turnover_ratio",
    "gross_profit_margin",
    "revenue_growth"
]

    warehouse_df["modified_row"] = (
        warehouse_df.isna().any(axis=1)
    )


    for column in imputation_columns:

        median_value = warehouse_df[column].median()
        warehouse_df[column] = warehouse_df[column].fillna(
            median_value
        )



    # 10. LOAD PRODUCT DIMENSION
    products = ( warehouse_df[["product"]] .dropna() .drop_duplicates() )
    with engine.begin() as conn:
        for product in products["product"]:
            conn.execute(
                text(""" INSERT INTO warehouse.dim_product (product) VALUES (:product) ON CONFLICT (product) DO NOTHING """),
                { "product": str(product) }
            )

    # 11. LOAD WEEK DIMENSION
    weeks = ( warehouse_df[["week"]] .dropna() .drop_duplicates() )
    with engine.begin() as conn:
        for week in weeks["week"]:
            week = int(week)
            # Week 1 = 2020-01-01
            # Each following week = +7 days
            start_date = ( pd.Timestamp(WEEK1_DATE) + pd.Timedelta(days=(week - 1) * 7) ).date()

            conn.execute(
                text(""" INSERT INTO warehouse.dim_week ( week_key, week, start_date )
                    VALUES ( :week_key, :week, :start_date )
                    ON CONFLICT (week_key)
                    DO UPDATE SET week = EXCLUDED.week, start_date = EXCLUDED.start_date
                    """),
                    { "week_key": week, "week": week, "start_date": start_date, }
            )

    product_keys = pd.read_sql(
    """ SELECT product_key, product FROM warehouse.dim_product """, engine,
      )
    week_keys = pd.read_sql( """ SELECT week_key, week FROM warehouse.dim_week """, engine, )
    # 13. BUILD FACT TABLE
    fact_df = warehouse_df.merge( product_keys, on="product", how="left", )
    fact_df = fact_df.merge( week_keys, on="week", how="left", )
    # Check that all dimension keys were found
    if fact_df["product_key"].isna().any(): 
        raise ValueError( "Some products could not be matched to dim_product." )
    if fact_df["week_key"].isna().any():
        raise ValueError( "Some weeks could not be matched to dim_week." )

    # Add current ETL run ID
    fact_df["run_id"] = run_id
    fact_df = fact_df[ [ "week_key", "product_key", "sales_units", "cost_of_goods_sold_cogs", "inventory_level"
                    , "demand_forecast", "price_per_unit", "gross_profit", "operating_profit", "revenue"
                    , "inventory_turnover_ratio", "gross_profit_margin", "revenue_growth", "modified_row", "run_id" ] ]

    fact_df.to_sql(name='sales_data', con=engine, schema='warehouse', if_exists='append'
               , index=False, chunksize=1000
            #    , dtype=dtypes
               )
    
    create_warehouse_view(engine)




def create_warehouse_view(engine):
    with engine.begin() as conn:
        conn.execute(text("""
    DROP VIEW warehouse.vw_warehouse_sales;
    CREATE  VIEW warehouse.vw_warehouse_sales AS
                        SELECT f.sales_key,
                        -- Dimension attributes
                        w.week, w.start_date, p.product,

                        -- Sales measures
                        f.sales_units, f.cost_of_goods_sold_cogs, f.inventory_level, f.demand_forecast,
                        f.price_per_unit, f.gross_profit, f.operating_profit, f.revenue
                        , f.inventory_turnover_ratio, f.gross_profit_margin, f.revenue_growth
                        , (f.gross_profit - f.operating_profit) as operating_cost,
                        -- ETL information
                        f.modified_row, f.run_id

                        FROM warehouse.sales_data AS f
                        INNER JOIN warehouse.dim_week AS w ON f.week_key = w.week_key
                        INNER JOIN warehouse.dim_product AS p ON f.product_key = p.product_key;

                        """))

def create_warehouse_tables(engine):
    with engine.begin() as conn:
    # Product dimension
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS warehouse.dim_product 
            ( product_key SERIAL PRIMARY KEY, product VARCHAR(100) NOT NULL UNIQUE )
                    """))
        
        # Week dimension
        conn.execute(text("""
    CREATE TABLE IF NOT EXISTS warehouse.dim_week 
    ( week_key INTEGER PRIMARY KEY, week INTEGER NOT NULL UNIQUE, start_date DATE NOT NULL )
                        """))
        
        # Single warehouse fact table
        conn.execute(text("""
    CREATE TABLE IF NOT EXISTS warehouse.sales_data ( sales_key SERIAL PRIMARY KEY,
                        week_key INTEGER NOT NULL, product_key INTEGER NOT NULL,
                        sales_units NUMERIC NOT NULL, cost_of_goods_sold_cogs NUMERIC, inventory_level NUMERIC,
                        demand_forecast NUMERIC, price_per_unit NUMERIC, gross_profit NUMERIC, operating_profit NUMERIC, revenue NUMERIC,
                        inventory_turnover_ratio NUMERIC, gross_profit_margin NUMERIC, revenue_growth NUMERIC,
                        modified_row BOOLEAN NOT NULL DEFAULT FALSE, run_id VARCHAR(50) NOT NULL,
                        FOREIGN KEY (week_key) REFERENCES warehouse.dim_week(week_key),
                        FOREIGN KEY (product_key) REFERENCES warehouse.dim_product(product_key),
                        FOREIGN KEY (run_id) REFERENCES etl.run_table(run_id),
                        UNIQUE ( week_key, product_key, run_id )
                        )
                        """))



if __name__ == '__main__':
    main()