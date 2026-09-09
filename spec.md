## Website Specification: Financial Metrics from 10-K Filings

This document outlines the specification for a web application that displays financial metrics for a given stock ticker, calculated from SEC EDGAR 10-K filings. The project will follow a Test-Driven Development (TDD) approach using Python, aiming for a production-grade, responsive, secure, and highly scalable (1M+ users) solution with minimal infrastructure costs.

---

### 1. Project Goal

To build a robust and cost-effective web application that allows users to quickly view key financial ratios and per-share metrics for a stock ticker, derived from SEC EDGAR 10-K filings. The initial focus will be on the last 5 years of XBRL data, with a roadmap for more extensive historical data and advanced visualizations.

---

### 2. Core Functionality (Minimum Viable Product - MVP)

**2.1. User Input:**
* A single, clear text input field (search bar) where users can enter a stock ticker symbol (e.g., "AAPL", "MSFT").
* A "Submit" or "Search" button to trigger the data retrieval and calculation.

**2.2. Data Retrieval & Parsing:**
* Upon submission, the system will fetch the latest 5 years of 10-K annual reports for the provided ticker from the SEC EDGAR database.
* **Constraint:** Only 10-K filings available in **XBRL format** will be processed for the MVP. Older formats (HTML, TXT) are out of scope for the initial phase.
* The system will extract relevant financial data points from the XBRL filings (e.g., Net Income, Revenue, Equity, Assets, Total Liabilities, Debt, Owner Earnings, Dividends, Shares Outstanding). Specific XBRL tags will need to be identified and mapped to these concepts.
* **Error Handling:** Graceful handling of invalid tickers, no 10-K filings found, or parsing errors.

**2.3. Financial Metric Calculation:**
The following metrics will be calculated year-over-year for the available 5 years of data:

* **Ratios:**
    * Net Income / Revenue
    * Net Income / Equity
    * Net Income / Assets
    * Net Income / Total Liabilities
    * Net Income / Debt
    * Owner Earnings / Revenue
    * Owner Earnings / Equity
    * Owner Earnings / Assets
    * Owner Earnings / Total Liabilities
    * Owner Earnings / Debt
    * Owner Earnings / Last Close Price (owner earnings per share / last close; same last close for all years in the 5-year table)
    * Dividends / Net Income
    * Dividends / Owner Earnings
    * Dividends / Equity
* **Per Share Metrics:**
    * Debt per Share
    * Revenue per Share
    * Net Income per Share
    * Owner Earnings per Share
    * Dividends per Share
    * Equity per Share
    * Assets per Share
    * Cash per Share
    * Liabilities per Share
    * Owner Earnings / 30 Year Treasury per Share (Requires fetching 30-year U.S. Treasury yield data from an external API, e.g., FRED. This will be the only external non-SEC data source for the MVP.)

**Owner earnings.** Cash the business generated after maintenance reinvestment, before allocation (dividends, buybacks, M&A, growth capex above D&A, net debt). Internal field name remains `fcf`.

```
OE = OCF − min(|capex|, D&A)
```

OCF is the reported operating-cash tag when present. If missing: `ΔCash − CFI − CFF − FX` (FX = 0 if absent). If still missing: `NI + D&A − ΔNWC` using AR / inventory / AP pairs that exist in both the year and the prior year. Do not use NI + D&A with no working-capital pair. Capex is PPE (or the combined PPE+intangibles tag if present), plus capitalized software, without double-counting ProductiveAssets on top of PPE. If OCF cannot be resolved, or both capex and D&A are missing, owner earnings is null.

**2.4. Data Display (MVP UI):**
* A responsive HTML table displaying the calculated metrics.
* Each row will represent a metric, and each column will represent a year (e.g., 2024, 2023, 2022, 2021, 2020).
* Metrics should be clearly labeled.
* Appropriate formatting for numbers (e.g., currency, percentages, decimal places).

---

### 3. User Interface (Initial & Future)

**3.1. Initial UI (MVP):**
* **Homepage:** Contains a prominent search bar and button.
* **Results Page:** Displays the ticker symbol and the calculated financial metrics in a clean, readable table.
* **Responsiveness:** The table layout and input form must adapt gracefully to different screen sizes (mobile, tablet, desktop).

**3.2. Future UI (Advanced Features - Post-MVP):**
* **Dashboard-Style Layout:**
    * **KPI Cards:** Prominent display of the latest year's key metrics.
    * **Interactive Line Charts:** Visualizing historical trends for each ratio and per-share metric. Charts should allow hovering for exact values and potentially time-range selection.
    * **Grouped Visualizations:** Logical grouping of related ratios (e.g., profitability, solvency).
    * **Detailed Data Table:** A persistent or toggleable table providing the raw calculated values for all years.

---

### 4. Data Acquisition & Storage

**4.1. SEC EDGAR (Primary Source):**
* Utilize SEC EDGAR's API or a reliable Python library (e.g., `edgartools`, `py-xbrl`, `sec-api.io` if free tier or open source is sufficient for production scale) to access 10-K filings.
* Implement rate limiting as per SEC guidelines to avoid being blocked.
* For the MVP, focus on extracting data from XBRL instance documents. This requires understanding XBRL concepts and common US-GAAP taxonomy tags.

**4.2. 30-Year U.S. Treasury Yield (Secondary Source):**
* Fetch historical 30-year U.S. Treasury yield data (e.g., from FRED API). This data needs to be aligned with the 10-K filing periods.

**4.3. Data Storage (Cache/Database):**
* Implement a caching mechanism for fetched 10-K filings and parsed/calculated metrics to minimize repeat SEC requests and improve performance.
* A database (e.g., PostgreSQL for relational data, or a NoSQL database like DynamoDB if data structure is highly flexible) to store processed financial data. This will enable faster retrieval for subsequent requests and support scalability. Schema design should consider efficient querying for historical trends and latest values.

---

### 5. Technical Requirements & Constraints

**5.1. Programming Language:** Python 3.9+

**5.2. Web Framework:**
* A lightweight, high-performance Python web framework suitable for APIs and web applications.
* **Recommendation:** Flask or FastAPI for their flexibility, performance, and suitability for microservices/APIs, or Django if a more "batteries-included" approach is preferred for initial development (though might be heavier for minimal cost). The choice should support asynchronous operations for I/O bound tasks like external API calls.

**5.3. Frontend:**
* HTML, CSS, JavaScript (minimal for MVP, potentially a lightweight JS framework like Alpine.js for interactivity or a more robust one like React/Vue for future visualizations).
* Emphasis on responsive design (CSS Grid, Flexbox, media queries).

**5.4. Development Methodology:**
* **Test-Driven Development (TDD):** Unit tests for data parsing, metric calculation logic, API endpoints, and UI components (where applicable). Integration tests for end-to-end flows.
* **Version Control:** Git.

**5.5. Security:**
* Protection against common web vulnerabilities (OWASP Top 10): XSS, CSRF, SQL Injection (if relational DB), etc.
* Secure handling of environment variables and API keys.
* HTTPS enforcement.

---

### 6. Infrastructure & Scalability (1 Million Users, Cost-Minimal)

**6.1. Cloud Provider:** AWS is a strong candidate due to its extensive services and pricing models.

**6.2. Architecture Principles:**
* **Serverless First (where appropriate):** AWS Lambda for backend logic (fetching, parsing, calculating). This provides auto-scaling and pay-per-execution, significantly reducing costs during low traffic.
* **Static Site Hosting:** AWS S3 for hosting static frontend assets (HTML, CSS, JS). Coupled with AWS CloudFront (CDN) for global low-latency content delivery and caching. Extremely cost-effective for static content.
* **API Gateway:** AWS API Gateway to expose Lambda functions as REST APIs, handling routing, authentication (if needed), and rate limiting.
* **Managed Database Service:** AWS DynamoDB (NoSQL) for highly scalable, low-latency key-value storage of parsed financial data and calculated metrics. Alternatively, AWS RDS (PostgreSQL) if complex relational queries are anticipated, but might incur higher costs at extreme scale. DynamoDB's on-demand capacity and pay-per-request model align well with cost-minimal and burstable traffic.
* **Caching:** AWS ElastiCache (Redis) for in-memory caching of frequently accessed calculated metrics to reduce database load and latency.
* **Asynchronous Processing (Optional but Recommended for Scale):** AWS SQS for queuing long-running tasks like initial 10-K parsing to decouple the web request from the processing backend. This prevents timeouts and allows for robust retries.
* **Monitoring & Logging:** AWS CloudWatch for monitoring application health, performance, and logging.

**6.3. Scalability Strategy:**
* **Horizontal Scaling:** Leveraged through serverless (Lambda auto-scaling), managed databases (DynamoDB/RDS scaling groups), and load balancing (API Gateway/CloudFront).
* **Caching:** Extensive use of caching at CDN, application, and database layers.
* **Stateless Components:** Design backend services to be stateless to facilitate easy horizontal scaling.
* **Database Optimization:** Proper indexing and query optimization for the chosen database.

**6.4. Cost Optimization:**
* Utilize AWS Free Tier where applicable.
* Leverage serverless architectures (Lambda, S3, DynamoDB) which are pay-per-use.
* Implement efficient caching to reduce compute and database reads.
* Minimize data transfer costs (e.g., egress).

---

### 7. Development Methodology

* **Continuous Integration/Continuous Deployment (CI/CD):** Automate testing, building, and deployment processes (e.g., using GitHub Actions, AWS CodePipeline).
* **Modular Design:** Break down the application into smaller, manageable services (e.g., a data fetching service, a parsing service, a calculation service, a web presentation service). This aligns with microservices principles, aiding scalability and independent development/deployment.

---

### 8. Definition of Done (for initial MVP)

* User can access the website via a URL.
* User can input a stock ticker into a search bar.
* Upon submission, the website retrieves 10-K XBRL filings for the last 5 years.
* All specified financial ratios and per-share metrics are calculated correctly.
* The calculated metrics are displayed in a responsive, well-formatted HTML table.
* Error messages are displayed for invalid tickers or data retrieval/parsing issues.
* All core functionalities have passing unit and integration tests.
* The application is deployed to a cloud environment (AWS) and demonstrates basic responsiveness.
* Initial security measures are implemented (HTTPS, basic input validation).