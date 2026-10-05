import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

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

    df["week"] = pd.to_numeric(df["week"])
    df["sales_units"] = pd.to_numeric(df["sales_units"])
    df["demand_forecast"] = pd.to_numeric(df["demand_forecast"])

    df["start_date"] = pd.to_datetime(df["start_date"])

    df = df.sort_values(
        ["product", "week"]
    ).reset_index(drop=True)



    # ============================================================
    # 4. TRAIN / TEST SPLIT
    # ============================================================

    TRAIN_END = 234
    TEST_START = 235
    TEST_END = 260

    train = df[
        df["week"] <= TRAIN_END
    ].copy()

    test = df[
        (df["week"] >= TEST_START) &
        (df["week"] <= TEST_END)
    ].copy()


    print("Number of products:", df["product"].nunique())
    print("Training weeks:", train["week"].min(), "-", train["week"].max())
    print("Test weeks:", test["week"].min(), "-", test["week"].max())
    print("Training rows:", len(train))
    print("Test rows:", len(test))

    # ============================================================
    # 6. CREATE FEATURES
    # ============================================================

    featured = create_features(df)
    feature_columns = [
    "lag_1",
    "lag_2",
    "lag_4",
    "lag_8",
    "lag_13",
    "lag_26",

    "rolling_mean_4",
    "rolling_mean_8",
    "rolling_mean_13",
    "rolling_mean_26",
    "rolling_std_8",

    "ewm_8",

    "week_sin",
    "week_cos",

    "product_code",
    ]

    model_train = featured[
    featured["week"] <= TRAIN_END
    ].copy()

    model_train = model_train.dropna(
        subset=feature_columns + ["sales_units"]
    )


    X_train = model_train[
        feature_columns
    ]

    y_train = model_train[
        "sales_units"
    ]


    print(
        "Rows used for model training:",
        len(model_train)
    )

    model = RandomForestRegressor(
    n_estimators=500,
    max_depth=12,
    min_samples_leaf=3,
    random_state=42,
    n_jobs=-1
    )

    model.fit(
        X_train,
        y_train
    )
    forecast_history = df[
        df["week"] <= TRAIN_END
    ].copy()

    forecast_rows = []

    for week in range(TEST_START, TEST_END + 1):

        current_rows = []

        for product in df["product"].unique():

            product_history = forecast_history[
                forecast_history["product"] == product
            ].sort_values("week").copy()

            sales_history = (
                product_history["sales_units"]
                .dropna()
                .tolist()
            )

            # ----------------------------------------------------
            # Create one future row
            # ----------------------------------------------------

            row = {
                "week": week,
                "product": product,
            }


            # ----------------------------------------------------
            # Lag features
            # ----------------------------------------------------

            row["lag_1"] = (
                sales_history[-1]
                if len(sales_history) >= 1
                else np.nan
            )

            row["lag_2"] = (
                sales_history[-2]
                if len(sales_history) >= 2
                else np.nan
            )

            row["lag_4"] = (
                sales_history[-4]
                if len(sales_history) >= 4
                else np.nan
            )

            row["lag_8"] = (
                sales_history[-8]
                if len(sales_history) >= 8
                else np.nan
            )

            row["lag_13"] = (
                sales_history[-13]
                if len(sales_history) >= 13
                else np.nan
            )

            row["lag_26"] = (
                sales_history[-26]
                if len(sales_history) >= 26
                else np.nan
            )


            # ----------------------------------------------------
            # Rolling features
            # ----------------------------------------------------

            row["rolling_mean_4"] = np.mean(
                sales_history[-4:]
            )

            row["rolling_mean_8"] = np.mean(
                sales_history[-8:]
            )

            row["rolling_mean_13"] = np.mean(
                sales_history[-13:]
            )

            row["rolling_mean_26"] = np.mean(
                sales_history[-26:]
            )

            row["rolling_std_8"] = np.std(
                sales_history[-8:],
                ddof=1
            )


            # ----------------------------------------------------
            # Exponential moving average
            # ----------------------------------------------------

            row["ewm_8"] = (
                pd.Series(sales_history)
                .ewm(
                    span=8,
                    adjust=False
                )
                .mean()
                .iloc[-1]
            )


            # ----------------------------------------------------
            # Seasonal features
            # ----------------------------------------------------

            row["week_sin"] = np.sin(
                2 * np.pi * week / 52
            )

            row["week_cos"] = np.cos(
                2 * np.pi * week / 52
            )


            # ----------------------------------------------------
            # Product encoding
            # ----------------------------------------------------

            product_codes = (
                df["product"]
                .astype("category")
                .cat
            )

            row["product_code"] = (
                product_codes
                .categories
                .get_loc(product)
            )


            current_rows.append(row)


        future_features = pd.DataFrame(
            current_rows
        )


        # --------------------------------------------------------
        # Predict this week
        # --------------------------------------------------------

        X_future = future_features[
            feature_columns
        ]

        predictions = model.predict(
            X_future
        )

        future_features["predicted_sales_units"] = (
            predictions
        )


        # --------------------------------------------------------
        # Add predictions to history
        #
        # This is what makes the forecast recursive.
        # For week 236, lag_1 can therefore use our prediction
        # for week 235.
        # --------------------------------------------------------

        new_history = future_features[
            [
                "week",
                "product",
                "predicted_sales_units"
            ]
        ].rename(
            columns={
                "predicted_sales_units":
                    "sales_units"
            }
        )

        forecast_history = pd.concat(
            [
                forecast_history,
                new_history
            ],
            ignore_index=True
        )


        forecast_rows.append(
            future_features
        )


    # Combine all 26 forecast weeks
    forecast = pd.concat(
        forecast_rows,
        ignore_index=True
    )


    # ============================================================
    # 11. GET ACTUAL VALUES
    # ============================================================

    actuals = test[
        [
            "week",
            "product",
            "sales_units",
            "demand_forecast"
        ]
    ].copy()


    results = forecast.merge(
        actuals,
        on=["week", "product"],
        how="left"
    )


    # ============================================================
    # 12. BASELINE MODELS
    # ============================================================

    # ------------------------------------------------------------
    # A. Demand Forecast baseline
    # ------------------------------------------------------------

    results["baseline_demand_forecast"] = (
        results["demand_forecast"]
    )


    # ------------------------------------------------------------
    # B. Naive forecast
    #
    # Predict every future week using the final observed
    # sales value from week 234.
    # ------------------------------------------------------------

    last_sales = (
        train
        .sort_values("week")
        .groupby("product")["sales_units"]
        .last()
        .rename("last_sales")
    )

    results = results.merge(
        last_sales,
        on="product",
        how="left"
    )

    results["baseline_naive"] = (
        results["last_sales"]
    )


    # ------------------------------------------------------------
    # C. Seasonal naive
    #
    # Predict week t using sales from t-26.
    # ------------------------------------------------------------

    seasonal_lookup = df[
        ["product", "week", "sales_units"]
    ].copy()

    seasonal_lookup["week"] = (
        seasonal_lookup["week"] + 26
    )

    seasonal_lookup = seasonal_lookup.rename(
        columns={
            "sales_units":
                "baseline_seasonal_26"
        }
    )

    results = results.merge(
        seasonal_lookup[
            [
                "product",
                "week",
                "baseline_seasonal_26"
            ]
        ],
        on=["product", "week"],
        how="left"
    )



        
    models = {
        "Random Forest": "predicted_sales_units",
        "Demand Forecast": "baseline_demand_forecast",
        "Naive": "baseline_naive",
        "Seasonal Naive 26": "baseline_seasonal_26",
    }
    metrics = []
    for model_name, prediction_column in models.items():

        evaluation = results[
            [
                "sales_units",
                prediction_column
            ]
        ].dropna()

        actual = evaluation["sales_units"]
        predicted = evaluation[prediction_column]

        metrics.append(
            {
                "model": model_name,
                "RMSE": rmse(
                    actual,
                    predicted
                ),
                "MAE": mae(
                    actual,
                    predicted
                ),
                "sMAPE": smape(
                    actual,
                    predicted
                ),
            }
        )


    metrics_df = pd.DataFrame(
        metrics
    )


    # ============================================================
    # 15. DISPLAY OVERALL RESULTS
    # ============================================================

    print("\n")
    print("=" * 70)
    print("OVERALL FORECAST PERFORMANCE")
    print("=" * 70)

    print(
        metrics_df.to_string(
            index=False,
            float_format=lambda x: f"{x:,.3f}"
        )
    )


    # ============================================================
    # 16. METRICS BY PRODUCT
    # ============================================================

    product_metrics = []


    for product, product_data in results.groupby("product"):

        actual = product_data[
            "sales_units"
        ]

        for model_name, prediction_column in models.items():

            mask = (
                actual.notna() &
                product_data[
                    prediction_column
                ].notna()
            )

            actual_values = actual[mask]
            predicted_values = product_data.loc[
                mask,
                prediction_column
            ]

            product_metrics.append(
                {
                    "product": product,
                    "model": model_name,
                    "RMSE": rmse(
                        actual_values,
                        predicted_values
                    ),
                    "MAE": mae(
                        actual_values,
                        predicted_values
                    ),
                    "sMAPE": smape(
                        actual_values,
                        predicted_values
                    ),
                }
            )


    product_metrics_df = pd.DataFrame(
        product_metrics
    )


    # ============================================================
    # 17. SHOW PRODUCT-LEVEL RESULTS
    # ============================================================

    print("\n")
    print("=" * 70)
    print("PER-PRODUCT FORECAST PERFORMANCE")
    print("=" * 70)

    print(
        product_metrics_df.to_string(
            index=False,
            float_format=lambda x: f"{x:,.3f}"
        )
    )


    # ============================================================
    # 18. FORECAST OUTPUT
    # ============================================================

    forecast_output = results[
        [
            "week",
            "product",
            "sales_units",
            "demand_forecast",
            "predicted_sales_units",
            "baseline_naive",
            "baseline_seasonal_26",
        ]
    ].sort_values(
        ["product", "week"]
    )


    print("\n")
    print("=" * 70)
    print("FIRST FORECAST RESULTS")
    print("=" * 70)

    print(
        forecast_output.head(30).to_string(
            index=False
        )
    )


    # ============================================================
    # 19. OPTIONAL: SAVE RESULTS LOCALLY
    # ============================================================

    forecast_output.to_csv(
        "forecast_v1_results.csv",
        index=False
    )

    metrics_df.to_csv(
        "forecast_v1_metrics.csv",
        index=False
    )

    product_metrics_df.to_csv(
        "forecast_v1_metrics_by_product.csv",
        index=False
    )


    print("\nForecast v1 files saved:")
    print("  forecast_v1_results.csv")
    print("  forecast_v1_metrics.csv")
    print("  forecast_v1_metrics_by_product.csv")




# ============================================================
# 13. METRIC FUNCTIONS
# ============================================================

def rmse(actual, predicted):
    return np.sqrt(
        mean_squared_error(
            actual,
            predicted
        )
    )


def mae(actual, predicted):
    return mean_absolute_error(
        actual,
        predicted
    )


def smape(actual, predicted):
    actual = np.asarray(actual)
    predicted = np.asarray(predicted)

    denominator = (
        np.abs(actual) +
        np.abs(predicted)
    )

    mask = denominator != 0

    return (
        100 *
        np.mean(
            2 *
            np.abs(
                predicted[mask] -
                actual[mask]
            ) /
            denominator[mask]
        )
    )








# ============================================================
# 5. TIME-SERIES FEATURE ENGINEERING
# ============================================================

def create_features(data):
    """
    Create lag, rolling and calendar features.

    IMPORTANT:
    All lag/rolling features are based only on historical
    sales_units values.
    """

    data = data.copy()

    data = data.sort_values(
        ["product", "week"]
    )

    grouped = data.groupby(
        "product",
        group_keys=False
    )

    # --------------------------------------------------------
    # Lag features
    # --------------------------------------------------------

    lag_periods = [
        1,
        2,
        4,
        8,
        13,
        26
    ]

    for lag in lag_periods:

        data[f"lag_{lag}"] = grouped[
            "sales_units"
        ].shift(lag)


    # --------------------------------------------------------
    # Rolling features
    #
    # Shift first so the current week's sales are NOT used.
    # --------------------------------------------------------

    shifted_sales = grouped["sales_units"].shift(1)

    data["rolling_mean_4"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.rolling(4).mean()
        )
    )

    data["rolling_mean_8"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.rolling(8).mean()
        )
    )

    data["rolling_mean_13"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.rolling(13).mean()
        )
    )

    data["rolling_mean_26"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.rolling(26).mean()
        )
    )

    data["rolling_std_8"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.rolling(8).std()
        )
    )


    # --------------------------------------------------------
    # Exponentially weighted moving average
    # --------------------------------------------------------

    data["ewm_8"] = (
        shifted_sales
        .groupby(data["product"])
        .transform(
            lambda x: x.ewm(
                span=8,
                adjust=False
            ).mean()
        )
    )


    # --------------------------------------------------------
    # Calendar / seasonal features
    # --------------------------------------------------------

    data["week_sin"] = np.sin(
        2 * np.pi * data["week"] / 52
    )

    data["week_cos"] = np.cos(
        2 * np.pi * data["week"] / 52
    )


    # --------------------------------------------------------
    # Product encoding
    # --------------------------------------------------------

    data["product_code"] = (
        data["product"]
        .astype("category")
        .cat.codes
    )


    return data





if __name__=='__main__':
    main()