## End-to-End Workflow

```bash
# 1. Configure .env

# 2. Add Sample_Data.xlsx

# 3. Run ETL
python etl_data_pipeline.py

# 4. Run ONE forecasting methodology
python sales_forecast_v1.py
# OR
python sales_forecast_v2.py

# 5. Generate pricing recommendations
python pricing.py
```

This workflow produces the forecasting metrics, product-level forecasts, forecast shares, and dynamic pricing recommendations required for downstream analysis and visualization.



# Sales Forecasting, ETL & Dynamic Pricing Pipeline

This project provides an end-to-end data pipeline for **sales data processing, demand forecasting, PCA-based forecasting, and dynamic pricing recommendations**.

The project consists of three main stages:

1. **ETL pipeline** — loads and transforms the source data into PostgreSQL.
2. **Sales forecasting** — provides two forecasting methodologies:

   * Baseline forecasting
   * PCA-based forecasting
3. **Dynamic pricing** — generates pricing recommendations based on the processed sales data and forecasting results.

---

## Project Structure

```text
.
├── etl_data_pipeline.py
├── sales_forecast_v1.py
├── sales_forecast_v2.py
├── pricing.py
├── Sample_Data.xlsx              # Not included in GitHub
├── .env                          # Not included in GitHub
│
├── forecast_v1_reults.csv
├── forecast_v1_metrics.csv
├── forecast_v1_metrics_by_products.csv
│
├── pca_sales_forecast.csv
├── pca_product_results.csv
├── pca_forecast_shares.csv
│
├── dynamic_pricing_recommendations.csv
└── pricing_strategy_table.csv
```

> **Note:** Generated CSV files may not be included in the repository depending on the project configuration. They are created when the corresponding Python scripts are executed.

---

# 1. Requirements

Make sure you have the following installed:

* Python 3.11.0
* PostgreSQL
* pip

Install the required Python packages using:

```bash
pip install -r requirements.txt
```

If a `requirements.txt` file is not provided, install the packages required by the Python scripts and database connection.

---

# 2. Environment Configuration

Create a `.env` file in the root directory of the project.

The `.env` file should contain your PostgreSQL connection information:

```env
HOST="localhost"
PORT="5432"
DB_NAME="Armani"
USER_NAME="YOUR_USER_NAME"
PASSWORD="YOUR_POSTGRES_PASSWORD"
```

Replace `YOUR_POSTGRES_PASSWORD` with your own PostgreSQL password.

### Security

The `.env` file contains sensitive database credentials and **must not be committed to GitHub**.

Make sure `.env` is included in `.gitignore`:

```gitignore
.env
```

---

# 3. Input Data

For data protection purposes, the source file:

```text
Sample_Data.xlsx
```

is **not included in the GitHub repository**.

To run the ETL pipeline successfully, place the `Sample_Data.xlsx` file in the **same directory as**:

```text
etl_data_pipeline.py
```

The directory should therefore look like:

```text
project/
├── etl_data_pipeline.py
├── Sample_Data.xlsx
├── sales_forecast_v1.py
├── sales_forecast_v2.py
├── pricing.py
└── .env
```

---

# 4. Step 1 — Run the ETL Pipeline

The first script that must be executed is:

```bash
python etl_data_pipeline.py
```

The ETL pipeline:

* Reads the source Excel file
* Processes and transforms the data
* Creates the required datasets/tables in PostgreSQL
* Prepares the database for the forecasting and pricing stages

### Week Start Date

At the beginning of `etl_data_pipeline.py`, the variable:

```python
WEEK1_DATE
```

defines the date corresponding to the first week in the dataset.

The current configuration uses:

```python
WEEK1_DATE = "01/01/2020"
```

If the starting date of the dataset changes, update this variable before running the ETL pipeline.

---

# 5. Step 2 — Sales Forecasting

After successfully running the ETL pipeline, you can run either of the two forecasting methodologies.

## Version 1 — Baseline Method

Run:

```bash
python sales_forecast_v1.py
```

Version 1 implements the **baseline forecasting methodology**.

The generated output files are:

```text
forecast_v1_reults.csv
forecast_v1_metrics.csv
forecast_v1_metrics_by_products.csv
```

These files contain the forecast results and performance evaluation metrics for the baseline approach.

> **Note:** The filename `forecast_v1_reults.csv` follows the existing project filename. If the filename is intended to be `forecast_v1_results.csv`, update both the script and documentation accordingly.

---

## Version 2 — PCA Methodology

Run:

```bash
python sales_forecast_v2.py
```

Version 2 uses a **Principal Component Analysis (PCA)-based methodology** for sales forecasting.

The generated output files are:

```text
pca_sales_forecast.csv
pca_product_results.csv
pca_forecast_shares.csv
```

These files contain the PCA-based forecasting results, product-level results, and forecast share information.

---

# 6. Step 3 — Dynamic Pricing

After the required forecasting process has been completed, run:

```bash
python pricing.py
```

The `pricing.py` script implements the **dynamic pricing strategy**.

The generated output files are:

```text
dynamic_pricing_recommendations.csv
pricing_strategy_table.csv
```

### Output Description

**`dynamic_pricing_recommendations.csv`**

Contains the recommended pricing decisions generated by the pricing strategy.

**`pricing_strategy_table.csv`**

Contains the pricing strategy information used to support the recommendations.

---

# 7. Complete Execution Order

For a complete end-to-end execution, follow this order:

### Step 1 — Configure the environment

Create:

```text
.env
```

and configure the PostgreSQL connection.

### Step 2 — Add the input data

Place:

```text
Sample_Data.xlsx
```

in the same directory as `etl_data_pipeline.py`.

### Step 3 — Run ETL

```bash
python etl_data_pipeline.py
```

### Step 4 — Run a forecasting methodology

For the baseline methodology:

```bash
python sales_forecast_v1.py
```

**OR**

For the PCA methodology:

```bash
python sales_forecast_v2.py
```

### Step 5 — Run dynamic pricing

```bash
python pricing.py
```

---

# 8. Pipeline Overview

The overall workflow can be summarized as:

```text
                 Sample_Data.xlsx
                        │
                        ▼
              etl_data_pipeline.py
                        │
                        ▼
                   PostgreSQL
                        │
              ┌─────────┴─────────┐
              │                   │
              ▼                   ▼
    sales_forecast_v1.py   sales_forecast_v2.py
              │                   │
              ▼                   ▼
       Baseline Forecast       PCA Forecast
              │                   │
              └─────────┬─────────┘
                        │
                        ▼
                   pricing.py
                        │
                        ▼
             Dynamic Pricing Results
```

---

# 9. Outputs

After completing the pipeline, the project can generate the following outputs:

### Baseline Forecast

```text
forecast_v1_reults.csv
forecast_v1_metrics.csv
forecast_v1_metrics_by_products.csv
```

### PCA Forecast

```text
pca_sales_forecast.csv
pca_product_results.csv
pca_forecast_shares.csv
```

### Dynamic Pricing

```text
dynamic_pricing_recommendations.csv
pricing_strategy_table.csv
```

---

# 10. Important Notes

* PostgreSQL must be running before executing the ETL pipeline.
* The database specified in `.env` must exist before running the scripts.
* `Sample_Data.xlsx` must be placed next to `etl_data_pipeline.py`.
* The ETL pipeline must be executed **before** running the forecasting scripts.
* `WEEK1_DATE` should match the actual starting date of the dataset.
* Do not commit `.env` or other files containing credentials to GitHub.
* The forecasting scripts should be run after the required PostgreSQL datasets have been created by the ETL pipeline.
* The dynamic pricing script should be executed after the required forecasting/data-processing steps have been completed.

---

# 11. Streamlit BI Dashboard

The project also includes an interactive **Business Intelligence dashboard** implemented using Streamlit.

The dashboard is launched through:

```bash
streamlit run streamlit_app.py
```

The Streamlit application provides interactive visualizations and analysis of the processed sales, financial, inventory, and forecasting data.

## Dashboard Prerequisites

Before launching the Streamlit dashboard, the following scripts **must already have been executed successfully**:

### 1. ETL Pipeline

```bash
python etl_data_pipeline.py
```

This creates and prepares the required datasets in PostgreSQL.

### 2. PCA-Based Sales Forecast

```bash
python sales_forecast_v2.py
```

This generates the PCA forecasting outputs required by the dashboard.

Therefore, the minimum required execution sequence for the dashboard is:

```text
Sample_Data.xlsx
       │
       ▼
etl_data_pipeline.py
       │
       ▼
PostgreSQL datasets
       │
       ▼
sales_forecast_v2.py
       │
       ▼
PCA forecasting outputs
       │
       ▼
streamlit_app.py
       │
       ▼
Interactive BI Dashboard
```

## Running the Dashboard

Once the ETL pipeline and PCA forecasting have been completed, run:

```bash
streamlit run streamlit_app.py
```

Streamlit will start a local web server and provide a URL that can be opened in a web browser.

The dashboard contains interactive BI pages for analyzing:

* Executive Overview
* Financial Performance
* Inventory & Operations
* Historical sales performance
* Sales forecasting
* Financial KPIs
* Inventory and operational KPIs
* Product-level performance

> **Important:** `streamlit_app.py` should not be run before `etl_data_pipeline.py` and `sales_forecast_v2.py`, as the dashboard depends on the datasets and forecasting outputs generated by these scripts.

---

# 12. Complete Execution Workflow

For the complete project workflow, use the following sequence:

```bash
# Step 1 — Configure the environment
# Create and configure .env

# Step 2 — Add the source data
# Place Sample_Data.xlsx next to etl_data_pipeline.py

# Step 3 — Run ETL
python etl_data_pipeline.py

# Step 4 — Run forecasting
# Baseline forecasting (optional)
python sales_forecast_v1.py

# OR

# PCA forecasting (required for Streamlit dashboard)
python sales_forecast_v2.py

# Step 5 — Run dynamic pricing
python pricing.py

# Step 6 — Launch the BI dashboard
streamlit run streamlit_app.py
```

### Dashboard-specific workflow

If the main goal is only to run the Streamlit BI dashboard, the minimum required steps are:

```bash
python etl_data_pipeline.py
python sales_forecast_v2.py
streamlit run streamlit_app.py
```

The **Baseline forecasting (V1)** and **dynamic pricing** scripts are separate components and are not required to launch the Streamlit dashboard.
