import numpy as np
import pandas as pd

from statsmodels.tsa.ar_model import AutoReg
from sqlalchemy import create_engine
from sklearn.decomposition import PCA
from sklearn.metrics import mean_squared_error, mean_absolute_error
from statsmodels.tsa.api import VAR

from dotenv import load_dotenv
import os



def main():

    
    load_dotenv()

    USER_NAME = os.getenv("USER_NAME")
    PASSWORD = os.getenv("PASSWORD")
    HOST = os.getenv("HOST")
    PORT = os.getenv("PORT")
    DB_NAME = os.getenv("DB_NAME")

    DATABASE_URL = rf"postgresql+psycopg2://{USER_NAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL)

    sql = 'SELECT * FROM warehouse.vw_warehouse_sales; '
    df = pd.read_sql(sql, con=engine)
    print(df.shape)
    df.head()


    df["week"] = pd.to_numeric(df["week"])
    df["sales_units"] = pd.to_numeric(df["sales_units"])
    df["demand_forecast"] = pd.to_numeric(df["demand_forecast"])
    df["inventory_level"] = pd.to_numeric(df["inventory_level"])

    df = df.sort_values(["week", "product"]).reset_index(drop=True)


    # ============================================================
    # 3. BASIC VALIDATION
    # ============================================================

    products = sorted(df["product"].unique())

    print(f"Products: {len(products)}")
    print(f"Weeks: {df['week'].min()} -> {df['week'].max()}")
    print(f"Rows: {len(df):,}")

    if len(products) != 30:
        print("WARNING: expected 30 products.")


    # ============================================================
    # 4. STOCKOUT IDENTIFICATION
    # ============================================================
    #
    # A stockout is defined here as:
    #
    # inventory <= 0 AND sales_units == 0
    #
    # This does NOT prove lost demand. It is simply the operational
    # definition we are using for adjustment.
    # ============================================================

    df["stockout"] = (
        (df["inventory_level"] <= 0) &
        (df["sales_units"] <= 0)
    )

    print("\nStockout observations:")
    print(df["stockout"].value_counts())



    # ============================================================
    # 5. PRODUCT MEDIANS
    # ============================================================
    #
    # Used only as fallback when demand_forecast is unavailable.
    # Calculate from non-stockout observations so the median isn't
    # distorted by periods where inventory was zero.
    # ============================================================

    product_medians = (
        df.loc[~df["stockout"]]
        .groupby("product")["sales_units"]
        .median()
    )


    # ============================================================
    # 6. CREATE STOCKOUT-ADJUSTED SALES
    # ============================================================
    #
    # IMPORTANT:
    # Actual sales remain untouched.
    #
    # For training:
    #   stockout + demand_forecast available -> demand_forecast
    #   stockout + demand_forecast missing    -> product median
    #   otherwise                             -> actual sales
    #
    # This attempts to estimate underlying demand rather than
    # observed constrained sales.
    # ============================================================

    df["sales_adjusted"] = df["sales_units"]

    stockout_with_forecast = (
        df["stockout"] &
        df["demand_forecast"].notna()
    )

    df.loc[stockout_with_forecast, "sales_adjusted"] = (
        df.loc[stockout_with_forecast, "demand_forecast"]
    )

    stockout_without_forecast = (
        df["stockout"] &
        # df["demand_forecast"].isna()
        (df["modified_row"]==True)
    )

    df.loc[stockout_without_forecast, "sales_adjusted"] = (
        df.loc[stockout_without_forecast, "product"]
        .map(product_medians)
    )

    print(
        "\nStockouts replaced by demand forecast:",
        stockout_with_forecast.sum()
    )

    print(
        "Stockouts replaced by product median:",
        stockout_without_forecast.sum()
    )


    # ============================================================
    # 7. TRAIN / TEST SPLIT
    # ============================================================

    TRAIN_END = 234
    TEST_START = 235
    TEST_END = 260

    train_df = df[df["week"] <= TRAIN_END].copy()
    test_df = df[
        (df["week"] >= TEST_START) &
        (df["week"] <= TEST_END)
    ].copy()


    # ============================================================
    # 8. BUILD WEEK x PRODUCT MATRIX
    # ============================================================
    #
    # Use adjusted sales for TRAINING only.
    #
    # For the future/test period we retain ACTUAL sales for
    # evaluation.
    # ============================================================

    train_matrix = (
        train_df
        .pivot_table(
            index="week",
            columns="product",
            values="sales_adjusted",
            aggfunc="sum"
        )
        .reindex(columns=products)
        .sort_index()
    )

    test_matrix = (
        test_df
        .pivot_table(
            index="week",
            columns="product",
            values="sales_units",
            aggfunc="sum"
        )
        .reindex(columns=products)
        .sort_index()
    )

        # Check completeness
    if train_matrix.isna().any().any():
        print("\nWARNING: missing product/week combinations in training data.")

    if test_matrix.isna().any().any():
        print("WARNING: missing product/week combinations in test data.")

    # ============================================================
    # 9. HANDLE MISSING PRODUCT-WEEK RECORDS
    # ============================================================
    #
    # Only do this if an absent row really means zero sales in
    # your warehouse. If an absent row means missing data, don't
    # perform this fill.
    # ============================================================

    train_matrix = train_matrix.fillna(0)
    test_matrix = test_matrix.fillna(0)


    # ============================================================
    # 10. WEEKLY TOTAL SALES
    # ============================================================

    train_total = train_matrix.sum(axis=1)
    test_total = test_matrix.sum(axis=1)

    if (train_total <= 0).any():
        zero_weeks = train_total[train_total <= 0].index.tolist()
        raise ValueError(
            f"Training contains weeks with zero total sales: {zero_weeks}"
        )


    # ============================================================
    # 11. CONVERT SALES -> WEEKLY PRODUCT SHARES
    # ============================================================

    train_shares = train_matrix.div(train_total, axis=0)

    print("\nShare check:")
    print(
        train_shares.sum(axis=1).describe()
    )

    # ============================================================
    # 12. PCA
    # ============================================================
    #
    # We reduce 30 product shares to a small number of latent
    # components.
    #
    # 5-8 components is a sensible starting range.
    # ============================================================

    N_COMPONENTS = 6

    pca = PCA(
        n_components=N_COMPONENTS,
        random_state=42
    )

    train_pca = pca.fit_transform(train_shares)

    explained = pca.explained_variance_ratio_

    print("\nPCA explained variance:")
    for i, value in enumerate(explained, start=1):
        print(f"PC{i}: {value:.4f}")

    print(
        f"Cumulative explained variance: "
        f"{explained.cumsum()[-1]:.4f}"
    )




    # ============================================================
    # 13. FORECAST PCA COMPONENTS WITH VAR
    # ============================================================
    #
    # Each row = one week
    # Each column = one PCA component.
    #
    # VAR captures relationships between the latent components.
    # ============================================================

    pca_df = pd.DataFrame(
        train_pca,
        index=train_shares.index,
        columns=[
            f"PC{i+1}"
            for i in range(N_COMPONENTS)
        ]
    )

    # Keep lag relatively small because we only have 234 weeks.
    MAX_LAGS = 8

    var_model = VAR(pca_df)

    var_result = var_model.fit(
        maxlags=MAX_LAGS,
        ic="aic",
        trend="c"
    )

    print("\nSelected VAR lag:")
    print(var_result.k_ar)

    print("\nVAR summary:")
    print(var_result.summary())


    # ============================================================
    # 14. FORECAST PCA COMPONENTS
    # ============================================================

    forecast_horizon = TEST_END - TRAIN_END

    last_values = pca_df.values[-var_result.k_ar:]

    pca_forecast = var_result.forecast(
        y=last_values,
        steps=forecast_horizon
    )

    forecast_weeks = np.arange(
        TEST_START,
        TEST_END + 1
    )

    pca_forecast_df = pd.DataFrame(
        pca_forecast,
        index=forecast_weeks,
        columns=pca_df.columns
    )



    # ============================================================
    # 15. RECONSTRUCT PRODUCT SHARES
    # ============================================================

    forecast_shares_raw = pca.inverse_transform(
        pca_forecast
    )

    forecast_shares = pd.DataFrame(
        forecast_shares_raw,
        index=forecast_weeks,
        columns=products
    )


    # ============================================================
    # 16. PROJECT BACK TO VALID SHARES
    # ============================================================
    #
    # PCA reconstruction can produce:
    #
    #   negative shares
    #   rows that don't sum exactly to 1
    #
    # We therefore:
    #
    #   1. clip negative values to zero
    #   2. normalize each week to sum to one
    #
    # This is a practical projection back onto the simplex.
    # ============================================================

    forecast_shares = forecast_shares.clip(lower=0)

    row_sums = forecast_shares.sum(axis=1)

    # Protect against a pathological all-zero row.
    for week in forecast_shares.index:
        if row_sums.loc[week] <= 0:
            forecast_shares.loc[week] = train_shares.mean(axis=0)

    forecast_shares = forecast_shares.div(
        forecast_shares.sum(axis=1),
        axis=0
    )


    print("\nForecast share check:")
    print(forecast_shares.sum(axis=1))



    # 17. FORECAST TOTAL SALES

    
    # Use a simple sequential index so statsmodels has a supported #
    #  time-series index.

    log_total = pd.Series( np.log1p(train_total.values), index=pd.RangeIndex(start=0, stop=len(train_total)) )

    total_model = AutoReg( log_total, lags=13, trend="ct", seasonal=False ).fit()

    # Forecast exactly 26 future observations
    log_total_forecast = total_model.forecast( steps=forecast_horizon )
    total_forecast = np.expm1( np.asarray(log_total_forecast) )
    total_forecast = pd.Series( total_forecast, index=forecast_weeks, name="total_sales_forecast" )
    # Make sure forecasts cannot become negative
    total_forecast = total_forecast.clip(lower=0)

    print("\nTotal sales forecast:") 
    print(total_forecast)

    # ============================================================
    # 18. OPTIONAL: SEASONAL NAIVE TOTAL FORECAST
    # ============================================================
    #
    # Useful as a sanity-check baseline.
    # ============================================================

    seasonal_total_forecast = pd.Series(
        [
            train_total.loc[week - 26]
            for week in forecast_weeks
        ],
        index=forecast_weeks,
        name="seasonal_naive_total"
    )


    # ============================================================
    # 19. CONVERT SHARE FORECAST -> PRODUCT SALES FORECAST
    # ============================================================

    sales_forecast = forecast_shares.mul(
        total_forecast,
        axis=0
    )

    sales_forecast.columns = products

    sales_forecast.index.name = "week"



    # ============================================================
    # 20. ROUND / NON-NEGATIVE
    # ============================================================

    sales_forecast = sales_forecast.clip(lower=0)


    # ============================================================
    # 21. ACTUAL TEST SALES
    # ============================================================

    actual_sales = test_matrix.loc[
        forecast_weeks,
        products
    ]


    # ============================================================
    # 22. EVALUATION
    # ============================================================

    y_true = actual_sales.values.flatten()
    y_pred = sales_forecast.values.flatten()


    rmse = np.sqrt(
        mean_squared_error(y_true, y_pred)
    )

    mae = mean_absolute_error(
        y_true,
        y_pred
    )

    smape = (
        100
        * np.mean(
            2 * np.abs(y_pred - y_true)
            /
            (
                np.abs(y_true) +
                np.abs(y_pred) +
                1e-8
            )
        )
    )


    print("\n====================================")
    print("PCA SHARE MODEL RESULTS")
    print("====================================")
    print(f"RMSE : {rmse:.4f}")
    print(f"MAE  : {mae:.4f}")
    print(f"sMAPE: {smape:.2f}%")



    # ============================================================
    # 23. COMPARE AGAINST DEMAND FORECAST
    # ============================================================

    demand_test = (
        test_df
        .pivot_table(
            index="week",
            columns="product",
            values="demand_forecast",
            aggfunc="sum"
        )
        .reindex(
            index=forecast_weeks,
            columns=products
        )
    )

    if not demand_test.isna().all().all():

        demand_true = actual_sales.values.flatten()
        demand_pred = demand_test.values.flatten()

        valid = np.isfinite(demand_pred)

        demand_rmse = np.sqrt(
            mean_squared_error(
                demand_true[valid],
                demand_pred[valid]
            )
        )

        demand_mae = mean_absolute_error(
            demand_true[valid],
            demand_pred[valid]
        )

        demand_smape = (
            100
            * np.mean(
                2 * np.abs(
                    demand_pred[valid] -
                    demand_true[valid]
                )
                /
                (
                    np.abs(demand_true[valid]) +
                    np.abs(demand_pred[valid]) +
                    1e-8
                )
            )
        )

        print("\n====================================")
        print("DEMAND FORECAST BASELINE")
        print("====================================")
        print(f"RMSE : {demand_rmse:.4f}")
        print(f"MAE  : {demand_mae:.4f}")
        print(f"sMAPE: {demand_smape:.2f}%")
        print(f"Coverage: {valid.mean():.2%}")




    
    # ============================================================
    # 24. PRODUCT-LEVEL RESULTS
    # ============================================================

    product_results = []

    for product in products:

        actual = actual_sales[product].values
        predicted = sales_forecast[product].values

        product_rmse = np.sqrt(
            mean_squared_error(actual, predicted)
        )

        product_mae = mean_absolute_error(
            actual,
            predicted
        )

        product_smape = (
            100
            * np.mean(
                2 * np.abs(predicted - actual)
                /
                (
                    np.abs(actual) +
                    np.abs(predicted) +
                    1e-8
                )
            )
        )

        product_results.append({
            "product": product,
            "rmse": product_rmse,
            "mae": product_mae,
            "smape": product_smape
        })


    product_results = pd.DataFrame(product_results)

    product_results = product_results.sort_values(
        "rmse",
        ascending=False
    )

    print("\nProduct-level results:")
    print(product_results.to_string(index=False))



    # ============================================================
    # 25. TOTAL SALES EVALUATION
    # ============================================================

    actual_total = test_total.loc[
        forecast_weeks
    ]

    total_rmse = np.sqrt(
        mean_squared_error(
            actual_total,
            total_forecast
        )
    )

    seasonal_rmse = np.sqrt(
        mean_squared_error(
            actual_total,
            seasonal_total_forecast
        )
    )

    print("\n====================================")
    print("TOTAL SALES FORECAST")
    print("====================================")
    print(f"AR total RMSE       : {total_rmse:.4f}")
    print(f"Seasonal naive RMSE : {seasonal_rmse:.4f}")



    # ============================================================
    # 26. SHARE FORECAST EVALUATION
    # ============================================================

    actual_test_total = actual_sales.sum(axis=1)

    actual_test_shares = actual_sales.div(
        actual_test_total.replace(0, np.nan),
        axis=0
    )

    share_rmse = np.sqrt(
        np.mean(
            (
                actual_test_shares.values -
                forecast_shares.values
            ) ** 2
        )
    )

    print("\n====================================")
    print("SHARE FORECAST")
    print("====================================")
    print(f"Share RMSE: {share_rmse:.8f}")



    # ============================================================
    # 27. SAVE LOCAL CSV FILES
    # ============================================================

    sales_forecast_long = (
        sales_forecast
        .reset_index()
        .melt(
            id_vars="week",
            var_name="product",
            value_name="predicted_sales"
        )
    )

    sales_forecast_long.to_csv(
        "pca_sales_forecast.csv",
        index=False
    )

    product_results.to_csv(
        "pca_product_results.csv",
        index=False
    )

    forecast_shares.reset_index().to_csv(
        "pca_forecast_shares.csv",
        index=False
    )

    print("\nSaved:")
    print("  pca_sales_forecast.csv")
    print("  pca_product_results.csv")
    print("  pca_forecast_shares.csv")





if __name__ == '__main__':
    main()