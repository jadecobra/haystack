# Haystack

This repository contains the code for **Haystack**, a web application designed to provide users with instant access to key financial metrics for any given stock ticker.

The metrics are calculated by parsing **10-K annual reports directly from the SEC EDGAR database**.

The goal with Haystack is to give you metrics to compare with prices quickly for anyone interested in fundamental stock analysis.

---

## Features

### Current (Minimum Viable Product - MVP)

* **Ticker Search:** A simple, intuitive search bar allows users to input any valid stock ticker symbol.
* **5-Year XBRL Data:** Automatically retrieves and processes the last **5 years of 10-K filings** in **XBRL format** from SEC EDGAR.
* **Comprehensive Metric Calculation:** Calculates and displays a wide array of financial ratios and per-share metrics, including:

    * **Ratios:**
      - Net Income/Revenue
      - Net Income/Equity
      - Net Income/Assets
      - Net Income/Total Liabilities
      - Net Income/Debt
      - Free Cash Flow/Revenue
      - Free Cash Flow/Equity
      - Free Cash Flow/Assets
      - Free Cash Flow/Total Liabilities
      - Free Cash Flow/Debt
      - Dividends/Net Income
      - Dividends/Free Cash Flow
      - Dividends/Equity

    * **Per Share Metrics:**
      - Debt per Share
      - Revenue per Share
      - Net Income per Share
      - Free Cash Flow per Share
      - Dividends per Share
      - Equity per Share
      - Assets per Share
      - Cash per Share
      - Liabilities per Share
      - Free Cash Flow/30 yr Treasury per Share

* **Tabular Display:** Presents all calculated metrics in a clean, easy-to-read, and **responsive table format**, showing year-over-year data for quick comparison.

### Future Enhancements

* **Advanced Data History:** Extend data retrieval beyond 5 years to include all available 10-K filings, addressing complexities with older HTML and TXT formats.
* **Interactive Visualizations:** Implement a comprehensive dashboard featuring:
    * **Key Performance Indicator (KPI) Cards:** Prominent display of the latest year's critical metrics.
    * **Interactive Line Charts:** Visualize historical trends for all ratios and per-share metrics over time.
    * **Grouped Visualizations:** Organize metrics logically for better insights.
* **Performance Optimizations:** Further enhance data parsing speed and caching mechanisms.

---

## Technology Stack

Haystack is built with a commitment to **Test-Driven Development (TDD)** and designed for **production-grade reliability**, **scalability (1M+ users)**, and **minimal infrastructure cost**.

* **Backend:** Python 3.9+ (leveraging frameworks like Flask or FastAPI for robust API development).
* **Frontend:** HTML, CSS, and JavaScript for a responsive and intuitive user interface.
* **Data Source:** SEC EDGAR database for 10-K filings; FRED API for 30-year U.S. Treasury yields.
* **Cloud Infrastructure:** Designed for deployment on **AWS**, utilizing serverless components (AWS Lambda, S3, API Gateway, DynamoDB) and caching (ElastiCache) for cost-efficiency and auto-scaling.

---

## Getting Started

*(This section will contain instructions on how to set up the project locally, install dependencies, and run the application. Placeholder for now.)*

---

I am excited about building this financial tool! explore the code, report issues, or suggest improvements.