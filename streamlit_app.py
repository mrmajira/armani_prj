import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from sqlalchemy import create_engine, text

from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
load_dotenv()

USER_NAME = os.getenv("USER_NAME")
PASSWORD = os.getenv("PASSWORD")
HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = rf"postgresql+psycopg2://{USER_NAME}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"


def main():
    # engine = create_engine(DATABASE_URL)
    # sql = 'SELECT * FROM warehouse.vw_warehouse_sales; '
    # engine.dispose()
    # sales_df = pd.read_sql(sql, con=engine)
    # forecast_df = pd.read_csv('pca_sales_forecast.csv')

    
    # ============================================================
    # STREAMLIT CONFIGURATION
    # ============================================================

    st.set_page_config(
        page_title="Warehouse Sales & Forecast Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )



    # ============================================================
    # CUSTOM CSS
    # ============================================================

    st.markdown(
        """
        <style>
            .main {
                padding-top: 1rem;
            }

            .kpi-card {
                padding: 20px;
                border-radius: 10px;
                border: 1px solid #ddd;
                background-color: #ffffff;
                text-align: center;
                box-shadow: 0px 2px 6px rgba(0,0,0,0.08);
            }

            .kpi-title {
                font-size: 14px;
                color: #666;
                margin-bottom: 5px;
            }

            .kpi-value {
                font-size: 28px;
                font-weight: bold;
            }

            .risk-high {
                background-color: #ffebee;
                padding: 12px;
                border-radius: 8px;
                border-left: 5px solid #d32f2f;
            }

            .risk-medium {
                background-color: #fff8e1;
                padding: 12px;
                border-radius: 8px;
                border-left: 5px solid #f9a825;
            }

            .risk-low {
                background-color: #e8f5e9;
                padding: 12px;
                border-radius: 8px;
                border-left: 5px solid #388e3c;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ============================================================
    # LOAD DATA
    # ============================================================

    try:

        sales_df = load_sales_data()
        forecast_df = load_forecast()

    except Exception as e:

        st.error(f"Error loading data: {e}")
        st.stop()

    
    # ============================================================
    # DATA CLEANING
    # ============================================================

    sales_df["start_date"] = pd.to_datetime(
        sales_df["start_date"],
        errors="coerce"
    )

    sales_df["product"] = (
        sales_df["product"]
        .astype(str)
        .str.strip()
    )

    numeric_columns = [
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
        "operating_cost"
    ]

    for column in numeric_columns:

        if column in sales_df.columns:

            sales_df[column] = pd.to_numeric(
                sales_df[column],
                errors="coerce"
            )
    
    # ============================================================
    # SIDEBAR FILTERS
    # ============================================================

    st.sidebar.title("Dashboard Filters")

    products = sorted(
        sales_df["product"]
        .dropna()
        .unique()
    )

    selected_products = st.sidebar.multiselect(
        "Products",
        products,
        default=products
    )

    min_date = sales_df["start_date"].min()
    max_date = sales_df["start_date"].max()

    date_range = st.sidebar.date_input(
        "Historical Date Range",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date()
    )

    if len(date_range) == 2:

        start_date = pd.Timestamp(date_range[0])
        end_date = pd.Timestamp(date_range[1])

    else:

        start_date = min_date
        end_date = max_date


    
    # ============================================================
    # APPLY FILTERS
    # ============================================================

    filtered_sales = sales_df[
        (sales_df["product"].isin(selected_products))
        &
        (sales_df["start_date"] >= start_date)
        &
        (sales_df["start_date"] <= end_date)
    ].copy()

    filtered_forecast = forecast_df[
        forecast_df["product"].isin(selected_products)
    ].copy()


    # ============================================================
    # HEADER
    # ============================================================

    st.title(
        "📊 Warehouse Sales, Inventory & Demand Forecast Dashboard"
    )

    st.markdown(
        """
        **Business objective:** evaluate commercial profitability,
        optimize inventory and warehouse efficiency, and identify
        demand and operational risks.
        """
    )

    # ============================================================
    # KPI SECTION
    # ============================================================

    st.header("Executive KPIs")

    kpis = calculate_kpis(filtered_sales)

    cols = st.columns(7)

    with cols[0]:
        kpi_card(
            "Revenue",
            money(kpis["revenue"]),
            "Historical period"
        )

    with cols[1]:
        kpi_card(
            "Gross Profit",
            money(kpis["gross_profit"]),
            "Historical period"
        )

    with cols[2]:
        kpi_card(
            "Operating Profit",
            money(kpis["operating_profit"]),
            "Historical period"
        )

    with cols[3]:
        kpi_card(
            "Gross Profit Margin",
            percentage(kpis["gross_profit_margin"]),
            "Profitability"
        )

    with cols[4]:
        kpi_card(
            "Revenue Growth",
            percentage(kpis["revenue_growth"]),
            "Latest week vs previous"
        )

    with cols[5]:
        kpi_card(
            "Inventory Turnover",
            number(kpis["inventory_turnover"]),
            "COGS / Avg inventory"
        )

    with cols[6]:
        kpi_card(
            "DSI",
            number(kpis["dsi"]),
            "Days of inventory"
        )



        
    # ============================================================
    # FINANCIAL PERFORMANCE
    # ============================================================

    st.header("1. Financial Performance")

    financial_col1, financial_col2 = st.columns(2)


    # Revenue trend
    with financial_col1:

        revenue_weekly = (
            filtered_sales
            .groupby("start_date", as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                gross_profit=("gross_profit", "sum"),
                operating_profit=("operating_profit", "sum")
            )
            .sort_values("start_date")
        )

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=revenue_weekly["start_date"],
                y=revenue_weekly["revenue"],
                mode="lines+markers",
                name="Revenue"
            )
        )

        fig.add_trace(
            go.Scatter(
                x=revenue_weekly["start_date"],
                y=revenue_weekly["gross_profit"],
                mode="lines",
                name="Gross Profit"
            )
        )

        fig.add_trace(
            go.Scatter(
                x=revenue_weekly["start_date"],
                y=revenue_weekly["operating_profit"],
                mode="lines",
                name="Operating Profit"
            )
        )

        fig.update_layout(
            title="Revenue & Profitability Trend",
            xaxis_title="Date",
            yaxis_title="Amount",
            hovermode="x unified"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


    # Gross margin
    with financial_col2:

        margin_df = (
            filtered_sales
            .groupby("start_date", as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                gross_profit=("gross_profit", "sum")
            )
        )

        margin_df["gross_profit_margin"] = np.where(
            margin_df["revenue"] != 0,
            margin_df["gross_profit"]
            / margin_df["revenue"] * 100,
            np.nan
        )

        fig = px.line(
            margin_df,
            x="start_date",
            y="gross_profit_margin",
            markers=True,
            title="Gross Profit Margin Trend"
        )

        fig.update_yaxes(
            title="Gross Profit Margin (%)"
        )

        fig.update_xaxes(
            title="Date"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


        
    # ============================================================
    # PRODUCT PROFITABILITY
    # ============================================================

    st.subheader("Product Profitability")

    financial_risk = calculate_financial_risk(
        filtered_sales
    )

    display_financial = financial_risk.copy()

    display_financial["revenue"] = (
        display_financial["revenue"]
        .round(2)
    )

    display_financial["gross_profit"] = (
        display_financial["gross_profit"]
        .round(2)
    )

    display_financial["operating_profit"] = (
        display_financial["operating_profit"]
        .round(2)
    )

    display_financial["gross_profit_margin"] = (
        display_financial["gross_profit_margin"]
        .round(2)
    )

    st.dataframe(
        display_financial,
        use_container_width=True,
        hide_index=True
    )



    
    # ============================================================
    # OPERATIONAL PERFORMANCE
    # ============================================================

    st.header("2. Operational Performance")

    operational_col1, operational_col2 = st.columns(2)


    # Inventory trend
    with operational_col1:

        inventory_df = (
            filtered_sales
            .groupby("start_date", as_index=False)
            .agg(
                inventory=("inventory_level", "sum"),
                sales_units=("sales_units", "sum")
            )
        )

        fig = px.line(
            inventory_df,
            x="start_date",
            y="inventory",
            markers=True,
            title="Inventory Level Trend"
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Inventory Units"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


    # Inventory turnover
    with operational_col2:

        turnover_df = (
            filtered_sales
            .groupby("start_date", as_index=False)
            .agg(
                cogs=("cost_of_goods_sold_cogs", "sum"),
                inventory=("inventory_level", "mean")
            )
        )

        turnover_df["inventory_turnover"] = np.where(
            turnover_df["inventory"] > 0,
            turnover_df["cogs"]
            / turnover_df["inventory"],
            np.nan
        )

        fig = px.line(
            turnover_df,
            x="start_date",
            y="inventory_turnover",
            markers=True,
            title="Inventory Turnover Ratio"
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Turnover Ratio"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # DSI
    st.subheader("Days Sales of Inventory (DSI)")

    dsi_df = (
        filtered_sales
        .groupby("start_date", as_index=False)
        .agg(
            inventory=("inventory_level", "mean"),
            cogs=("cost_of_goods_sold_cogs", "sum")
        )
    )

    dsi_df["dsi"] = np.where(
        dsi_df["cogs"] > 0,
        dsi_df["inventory"]
        / dsi_df["cogs"]
        * 7,
        np.nan
    )

    fig = px.line(
        dsi_df,
        x="start_date",
        y="dsi",
        markers=True,
        title="Days Sales of Inventory"
    )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="DSI (Days)"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


    
    # ============================================================
    # INVENTORY RISK
    # ============================================================

    st.header("3. Inventory Risk Alerts")

    inventory_risk = calculate_inventory_risk(
        filtered_sales,
        filtered_forecast
    )

    high_inventory_risk = inventory_risk[
        inventory_risk["risk_level"] == "High"
    ]

    medium_inventory_risk = inventory_risk[
        inventory_risk["risk_level"] == "Medium"
    ]


    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "High Risk Products",
            len(high_inventory_risk)
        )

    with col2:

        st.metric(
            "Medium Risk Products",
            len(medium_inventory_risk)
        )

    with col3:

        st.metric(
            "Products Analyzed",
            len(inventory_risk)
        )


    if len(high_inventory_risk) > 0:

        st.error(
            "⚠️ High inventory risk detected for "
            f"{len(high_inventory_risk)} product(s)."
        )

        st.dataframe(
            high_inventory_risk,
            use_container_width=True,
            hide_index=True
        )

    elif len(medium_inventory_risk) > 0:

        st.warning(
            "⚠️ Medium inventory risk detected."
        )

    else:

        st.success(
            "✓ No significant inventory coverage risks detected."
        )

    
    # ============================================================
    # SALES & DEMAND
    # ============================================================

    st.header("4. Sales Performance")

    sales_col1, sales_col2 = st.columns(2)


    # Sales units
    with sales_col1:

        sales_trend = (
            filtered_sales
            .groupby("start_date", as_index=False)
            .agg(
                sales_units=("sales_units", "sum")
            )
        )

        fig = px.line(
            sales_trend,
            x="start_date",
            y="sales_units",
            markers=True,
            title="Historical Sales Units"
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Sales Units"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


    # Product sales
    with sales_col2:

        product_sales = (
            filtered_sales
            .groupby("product", as_index=False)
            .agg(
                sales_units=("sales_units", "sum")
            )
            .sort_values(
                "sales_units",
                ascending=False
            )
        )

        fig = px.bar(
            product_sales,
            x="product",
            y="sales_units",
            title="Sales Units by Product"
        )

        fig.update_layout(
            xaxis_title="Product",
            yaxis_title="Sales Units"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )


    
    # ============================================================
    # 26-WEEK FORECAST
    # ============================================================

    st.header("5. 26-Week Demand Forecast")

    st.markdown(
        """
        The forecast below uses the `predicted_sales` values generated
        by your PCA forecasting model.
        """
    )


    # Forecast summary
    forecast_summary = (
        filtered_forecast
        .groupby("product", as_index=False)
        .agg(
            forecast_demand=(
                "predicted_sales",
                "sum"
            ),
            average_weekly_forecast=(
                "predicted_sales",
                "mean"
            )
        )
    )


    forecast_col1, forecast_col2, forecast_col3 = st.columns(3)

    with forecast_col1:

        total_forecast = (
            filtered_forecast["predicted_sales"]
            .sum()
        )

        kpi_card(
            "26-Week Forecast",
            f"{total_forecast:,.0f}",
            "Predicted sales units"
        )

    with forecast_col2:

        avg_weekly_forecast = (
            filtered_forecast["predicted_sales"]
            .mean()
        )

        kpi_card(
            "Average Weekly Forecast",
            f"{avg_weekly_forecast:,.0f}",
            "Predicted units/week"
        )

    with forecast_col3:

        forecast_products = (
            filtered_forecast["product"]
            .nunique()
        )

        kpi_card(
            "Products Forecasted",
            forecast_products,
            "Products"
        )


    # Forecast chart
    forecast_chart = (
        filtered_forecast
        .groupby("week", as_index=False)
        .agg(
            predicted_sales=(
                "predicted_sales",
                "sum"
            )
        )
    )

    fig = px.line(
        forecast_chart,
        x="week",
        y="predicted_sales",
        markers=True,
        title="26-Week Forecasted Demand"
    )

    fig.update_layout(
        xaxis_title="Forecast Week",
        yaxis_title="Predicted Sales Units"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


    # ============================================================
    # HISTORICAL VS FORECAST
    # ============================================================

    st.subheader("Historical Sales vs Forecast")

    historical_sales = (
        filtered_sales
        .groupby("week", as_index=False)
        .agg(
            actual_sales=(
                "sales_units",
                "sum"
            )
        )
    )

    forecast_sales = (
        filtered_forecast
        .groupby("week", as_index=False)
        .agg(
            predicted_sales=(
                "predicted_sales",
                "sum"
            )
        )
    )

    comparison = pd.merge(
        historical_sales,
        forecast_sales,
        on="week",
        how="outer"
    ).sort_values("week")


    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=comparison["week"],
            y=comparison["actual_sales"],
            mode="lines+markers",
            name="Actual Sales"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=comparison["week"],
            y=comparison["predicted_sales"],
            mode="lines+markers",
            name="Forecast"
        )
    )

    fig.update_layout(
        title="Historical Sales and Forecast",
        xaxis_title="Week",
        yaxis_title="Sales Units",
        hovermode="x unified"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


        
    # ============================================================
    # PRODUCT FORECAST
    # ============================================================

    st.subheader("Forecast by Product")

    forecast_product_chart = (
        filtered_forecast
        .groupby("product", as_index=False)
        .agg(
            predicted_sales=(
                "predicted_sales",
                "sum"
            )
        )
        .sort_values(
            "predicted_sales",
            ascending=False
        )
    )

    fig = px.bar(
        forecast_product_chart,
        x="product",
        y="predicted_sales",
        title="Total 26-Week Forecast by Product"
    )

    fig.update_layout(
        xaxis_title="Product",
        yaxis_title="Forecasted Sales Units"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    
    # ============================================================
    # DEMAND RISK
    # ============================================================

    st.header("6. Demand Risk Alerts")

    # Average historical weekly sales by product
    historical_product = (
        filtered_sales
        .groupby("product", as_index=False)
        .agg(
            historical_weekly_sales=(
                "sales_units",
                "mean"
            )
        )
    )

    forecast_product = (
        filtered_forecast
        .groupby("product", as_index=False)
        .agg(
            forecast_weekly_sales=(
                "predicted_sales",
                "mean"
            )
        )
    )

    demand_risk = historical_product.merge(
        forecast_product,
        on="product",
        how="outer"
    )

    demand_risk[
        [
            "historical_weekly_sales",
            "forecast_weekly_sales"
        ]
    ] = demand_risk[
        [
            "historical_weekly_sales",
            "forecast_weekly_sales"
        ]
    ].fillna(0)

    demand_risk["forecast_change_pct"] = np.where(
        demand_risk["historical_weekly_sales"] != 0,
        (
            (
                demand_risk["forecast_weekly_sales"]
                - demand_risk["historical_weekly_sales"]
            )
            / demand_risk["historical_weekly_sales"]
        ) * 100,
        np.nan
    )


    def demand_risk_level(value):

        if pd.isna(value):
            return "Unknown"

        if value >= 20:
            return "High Growth"

        elif value <= -20:
            return "High Decline"

        return "Stable"


    demand_risk["risk_status"] = (
        demand_risk["forecast_change_pct"]
        .apply(demand_risk_level)
    )


    high_growth = demand_risk[
        demand_risk["risk_status"] == "High Growth"
    ]

    high_decline = demand_risk[
        demand_risk["risk_status"] == "High Decline"
    ]


    if len(high_growth) > 0:

        st.warning(
            f"📈 {len(high_growth)} product(s) have forecast demand "
            "more than 20% above historical weekly sales."
        )


    if len(high_decline) > 0:

        st.error(
            f"📉 {len(high_decline)} product(s) have forecast demand "
            "more than 20% below historical weekly sales."
        )


    st.dataframe(
        demand_risk.sort_values(
            "forecast_change_pct",
            ascending=False
        ),
        use_container_width=True,
        hide_index=True
    )




    
    # ============================================================
    # SALES & CREDIT RISK
    # ============================================================

    st.header("7. Sales & Credit Risk")

    st.warning(
        """
        Credit-risk KPIs cannot currently be calculated from
        `warehouse.vw_warehouse_sales` because the view does not contain
        customer default-risk, accounts receivable, or credit-sales fields.
        """
    )

    credit_col1, credit_col2 = st.columns(2)

    with credit_col1:

        kpi_card(
            "DSO",
            "N/A",
            "Requires Accounts Receivable + Credit Sales"
        )

    with credit_col2:

        kpi_card(
            "Default Risk Rating",
            "N/A",
            "Requires customer credit-risk data"
        )


    st.info(
        """
        To activate this section, connect a customer/credit dataset
        containing at least customer risk rating and accounts receivable /
        credit sales information.
        """
    )


        
    # ============================================================
    # RISK SUMMARY
    # ============================================================

    st.header("8. Management Risk Summary")

    risk_col1, risk_col2, risk_col3 = st.columns(3)

    with risk_col1:

        if len(high_inventory_risk) > 0:

            st.markdown(
                f"""
                <div class="risk-high">
                    <b>🔴 Inventory Risk</b><br>
                    {len(high_inventory_risk)} product(s)
                    have low inventory coverage.
                </div>
                """,
                unsafe_allow_html=True
            )

        else:

            st.markdown(
                """
                <div class="risk-low">
                    <b>🟢 Inventory Risk</b><br>
                    No high-risk inventory detected.
                </div>
                """,
                unsafe_allow_html=True
            )


    with risk_col2:

        if len(high_decline) > 0:

            st.markdown(
                f"""
                <div class="risk-high">
                    <b>🔴 Demand Risk</b><br>
                    {len(high_decline)} product(s)
                    show significant forecast decline.
                </div>
                """,
                unsafe_allow_html=True
            )

        elif len(high_growth) > 0:

            st.markdown(
                f"""
                <div class="risk-medium">
                    <b>🟡 Demand Risk</b><br>
                    {len(high_growth)} product(s)
                    show strong expected demand growth.
                </div>
                """,
                unsafe_allow_html=True
            )

        else:

            st.markdown(
                """
                <div class="risk-low">
                    <b>🟢 Demand Risk</b><br>
                    Forecast demand is relatively stable.
                </div>
                """,
                unsafe_allow_html=True
            )


    with risk_col3:

        negative_profit = (
            financial_risk[
                financial_risk["operating_profit"] < 0
            ]
        )

        if len(negative_profit) > 0:

            st.markdown(
                f"""
                <div class="risk-high">
                    <b>🔴 Profitability Risk</b><br>
                    {len(negative_profit)} product(s)
                    have negative operating profit.
                </div>
                """,
                unsafe_allow_html=True
            )

        else:

            st.markdown(
                """
                <div class="risk-low">
                    <b>🟢 Profitability Risk</b><br>
                    No products with negative operating profit.
                </div>
                """,
                unsafe_allow_html=True
            )




        
    # ============================================================
    # DATA DOWNLOAD
    # ============================================================

    st.header("9. Download Data")

    download_col1, download_col2 = st.columns(2)

    with download_col1:

        csv_historical = filtered_sales.to_csv(
            index=False
        )

        st.download_button(
            label="⬇️ Download Historical Data",
            data=csv_historical,
            file_name="historical_sales.csv",
            mime="text/csv"
        )


    with download_col2:

        csv_forecast = filtered_forecast.to_csv(
            index=False
        )

        st.download_button(
            label="⬇️ Download Forecast Data",
            data=csv_forecast,
            file_name="sales_forecast.csv",
            mime="text/csv"
        )


        
    # ============================================================
    # FOOTER
    # ============================================================

    st.divider()

    st.caption(
        "Warehouse Sales & Forecast Analytics Dashboard | "
        "PostgreSQL + Streamlit + PCA Forecast"
    )





# ============================================================
# DATABASE CONNECTION
# ============================================================

@st.cache_resource
def get_database_connection(database_url=DATABASE_URL):

    # Recommended:
    # Set DATABASE_URL as an environment variable.
    #
    # Example:
    # postgresql+psycopg2://username:password@localhost:5432/database_name


    if not database_url:
        st.error(
            "DATABASE_URL environment variable is not configured."
        )
        st.stop()

    return create_engine(
        database_url,
        pool_pre_ping=True
    )


# ============================================================
# LOAD HISTORICAL DATA
# ============================================================

@st.cache_data(ttl=600)
def load_sales_data():

    engine = get_database_connection()

    query = """
        SELECT
            sales_key,
            week,
            start_date,
            product,
            sales_units,
            cost_of_goods_sold_cogs,
            inventory_level,
            demand_forecast,
            price_per_unit,
            gross_profit,
            operating_profit,
            revenue,
            inventory_turnover_ratio,
            gross_profit_margin,
            revenue_growth,
            operating_cost,
            modified_row,
            run_id
        FROM warehouse.vw_warehouse_sales
        ORDER BY start_date, week, product;
    """

    with engine.connect() as connection:
        df = pd.read_sql(text(query), connection)

    return df


# ============================================================
# LOAD FORECAST
# ============================================================

@st.cache_data
def load_forecast(forecast_file = "pca_sales_forecast.csv"):

    # Change this path if necessary
    
    if not os.path.exists(forecast_file):
        st.error(
            f"Forecast file '{forecast_file}' was not found."
        )
        st.stop()

    forecast = pd.read_csv(forecast_file)

    # Normalize column names
    forecast.columns = (
        forecast.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    required_columns = [
        "week",
        "product",
        "predicted_sales"
    ]

    missing_columns = [
        c for c in required_columns
        if c not in forecast.columns
    ]

    if missing_columns:
        st.error(
            f"Forecast file is missing columns: {missing_columns}"
        )
        st.stop()

    forecast["week"] = pd.to_numeric(
        forecast["week"],
        errors="coerce"
    )

    forecast["predicted_sales"] = pd.to_numeric(
        forecast["predicted_sales"],
        errors="coerce"
    )

    forecast["product"] = forecast["product"].astype(str).str.strip()

    forecast = forecast.dropna(
        subset=["week", "product", "predicted_sales"]
    )

    return forecast


# ============================================================
# KPI CALCULATIONS
# ============================================================

def calculate_kpis(df):

    revenue = df["revenue"].sum()

    gross_profit = df["gross_profit"].sum()

    operating_profit = df["operating_profit"].sum()

    cogs = df["cost_of_goods_sold_cogs"].sum()

    # Weighted gross profit margin
    if revenue != 0:
        gross_profit_margin = (
            gross_profit / revenue
        ) * 100
    else:
        gross_profit_margin = np.nan

    # Inventory turnover
    average_inventory = df["inventory_level"].mean()

    if average_inventory > 0:
        inventory_turnover = (
            cogs / average_inventory
        )
    else:
        inventory_turnover = np.nan

    # DSI
    if cogs > 0:
        dsi = (
            average_inventory / cogs
        ) * len(df["week"].unique()) * 7
    else:
        dsi = np.nan

    # Revenue growth
    revenue_by_week = (
        df.groupby("week")["revenue"]
        .sum()
        .sort_index()
    )

    if len(revenue_by_week) >= 2:

        current_revenue = revenue_by_week.iloc[-1]
        previous_revenue = revenue_by_week.iloc[-2]

        if previous_revenue != 0:
            revenue_growth = (
                (current_revenue - previous_revenue)
                / previous_revenue
            ) * 100
        else:
            revenue_growth = np.nan

    else:
        revenue_growth = np.nan

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_profit": operating_profit,
        "gross_profit_margin": gross_profit_margin,
        "revenue_growth": revenue_growth,
        "inventory_turnover": inventory_turnover,
        "dsi": dsi
    }



# ============================================================
# KPI CARD
# ============================================================

def kpi_card(title, value, subtitle=""):

    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
            <div style="font-size:12px;color:#888;">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )



# ============================================================
# FORMATTERS
# ============================================================

def money(value):

    if pd.isna(value):
        return "N/A"

    return f"${value:,.0f}"


def percentage(value):

    if pd.isna(value):
        return "N/A"

    return f"{value:.2f}%"


def number(value):

    if pd.isna(value):
        return "N/A"

    return f"{value:,.2f}"


# ============================================================
# INVENTORY RISK
# ============================================================

def calculate_inventory_risk(
    historical,
    forecast
):

    # Latest inventory for each product
    latest_inventory = (
        historical
        .sort_values("start_date")
        .groupby("product")
        .tail(1)
        [["product", "inventory_level"]]
    )

    # Total forecast demand per product
    forecast_demand = (
        forecast
        .groupby("product")["predicted_sales"]
        .sum()
        .reset_index()
    )

    risk = latest_inventory.merge(
        forecast_demand,
        on="product",
        how="left"
    )

    risk["predicted_sales"] = (
        risk["predicted_sales"]
        .fillna(0)
    )

    # Coverage ratio
    risk["coverage_ratio"] = np.where(
        risk["predicted_sales"] > 0,
        risk["inventory_level"]
        / risk["predicted_sales"],
        np.inf
    )

    def risk_level(row):

        if row["predicted_sales"] <= 0:
            return "Low"

        ratio = row["coverage_ratio"]

        if ratio < 0.25:
            return "High"

        elif ratio < 0.50:
            return "Medium"

        return "Low"

    risk["risk_level"] = risk.apply(
        risk_level,
        axis=1
    )

    return risk.sort_values(
        "coverage_ratio"
    )



# ============================================================
# FINANCIAL RISK
# ============================================================

def calculate_financial_risk(product_df):

    results = []

    for product, group in product_df.groupby("product"):

        revenue = group["revenue"].sum()

        gross_profit = group["gross_profit"].sum()

        operating_profit = group["operating_profit"].sum()

        margin = (
            gross_profit / revenue * 100
            if revenue != 0
            else np.nan
        )

        results.append({
            "product": product,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "operating_profit": operating_profit,
            "gross_profit_margin": margin
        })

    result = pd.DataFrame(results)

    result["risk_level"] = np.select(
        [
            result["operating_profit"] < 0,
            result["gross_profit_margin"] < 10
        ],
        [
            "High",
            "Medium"
        ],
        default="Low"
    )

    return result






if __name__ == '__main__':
    main()