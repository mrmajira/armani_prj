import numpy as np
import pandas as pd

from sqlalchemy import create_engine
from dotenv import load_dotenv
import os




def main():
    # ============================================================
    # CONFIGURATION
    # ============================================================
    SALES_FORECAST_FILE_PATH = 'pca_sales_forecast.csv'

    TRAIN_END = 234

    # What should the pricing engine optimize?
    #
    # "profit"  -> recommended
    # "revenue" -> alternative
    #
    OBJECTIVE = "profit"

    # Minimum number of historical observations required
    # for a pricing regime.
    MIN_SAMPLES = 15

    # Minimum acceptable gross margin
    MIN_GROSS_MARGIN = 0.15       # 15%

    # Maximum allowed price movement per week
    MAX_PRICE_CHANGE = 0.05       # +/- 5%

    # Number of sales regimes
    N_SALES_QUARTILES = 4

    # Number of margin regimes
    N_MARGIN_QUARTILES = 4


    load_dotenv()

    USER_NAME = os.getenv("USER_NAME")
    PASSWORD = os.getenv("PASSWORD")
    HOST = os.getenv("HOST")
    PORT = os.getenv("PORT")
    DB_NAME = os.getenv("DB_NAME")

    DATABASE_URL = rf"postgresql+psycopg2://{USER_NAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL)


    sql = 'SELECT * FROM warehouse.vw_warehouse_sales; '
    historical  = pd.read_sql(sql, con=engine)


    # ============================================================
    # 2. CLEAN DATA
    # ============================================================

    numeric_columns = [
        "week",
        "sales_units",
        "demand_forecast",
        "price_per_unit",
        "cost_of_goods_sold_cogs",
        "revenue",
        "gross_profit",
        "inventory_level"
    ]

    for column in numeric_columns:
        historical[column] = pd.to_numeric(
            historical[column],
            errors="coerce"
        )


    historical = historical.sort_values(
        ["product", "week"]
    ).reset_index(drop=True)


    # ============================================================
    # 3. CALCULATE PRICING METRICS
    # ============================================================

    # Gross margin %
    #
    # (Price - COGS) / Price
    #
    historical["gross_margin_pct"] = (
        (
            historical["price_per_unit"]
            - historical["cost_of_goods_sold_cogs"]
        )
        /
        historical["price_per_unit"]
    )
    


    # Markup %
    #
    # (Price - COGS) / COGS
    #
    historical["markup_pct"] = (
        (
            historical["price_per_unit"]
            - historical["cost_of_goods_sold_cogs"]
        )
        /
        historical["cost_of_goods_sold_cogs"]
    )


    # Recalculate revenue and profit where useful
    historical["calculated_revenue"] = (
        historical["price_per_unit"]
        * historical["sales_units"]
    )


    historical["calculated_profit"] = (
        (
            historical["price_per_unit"]
            -
            historical["cost_of_goods_sold_cogs"]
        )
        *
        historical["sales_units"]
    )


    # ============================================================
    # 4. REMOVE INVALID PRICING OBSERVATIONS
    # ============================================================

    pricing_data = historical[
        (historical["sales_units"] >= 0) &
        (historical["price_per_unit"] > 0) &
        (historical["cost_of_goods_sold_cogs"] > 0) &
        (historical["gross_margin_pct"].notna())
    ].copy()



    pricing_data["sales_quartile"] = (
    pricing_data
    .groupby("product")["sales_units"]
    .transform(assign_sales_quartile)
)

    pricing_data["margin_quartile"] = (
        pricing_data
        .groupby(
            ["product", "sales_quartile"]
        )["gross_margin_pct"]
        .transform(assign_margin_quartile)
    )


    # ============================================================
    # 7. CALCULATE PERFORMANCE OF EACH PRICING REGIME
    # ============================================================

    strategy_summary = (
        pricing_data
        .groupby(
            [
                "product",
                "sales_quartile",
                "margin_quartile"
            ]
        )
        .agg(
            observations=("week", "count"),

            avg_sales=("sales_units", "mean"),
            median_sales=("sales_units", "median"),

            avg_price=("price_per_unit", "mean"),
            median_price=("price_per_unit", "median"),

            min_price=("price_per_unit", "min"),
            max_price=("price_per_unit", "max"),

            avg_margin=("gross_margin_pct", "mean"),
            median_margin=("gross_margin_pct", "median"),

            avg_markup=("markup_pct", "mean"),

            avg_revenue=("calculated_revenue", "mean"),
            total_revenue=("calculated_revenue", "sum"),

            avg_profit=("calculated_profit", "mean"),
            total_profit=("calculated_profit", "sum")
        )
        .reset_index()
    )




    # ============================================================
    # 8. SELECT BEST STRATEGY
    # ============================================================
    #
    # We select the best margin regime separately for each:
    #
    # product + sales quartile
    #
    # This produces the historical pricing strategy table.
    # ============================================================

    if OBJECTIVE == "profit":

        strategy_summary["objective_value"] = (
            strategy_summary["avg_profit"]
        )

    elif OBJECTIVE == "revenue":

        strategy_summary["objective_value"] = (
            strategy_summary["avg_revenue"]
        )

    else:

        raise ValueError(
            "OBJECTIVE must be 'profit' or 'revenue'"
        )


    # Remove strategies with too few observations
    strategy_candidates = strategy_summary[
        strategy_summary["observations"] >= MIN_SAMPLES
    ].copy()


    # Best strategy within each sales regime
    best_strategies = (
        strategy_candidates
        .sort_values(
            [
                "product",
                "sales_quartile",
                "objective_value"
            ],
            ascending=[
                True,
                True,
                False
            ]
        )
        .groupby(
            ["product", "sales_quartile"],
            as_index=False
        )
        .first()
    )


    forecast=pd.read_csv(SALES_FORECAST_FILE_PATH)
    # ============================================================
    # 9. PREPARE THE 26-WEEK SALES FORECAST
    # ============================================================
    #
    # This section assumes:
    #
    # sales_forecast
    #
    # already exists from your PCA model and looks like:
    #
    # week | product | predicted_sales
    #
    # If your PCA output is wide, convert it first.
    # ============================================================


    forecast["predicted_sales"] = pd.to_numeric(
        forecast["predicted_sales"],
        errors="coerce"
    )

    


    # ============================================================
    # 10. FIND HISTORICAL SALES QUARTILE FOR EACH FORECAST
    # ============================================================
    #
    # IMPORTANT:
    # The quartile boundaries are calculated ONLY from training
    # history.
    # ============================================================

    sales_thresholds = (
        pricing_data
        .groupby("product")["sales_units"]
        .quantile(
            [0.25, 0.50, 0.75]
        )
        .unstack()
        .rename(
            columns={
                0.25: "sales_q25",
                0.50: "sales_q50",
                0.75: "sales_q75"
            }
        )
        .reset_index()
    )


    forecast = forecast.merge(
        sales_thresholds,
        on="product",
        how="left"
    )

    forecast["sales_quartile"] = (
    forecast
    .apply(
        determine_sales_quartile,
        axis=1
    )
)



    
    # ============================================================
    # 12. CONNECT FORECAST TO HISTORICAL STRATEGY
    # ============================================================

    forecast = forecast.merge(
        best_strategies[
            [
                "product",
                "sales_quartile",
                "margin_quartile",
                "observations",
                "median_price",
                "avg_price",
                "min_price",
                "max_price",
                "median_margin",
                "avg_margin",
                "avg_sales",
                "avg_revenue",
                "avg_profit",
                "objective_value"
            ]
        ],
        on=[
            "product",
            "sales_quartile"
        ],
        how="left"
    )

    # ============================================================
    # 13. GET CURRENT PRICE
    # ============================================================
    #
    # Current price = price at week 234.
    # ============================================================

    current_prices = (
        historical[
            historical["week"] == TRAIN_END
        ][
            [
                "product",
                "price_per_unit"
            ]
        ]
        .drop_duplicates("product")
        .rename(
            columns={
                "price_per_unit":
                    "current_price"
            }
        )
    )


    forecast = forecast.merge(
        current_prices,
        on="product",
        how="left"
    )


    # ============================================================
    # 14. CALCULATE RECOMMENDED PRICE
    # ============================================================
    #
    # We use the median historical price observed inside the
    # selected sales + margin regime.
    #
    # This is preferable to using the average because it is less
    # sensitive to extreme historical prices.
    # ============================================================

    forecast["recommended_price_raw"] = (
        forecast["median_price"]
    )


    # ============================================================
    # 15. MINIMUM MARGIN GUARDRAIL
    # ============================================================
    #
    # If recommended price produces less than the required margin,
    # raise it to the minimum economically acceptable price.
    #
    # Gross margin:
    #
    #     (P - COGS) / P >= MIN_GROSS_MARGIN
    #
    # Therefore:
    #
    #     P >= COGS / (1 - MIN_GROSS_MARGIN)
    #
    # ============================================================

    current_cogs = (
        historical[
            historical["week"] == TRAIN_END
        ][
            [
                "product",
                "cost_of_goods_sold_cogs"
            ]
        ]
        .drop_duplicates("product")
        .rename(
            columns={
                "cost_of_goods_sold_cogs":
                    "current_cogs"
            }
        )
    )


    forecast = forecast.merge(
        current_cogs,
        on="product",
        how="left"
    )


    forecast["minimum_price"] = (
        forecast["current_cogs"]
        /
        (1 - MIN_GROSS_MARGIN)
    )


    forecast["recommended_price_margin_guardrail"] = (
        np.maximum(
            forecast["recommended_price_raw"],
            forecast["minimum_price"]
        )
    )


    # ============================================================
    # 16. MAXIMUM PRICE MOVEMENT GUARDRAIL
    # ============================================================
    #
    # Example:
    #
    # Current price = €100
    # Max movement = 5%
    #
    # Allowed:
    #
    # €95 -> €105
    # ============================================================

    forecast["minimum_allowed_price"] = (
        forecast["current_price"]
        * (1 - MAX_PRICE_CHANGE)
    )

    forecast["maximum_allowed_price"] = (
        forecast["current_price"]
        * (1 + MAX_PRICE_CHANGE)
    )


    forecast["recommended_price"] = (
        forecast[
            "recommended_price_margin_guardrail"
        ]
        .clip(
            lower=forecast[
                "minimum_allowed_price"
            ],
            upper=forecast[
                "maximum_allowed_price"
            ]
        )
    )


    # ============================================================
    # 17. CALCULATE PRICE CHANGE
    # ============================================================

    forecast["price_change_pct"] = (
        (
            forecast["recommended_price"]
            /
            forecast["current_price"]
        )
        - 1
    )

    forecast["strategy"] = (
    forecast
    .apply(
        strategy_description,
        axis=1
    )
)


    # ============================================================
    # 19. ADD INVENTORY SIGNAL
    # ============================================================
    #
    # Inventory is used as a guardrail / business signal.
    #
    # We use current inventory from week 234.
    # ============================================================

    current_inventory = (
        historical[
            historical["week"] == TRAIN_END
        ][
            [
                "product",
                "inventory_level"
            ]
        ]
        .drop_duplicates("product")
        .rename(
            columns={
                "inventory_level":
                    "current_inventory"
            }
        )
    )


    forecast = forecast.merge(
        current_inventory,
        on="product",
        how="left"
    )


    # ============================================================
    # 20. INVENTORY COVERAGE
    # ============================================================

    forecast["inventory_weeks"] = (
        forecast["current_inventory"]
        /
        forecast["predicted_sales"].replace(
            0,
            np.nan
        )
    )


    forecast["inventory_action"] = (
    forecast
    .apply(
        inventory_action,
        axis=1
    )
    )


    
    forecast["final_price_raw"] = (
        forecast
        .apply(
            apply_inventory_rule,
            axis=1
        )
    )


    # ============================================================
    # 23. RE-APPLY ALL PRICE GUARDRAILS
    # ============================================================

    forecast["final_price"] = (
        forecast["final_price_raw"]
        .clip(
            lower=forecast["minimum_price"]
        )
    )


    # Maximum weekly movement
    forecast["final_price"] = (
        forecast["final_price"]
        .clip(
            lower=forecast["minimum_allowed_price"],
            upper=forecast["maximum_allowed_price"]
        )
    )


    # ============================================================
    # 24. FINAL PRICE CHANGE
    # ============================================================

    forecast["final_price_change_pct"] = (
        (
            forecast["final_price"]
            /
            forecast["current_price"]
        )
        - 1
    ) * 100


    # ============================================================
    # 25. FINAL OUTPUT
    # ============================================================

    pricing_output = forecast[
        [
            "week",
            "product",
            "predicted_sales",

            "sales_quartile",

            "margin_quartile",

            "observations",

            "current_price",

            "median_price",
            "min_price",
            "max_price",

            "median_margin",
            "avg_margin",

            "avg_revenue",
            "avg_profit",

            "current_cogs",
            "minimum_price",

            "current_inventory",
            "inventory_weeks",
            "inventory_action",

            "recommended_price",

            "final_price",

            "final_price_change_pct",

            "strategy"
        ]
    ].sort_values(
        ["product", "week"]
    )

    # ============================================================
    # 26. DISPLAY RESULTS
    # ============================================================

    print("\n")
    print("=" * 100)
    print("DYNAMIC PRICING RECOMMENDATIONS")
    print("=" * 100)

    print(
        pricing_output.to_string(
            index=False,
            float_format=lambda x: f"{x:,.3f}"
        )
    )

    # ============================================================
    # 27. STRATEGY SUMMARY
    # ============================================================

    print("\n")
    print("=" * 100)
    print("HISTORICAL PRICING STRATEGIES")
    print("=" * 100)

    print(
        best_strategies[
            [
                "product",
                "sales_quartile",
                "margin_quartile",
                "observations",
                "median_price",
                "median_margin",
                "avg_revenue",
                "avg_profit"
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:,.3f}"
        )
    )

    # ============================================================
    # 28. SAVE RESULTS
    # ============================================================

    pricing_output.to_csv(
        "dynamic_pricing_recommendations.csv",
        index=False
    )

    best_strategies.to_csv(
        "pricing_strategy_table.csv",
        index=False
    )


    print("\nSaved:")
    print("  dynamic_pricing_recommendations.csv")
    print("  pricing_strategy_table.csv")







# ============================================================
# 22. OPTIONAL INVENTORY PRICE ADJUSTMENT
# ============================================================
#
# We keep this conservative.
#
# CRITICAL / LOW stock:
#     don't discount below the historical strategy
#
# HIGH stock:
#     allow a small additional discount if demand is weak
#
# ============================================================

def apply_inventory_rule(row):

    price = row["recommended_price"]

    action = row["inventory_action"]

    sales_q = row["sales_quartile"]

    # Critical shortage:
    # don't reduce price further
    if action == "CRITICAL_LOW_STOCK":
        return max(
            price,
            row["current_price"]
        )

    # High stock + low demand:
    # modest discount
    if (
        action == "HIGH_STOCK"
        and sales_q == "Q1_Low"
    ):
        return price * 0.97

    return price



# ============================================================
# 21. INVENTORY-BASED OVERRIDE
# ============================================================
#
# We don't let the historical strategy blindly discount
# a product that has critically low inventory.
#
# Likewise, high inventory + weak demand can justify
# additional downward pricing pressure.
# ============================================================

def inventory_action(row):

    inventory_weeks = row["inventory_weeks"]

    if pd.isna(inventory_weeks):
        return "No inventory signal"

    if inventory_weeks < 1:
        return "CRITICAL_LOW_STOCK"

    elif inventory_weeks < 2:
        return "LOW_STOCK"

    elif inventory_weeks > 8:
        return "HIGH_STOCK"

    else:
        return "NORMAL_STOCK"





    

# ============================================================
# 18. STRATEGY DESCRIPTION
# ============================================================

def strategy_description(row):

    sales_q = row["sales_quartile"]
    margin_q = row["margin_quartile"]

    if pd.isna(sales_q):
        return "No sales forecast"

    if pd.isna(margin_q):
        return "Insufficient historical pricing data"

    return (
        f"{sales_q} demand / "
        f"{margin_q} margin"
    )






# ============================================================
# 11. FUNCTION TO ASSIGN FORECAST SALES QUARTILE
# ============================================================

def determine_sales_quartile(row):

    sales = row["predicted_sales"]

    if pd.isna(sales):
        return np.nan

    if sales <= row["sales_q25"]:
        return "Q1_Low"

    elif sales <= row["sales_q50"]:
        return "Q2"

    elif sales <= row["sales_q75"]:
        return "Q3"

    else:
        return "Q4_High"







# ============================================================
# 6. ASSIGN MARGIN QUARTILE WITHIN SALES REGIME
# ============================================================

def assign_margin_quartile(series):
    try:
        return pd.qcut(
            series,
            q=4,
            labels=[
                "Q1_LowMargin",
                "Q2",
                "Q3",
                "Q4_HighMargin"
            ],
            duplicates="drop"
        )
    except ValueError:
        return pd.Series(
            "Unknown",
            index=series.index,
            dtype="object"
        )




# ============================================================
# 5. ASSIGN SALES QUARTILE PER PRODUCT
# ============================================================

def assign_sales_quartile(series):
    try:
        return pd.qcut(
            series,
            q=4,
            labels=[
                "Q1_Low",
                "Q2",
                "Q3",
                "Q4_High"
            ],
            duplicates="drop"
        )
    except ValueError:
        return pd.Series(
            "Unknown",
            index=series.index,
            dtype="object"
        )






if __name__ == '__main__':
    main()