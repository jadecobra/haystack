# US Equity Taxonomy via NASDAQ ICB Screener (#89)

Date: 2026-11-24
Status: Accepted

## Context

Non-S&P 1500 US filers previously fell back directly to SEC SIC divisions and 4-digit SIC codes for ticker classification and peer grouping. SEC SIC labels are dated and coarse for modern software, hardware, and financial companies, grouping heterogeneous businesses under broad legacy codes such as SIC 7372 (Prepackaged Software) and SIC 3674 (Semiconductors and Related Devices).

Three alternatives to SEC SIC were evaluated for non-S&P 1500 equities:
- **Yahoo Finance `assetProfile` endpoint**: Returns `401 Invalid Crumb` to unauthenticated requests and requires per-ticker scraping rather than a single snapshot.
- **Static SIC-to-GICS crosswalk**: Fails on many-to-many SEC codes such as SIC 7372, which spans enterprise software, consumer internet platforms, and cybersecurity vendors that belong in distinct industries.
- **10-K Item 1 inference**: Introduces model-inferred classification labels instead of an established exchange taxonomy.

NASDAQ exposes a bulk stock screener endpoint (`https://api.nasdaq.com/api/screener/stocks?download=true`) covering US exchange-listed equities with FTSE Russell Industry Classification Benchmark (ICB) sector and industry fields in a single JSON payload.

## Decision

1. **Taxonomy precedence**: Classify US tickers using a three-tier chain. S&P 1500 constituents use GICS from `backend/data/sp1500_map.json`. Other exchange-listed tickers use NASDAQ Screener ICB from `backend/data/us_taxonomy.json` (`scheme: "icb"`). Tickers absent from both snapshots fall back to SEC SIC (`scheme: "sic"`).
2. **Sector normalization**: Map the 11 NASDAQ ICB sectors onto canonical GICS sector names (`Basic Materials` to `Materials`, `Finance` to `Financials`, `Technology` to `Information Technology`, `Telecommunications` to `Communication Services`, and keeping the other 7 matching names intact). Keeping `Real Estate` separate from `Financials` preserves REIT owner-earnings rules, and unmapped labels such as `Miscellaneous` are preserved verbatim in `sector` alongside `raw_sector`.
3. **Peer grouping**: Rank SEC filers in `backend/data/sic_peers.json` (including S&P 1500 names) by NASDAQ ICB `industry` (`basis: "icb"`) using the existing $10M annual revenue floor, widening to the normalized ICB `sector` (`basis: "icb_sector"`) when fewer than 5 peers clear the floor (excluding `Miscellaneous` from sector widening). Tickers without an ICB entry fall back to 4-digit and 3-digit SEC SIC (`basis: "sic"` and `basis: "sic3"`). Refresh `backend/data/us_taxonomy.json` monthly in CI and re-rank `backend/data/sic_peers.json` offline when the taxonomy changes.

## Consequences

- **Modern industry labels for non-S&P tickers without per-ticker scraping**: One monthly request to the NASDAQ Screener bulk endpoint covers US exchange-listed equities using an established FTSE Russell ICB taxonomy.
- **Consistent sector semantics with S&P 1500 GICS**: Normalizing the 11 ICB sectors to GICS names keeps sector-level display and REIT owner-earnings handling aligned while retaining `raw_sector` in `us_taxonomy.json`.
- **Clean fallback for OTC and unlisted SEC filers**: Tickers absent from `us_taxonomy.json` continue to resolve via SEC SIC for both classification and peer comparison.
- **External endpoint dependency confined to monthly CI**: Runtime analysis reads static JSON snapshots (`us_taxonomy.json` and `sic_peers.json`), so NASDAQ API downtime or schema shifts only block the monthly refresh workflow (`min_rows` guard prevents writing truncated snapshots).
