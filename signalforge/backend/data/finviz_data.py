"""
FinViz fundamental data — fetched via curl_cffi, parsed via BeautifulSoup.

This implementation fetches the FinViz HTML page directly with curl_cffi
(Chrome TLS impersonation, same technique used for StockTwits) and parses
it with BeautifulSoup. finvizfinance is no longer used for HTTP — only its
data models are referenced if needed.

No API key required. Redis TTL: 4 hours.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

FINVIZ_BASE   = "https://finviz.com/quote.ashx"
TIMEOUT       = 15.0
BROWSER       = "chrome"

# User-agent is set by curl_cffi's impersonation — do not override it.
# Adding a mismatched User-Agent header would worsen TLS fingerprint
# detection by creating a mismatch between the JA3 and the UA string.
HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://finviz.com/",
}


@dataclass
class FinvizFundamentals:
    ticker: str
    # Valuation
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    ps_ratio: Optional[float]
    pb_ratio: Optional[float]
    price_to_fcf: Optional[float]
    # Growth
    eps_ttm: Optional[float]
    eps_next_year: Optional[float]
    eps_next_5y_pct: Optional[float]
    eps_past_5y_pct: Optional[float]
    sales_past_5y_pct: Optional[float]
    # Profitability
    gross_margin_pct: Optional[float]
    oper_margin_pct: Optional[float]
    profit_margin_pct: Optional[float]
    roa_pct: Optional[float]
    roe_pct: Optional[float]
    roi_pct: Optional[float]
    # Financial health
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    quick_ratio: Optional[float]
    # Ownership
    insider_own_pct: Optional[float]
    insider_trans_pct: Optional[float]
    inst_own_pct: Optional[float]
    short_float_pct: Optional[float]
    # Market
    market_cap_billions: Optional[float]
    beta: Optional[float]
    # Insider activity (derived from insider table)
    net_insider_sentiment: Optional[float]   # -1.0 to +1.0
    insider_buys_90d: Optional[int]
    insider_sells_90d: Optional[int]
    # Recent analyst actions
    recent_analyst_actions: list = field(default_factory=list)
    # Meta
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "finviz"


async def fetch_finviz_fundamentals(ticker: str) -> Optional[FinvizFundamentals]:
    """
    Fetch and parse FinViz fundamental data for a ticker.

    Fetches the raw HTML page with curl_cffi (bypasses Cloudflare),
    then parses with BeautifulSoup. Runs in async context.
    Returns None on any failure — never raises.
    """
    try:
        html = await _fetch_html(ticker)
        if html is None:
            return None
        logger.info("Calling finviz")
        return await asyncio.get_event_loop().run_in_executor(
            None, _parse_html, ticker, html
        )
    except Exception as exc:
        logger.warning("fetch_finviz_fundamentals failed for %s: %s", ticker, exc)
        return None


async def _fetch_html(ticker: str) -> Optional[str]:
    """
    Fetch raw FinViz quote page HTML using curl_cffi with Chrome impersonation.
    Returns raw HTML string, or None on error.
    """
    url    = f"{FINVIZ_BASE}?t={ticker.upper()}"
    try:
        async with AsyncSession(impersonate=BROWSER, timeout=TIMEOUT) as session:
            resp = await session.get(url, headers=HEADERS)

        if resp.status_code == 404:
            logger.warning("FinViz: ticker %s not found (404)", ticker)
            return None
        if resp.status_code == 403:
            logger.warning(
                "FinViz: 403 Forbidden for %s — Cloudflare still blocking. "
                "curl_cffi impersonation may need updating: uv add curl-cffi --upgrade",
                ticker,
            )
            return None
        if resp.status_code != 200:
            logger.warning(
                "FinViz: unexpected status %s for %s", resp.status_code, ticker
            )
            return None

        html = resp.text
        logger.info("FinViz returned: %s", len(html))

        # Detect Cloudflare challenge page — real data pages contain
        # "snapshot-table2" or "fv-container" in their HTML.
        # A challenge page contains neither and instead has "cf-browser-verification".
        if "cf-browser-verification" in html or "Just a moment" in html:
            logger.warning(
                "FinViz: received Cloudflare challenge page for %s — "
                "curl_cffi impersonation may need updating: uv add curl-cffi --upgrade",
                ticker,
            )
            return None

        if "snapshot-table2" not in html and "fv-container" not in html:
            logger.warning(
                "FinViz: page for %s does not contain expected data tables — "
                "FinViz HTML structure may have changed",
                ticker,
            )
            return None

        return html

    except Exception as exc:
        logger.warning("FinViz HTTP fetch failed for %s: %s", ticker, exc)
        return None


def _parse_html(ticker: str, html: str) -> Optional[FinvizFundamentals]:
    """
    Parse FinViz quote page HTML into a FinvizFundamentals dataclass.
    Runs synchronously — must be called via run_in_executor.

    FinViz fundamentals live in a table with class "snapshot-table2".
    Each row has alternating <td> cells: label, value, label, value...
    We build a flat dict of {label: value} then extract fields.
    """
    try:
        soup = BeautifulSoup(html, "lxml")

        # --- Fundamentals table ---
        fund_dict = _parse_fundamentals_table(soup)
        if not fund_dict:
            logger.warning(
                "FinViz: could not parse fundamentals table for %s", ticker
            )
            return None

        # --- Insider trading table ---
        net_sentiment, buys, sells = _parse_insider_table(soup)

        # --- Analyst ratings table ---
        recent_actions = _parse_ratings_table(soup)

        return FinvizFundamentals(
            ticker=ticker,
            pe_ratio=_parse_float(fund_dict.get("P/E")),
            forward_pe=_parse_float(fund_dict.get("Forward P/E")),
            peg_ratio=_parse_float(fund_dict.get("PEG")),
            ps_ratio=_parse_float(fund_dict.get("P/S")),
            pb_ratio=_parse_float(fund_dict.get("P/B")),
            price_to_fcf=_parse_float(fund_dict.get("P/FCF")),
            eps_ttm=_parse_float(fund_dict.get("EPS (ttm)")),
            eps_next_year=_parse_float(fund_dict.get("EPS next Y")),
            eps_next_5y_pct=_parse_pct(fund_dict.get("EPS next 5Y")),
            eps_past_5y_pct=_parse_pct(fund_dict.get("EPS past 5Y")),
            sales_past_5y_pct=_parse_pct(fund_dict.get("Sales past 5Y")),
            gross_margin_pct=_parse_pct(fund_dict.get("Gross Margin")),
            oper_margin_pct=_parse_pct(fund_dict.get("Oper. Margin")),
            profit_margin_pct=_parse_pct(fund_dict.get("Profit Margin")),
            roa_pct=_parse_pct(fund_dict.get("ROA")),
            roe_pct=_parse_pct(fund_dict.get("ROE")),
            roi_pct=_parse_pct(fund_dict.get("ROI")),
            debt_to_equity=_parse_float(fund_dict.get("Debt/Eq")),
            current_ratio=_parse_float(fund_dict.get("Current Ratio")),
            quick_ratio=_parse_float(fund_dict.get("Quick Ratio")),
            insider_own_pct=_parse_pct(fund_dict.get("Insider Own")),
            insider_trans_pct=_parse_pct(fund_dict.get("Insider Trans")),
            inst_own_pct=_parse_pct(fund_dict.get("Inst Own")),
            short_float_pct=_parse_pct(fund_dict.get("Short Float")),
            market_cap_billions=_parse_market_cap(fund_dict.get("Market Cap")),
            beta=_parse_float(fund_dict.get("Beta")),
            net_insider_sentiment=net_sentiment,
            insider_buys_90d=buys,
            insider_sells_90d=sells,
            recent_analyst_actions=recent_actions,
        )

    except Exception as exc:
        logger.warning("FinViz HTML parse error for %s: %s", ticker, exc)
        return None


def _parse_fundamentals_table(soup: BeautifulSoup) -> dict:
    """
    Parse the snapshot-table2 into a {label: value} dict.
    Table structure: rows of <td class="snapshot-td2-cp"> (label)
    alternating with <td class="snapshot-td2"> (value).
    """
    result = {}
    # Collect ALL td cells across ALL matching snapshot tables.
    # FinViz splits fundamentals across multiple tables that share
    # the same class — finding only the first table misses P/E and
    # other ratios that live in the second or third table.
    all_cells = []
    candidates = soup.find_all(
        "table",
        class_=lambda c: c and (
            "snapshot-table2" in c or "js-snapshot-table" in c
        )
    )
    if not candidates:
        # Fallback: any table with "snapshot" in any class
        candidates = soup.find_all(
            "table", {"class": re.compile(r"snapshot", re.I)}
        )

    for t in candidates:
        all_cells.extend(t.find_all("td"))

    if not all_cells:
        return result

    # Cells alternate label / value across the combined cell list.
    # Known label set guards against misaligned pairs — if a cell
    # text is not a known label it is treated as a stray value
    # and skipped, keeping the label/value pairing correct.
    KNOWN_LABELS = {
        "Index", "Market Cap", "Enterprise Value", "Income", "Sales",
        "Book/sh", "Cash/sh", "Dividend Est.", "Dividend TTM",
        "Dividend Ex-Date", "Dividend Gr. 3/5Y", "Payout", "Employees",
        "IPO", "P/E", "Forward P/E", "PEG", "P/S", "P/B", "P/C",
        "P/FCF", "EPS (ttm)", "EPS next Y", "EPS next Q", "EPS this Y",
        "EPS next 5Y", "EPS past 5Y", "Sales past 5Y", "Sales Q/Q",
        "EPS Q/Q", "Earnings", "Gross Margin", "Oper. Margin",
        "Profit Margin", "ROA", "ROE", "ROI", "Debt/Eq", "LT Debt/Eq",
        "Current Ratio", "Quick Ratio", "Insider Own", "Insider Trans",
        "Inst Own", "Inst Trans", "Short Float", "Short Ratio",
        "Short Interest", "52W High", "52W Low", "RSI (14)", "Beta",
        "ATR (14)", "SMA20", "SMA50", "SMA200", "Volume", "Avg Volume",
        "Rel Volume", "Prev Close", "Price", "Change", "Perf Week",
        "Perf Month", "Perf Quarter", "Perf Half Y", "Perf Year",
        "Perf YTD", "Volatility", "Recom", "Target Price",
        "52W Range", "Optionable", "Shortable",
    }

    i = 0
    while i < len(all_cells) - 1:
        label = all_cells[i].get_text(strip=True)
        value = all_cells[i + 1].get_text(strip=True)
        if label in KNOWN_LABELS:
            result[label] = value
            i += 2
            logger.info("fundamental %s = %s", label, value)
        else:
            # Not a known label — skip one cell to re-sync pairing
            i += 1

    return result


def _parse_insider_table(soup: BeautifulSoup) -> tuple[Optional[float], int, int]:
    """
    Parse insider trading table. Returns (net_sentiment, buys, sells).
    net_sentiment = (buys - sells) / total, range -1.0 to +1.0.
    """
    buys  = 0
    sells = 0
    try:
        # Insider table rows have class "insider-row" or similar
        insider_table = soup.find("table", id="insider-trading-table")
        if insider_table is None:
            insider_table = soup.find(
                "table", {"class": re.compile(r"insider", re.I)}
            )
        if insider_table is None:
            return None, 0, 0

        for row in insider_table.find_all("tr")[1:]:   # skip header
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            transaction = cols[3].get_text(strip=True).lower()
            if "buy" in transaction or "purchase" in transaction:
                buys += 1
            elif "sale" in transaction or "sell" in transaction:
                sells += 1

        total = buys + sells
        sentiment = round((buys - sells) / total, 4) if total > 0 else None
        return sentiment, buys, sells

    except Exception as exc:
        logger.debug("insider table parse error: %s", exc)
        return None, buys, sells


def _parse_ratings_table(soup: BeautifulSoup) -> list:
    """
    Parse the outer ratings / analyst actions table.
    Returns list of dicts with date, status, firm, target.
    """
    actions = []
    try:
        ratings_table = soup.find("table", id="analyst-ratings-table")
        if ratings_table is None:
            ratings_table = soup.find(
                "table", {"class": re.compile(r"rating|outer", re.I)}
            )
        if ratings_table is None:
            return actions

        for row in ratings_table.find_all("tr")[1:6]:  # last 5 actions
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            actions.append({
                "date":   cols[0].get_text(strip=True),
                "status": cols[1].get_text(strip=True),
                "firm":   cols[2].get_text(strip=True),
                "target": cols[3].get_text(strip=True),
            })
    except Exception as exc:
        logger.debug("ratings table parse error: %s", exc)

    return actions


# ---------------------------------------------------------------------------
# Value parsers — identical to previous implementation
# ---------------------------------------------------------------------------

def _parse_pct(val: Optional[str]) -> Optional[float]:
    if not val or val == "-":
        return None
    try:
        return float(str(val).replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_float(val: Optional[str]) -> Optional[float]:
    if not val or val == "-":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.endswith("B"):
            return float(s[:-1]) * 1e9
        if s.endswith("M"):
            return float(s[:-1]) * 1e6
        if s.endswith("K"):
            return float(s[:-1]) * 1e3
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_market_cap(val: Optional[str]) -> Optional[float]:
    if not val or val == "-":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.endswith("T"):
            return float(s[:-1]) * 1000
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000
        return float(s) / 1e9
    except (ValueError, TypeError):
        return None