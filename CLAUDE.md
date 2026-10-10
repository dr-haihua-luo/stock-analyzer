# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

don't assume. don't hide confusion. surface tradeoff
Before implementing
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

minimum code to solve the problem
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

touch only what you must.  clean up only your own code.
When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

define success criteria.  loop until verified.
Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Repository Overview

This repository contains the SignalForge trading analysis application, a trading signal generation system that uses AI agents to analyze market data, sector rotation, stock fundamentals, technicals, and news/social sentiment — then synthesizes everything into a BUY/HOLD/SELL signal with a 6-month outlook verdict.

The application source lives in the `signalforge/` subdirectory. Commands in this guide are run from there. This file (CLAUDE.md) sits at the repository root.

The application consists of:
- A backend built with Python 3.10+, FastAPI, and LangGraph for AI agent orchestration
- A frontend built with React 18, Vite, TypeScript, and TailwindCSS (charts via Recharts)
- Infrastructure components including PostgreSQL, Redis, and Docker Compose
- Integration with OpenRouter API for LLM access

### Tech Stack Summary
- **Data sources**: Alpaca Market Data (OHLCV, quotes, news), yfinance (indexes, sector ETFs, rates, FX), FRED/fredapi (inflation expectations, Fed funds), Finviz (fundamentals scraping via curl_cffi, now also provides sector/industry classification and institutional ownership), TipRanks MCP (analyst ratings, price targets, smart score), StockTwits public stream (social sentiment), FMP (earnings quality)
- **Indicators**: pandas / numpy / `ta` library (RSIIndicator, MACD, Bollinger Bands); custom MA trend slope analysis (linear regression on long/medium/short moving averages); volatility-based statistical price range projection (log-normal model with VIX regime adjustment)
- **HTTP**: `curl_cffi` with Chrome TLS impersonation used for FinViz, StockTwits, and FMP requests to bypass Cloudflare bot detection
- **Cache**: Redis — per-source TTLs for data plus per-agent TTLs for LLM narratives (market/sector/news/overall: 1 hour; stock: 2 hours). Cache keys are `llm:<agent>:<ticker>` (input digest is computed but **not** included in the key — see Known Issues).
- **Database**: PostgreSQL via SQLAlchemy (async) + asyncpg, with Alembic migrations
- **Package Manager**: UV

## Code Structure

### Backend (`/signalforge/backend`)
- `main.py`: FastAPI application entry point (auto-runs DB migrations on startup), health check endpoint
- `config.py`: Pydantic-based configuration management (all env vars). 
- `Dockerfile`: Backend container build instructions (Python 3.11-slim + UV)
- `/agents`: LangGraph agent framework — 6-node pipeline (see Analysis Pipeline below)
  - `graph.py`: StateGraph state machine definition, node wiring, error-isolating conditional edges
  - `state.py`: TypedDict `AnalysisState` + Pydantic context models (`StockContext`, `MarketContext`)
  - `market_agent.py`: Macro/volatility analysis using prompt_version "market_v2" — fetches VIX, fear/greed, yield curve, indexes, rates, FX, inflation concurrently; LLM returns JSON with MACRO/RATES & FX/REGIME/OUTLOOK keys
  - `sector_agent.py`: Sector rotation analysis — independently determines the ticker's sector via FinViz, fetches the ticker's specific sector ETF data, then overall rotation; computes sector rank within the 11-sector ranking
  - `stock_agent.py`: Individual stock analysis (technicals + fundamentals + news) — also computes MA trend indicators and statistical price range projection (both informational only, do not affect signal); LLM cache TTL is 2 hours
  - `news_sentiment_agent.py`: Synthesizes Alpaca news + StockTwits sentiment into a narrative (NEWS/SENTIMENT/OUTLOOK format)
  - `overall_analysis_agent.py`: Final 6-month outlook synthesis across all narratives + signal into VERDICT/REASONING/WATCH format
  - `llm_client.py`: OpenRouter API integration with primary/fallback model failover (`minimax/minimax-m3:free` / `z-ai/glm-5.2:free`)
- `/signal`: Signal generation components
  - `engine.py`: Three independent horizon-specific signal functions, each with its own weighting, thresholds, and hysteresis. `compute_swing_signal` (3-5 week, technical-dominant: 45% technical / 20% sector / 15% market / 10% news_sentiment / 10% fundamental, thresholds ±0.30), `compute_position_signal` (6-month, fundamental-dominant: 40% fundamental_blend / 20% market / 15% sector / 15% institutional / 10% technical, thresholds ±0.30), and `compute_day_trade_signal` (EXPERIMENTAL, Phase 2 placeholder: 40% volatility_regime / 40% mean_reversion / 20% volume, thresholds ±0.35). All share helpers: `_classify_with_hysteresis`, `_unavailable_signal`, `_trading_days_until`. `compute_all_signals()` is the top-level entry point. The deprecated `SignalEngine` class and `compute_signal()` are retained for backward compatibility. Confidence = `min(abs(composite) / 0.8, 1.0)` for swing/position; `min(abs(composite) / 0.7, 1.0) * 0.6` for day_trade (deliberately capped lower)
  - `models.py`: Pydantic models — `SignalOutput`, `ConfidenceBreakdown`, `AnalysisRequest`, `AnalysisResponse`, plus display models for `FundamentalsDisplay`, `EarningsQualityDisplay`, `StockTwitsSentiment`, `FinvizSnapshot`, `TipRanksSnapshot`, `StockContextDisplay`, `PriceRangeProjection`/`PriceRangeHorizon`/`PriceRangeLevel`, `QuarterlyDataPoint`
- `/data`: Data collection modules
  - `market_data.py`: VIX, fear/greed, yield curve (via FRED/yfinance), indexes (S&P 500, Nasdaq, Dow, Russell), rates (US3M/10Y/30Y, Fed funds), FX (DXY, EURUSD, etc.), inflation expectations (breakeven rates via FRED with TIP ETF fallback). Standalone cached functions: `fetch_index_data`, `fetch_rate_data`, `fetch_fx_data`, `fetch_inflation_expectations`
  - `sector_data.py`: Sector ETF performance data for 11 GICS sectors (SPDR ETFs). `SectorData` class with `get_sector_performance`, `_get_etf_data`, `get_sector_etf_data`, `get_sector_etf_data_by_sector`
  - `stock_data.py`: Stock OHLCV bars (500 days for 12-month MA trend calc), latest price/quote, news headlines (10-day window). Technicals: RSI(14), MACD, Bollinger Bands, volume trend. MA trend indicators: long (12mo/252d), medium (2mo/42d), short (2wk/10d) via linear regression on MA slope. Statistical price range projection: log-normal volatility-based model with VIX regime adjustment for 2-day/1-week/2-week/1-month horizons at 68%/90%/95% confidence. **Note**: `compute_fundamental_score` (the old proxy function) is now dead code — the stock agent uses `fetch_fundamentals()` from `fundamentals_data.py` instead
  - `earnings_quality_data.py`: Earnings quality metrics from FMP API (revenue trends, margins, FCF, balance sheet). 3 concurrent HTTP calls per ticker, 4-hour cache TTL
  - `earnings_quality_cache.py`: Redis cache wrapper (`get_earnings_quality`) for earnings quality data
  - `finviz_data.py`: Fundamental data + sector/industry classification scraping from FinViz via curl_cffi + BeautifulSoup. Includes `normalize_sector_to_spdr()` to map FinViz sector labels to SPDR sector names. Fetches `inst_trans_pct`, `sector`, `industry` in addition to standard fundamental ratios. 4-hour Redis TTL (shared between sector_agent and stock_agent)
  - `fundamentals_data.py`: Orchestrates concurrent FinViz + TipRanks fetch and computes real `fundamental_score` via `_compute_fundamental_score()`. Scoring components: valuation (0.25), growth (0.25), profitability (0.25), financial health (0.08), insider sentiment (0.08), institutional flow (0.09), analyst consensus (0.0), smart score (0.0)
  - `tipranks_data.py`: Analyst consensus, price targets, smart score via TipRanks MCP SDK (Python `mcp` library). `TipRanksData` dataclass with consensus, price targets, buy/hold/sell counts, smart score, upside-to-target
  - `stocktwits_data.py`: Social sentiment from StockTwits public stream API (via curl_cffi). Parses last 30 messages for user-tagged bullish/bearish sentiment
- `/cache`: Redis client (`redis_client.py`) with typed TTLs and LLM narrative caching
  - `get()` / `set()` — general JSON-cached data (market, sector, stock data)
  - `get_raw()` / `set_raw()` — raw string caching (OHLCV DataFrames, fundamentals JSON)
  - `get_llm_narrative()` / `set_llm_narrative()` — LLM response cache. Key: `llm:<agent>:<ticker>` (see Known Issues for the digest-removal caveat). TTL: defaults to 1 hour (3600s); stock agent passes 7200s (2 hours); overall analysis passes 3600s (1 hour)
  - Redis connection retries with exponential backoff; app continues without cache on failure
- `/db`: PostgreSQL ORM
  - `models.py`: `Signal` model (id, ticker, signal, confidence, timestamp, price_at_signal, composite_score)
  - `session.py`: Async engine + session factory with auto-managed lifecycle

### Frontend (`/signalforge/frontend`)
- `App.tsx`: Main application component — orchestrates analysis flow, displays results, includes performance report modal. Renders `MATrendBadges` and `PriceRangePanel` components. Includes a "Raw Analysis Data (for debugging)" section that displays the full API response as JSON.
- `/src/components`: Reusable UI components (all under `src/components/`)
  - `SignalCard.tsx`: Displays the trading signal (BUY/HOLD/SELL), confidence %, and composite score
  - `MarketOverview.tsx`: Shows VIX, fear/greed, yield curve (uses mock data — does not call backend API)
  - `SectorHeatmap.tsx`: Visualizes sector rotation performance
  - `StockChart.tsx`: Interactive price charts using Recharts
  - `ConfidenceBreakdown.tsx`: Shows market/sector/technical/fundamental factor contributions. Market and sector bars display detailed LLM fields (MACRO, RATES & FX, REGIME, rotation momentum, economic implications, etc.) alongside narrative. Stock narrative rendered with section-aware parsing (TECHNICAL/SETUP/FUNDAMENTALS/ANALYST VIEW/SENTIMENT). Weight legend shows "Market 25%, Sector 25%, Stock 50%" — **bug**: actual weights are 20/30/50
  - `FundamentalPanel.tsx`: Displays FinViz + TipRanks fundamental data including "Institutional Activity" section (ownership + quarterly change), analyst consensus, price targets, KPI grid, insider activity, and fundamental score with coverage display
  - `EarningsQualityPanel.tsx`: Shows earnings quality metrics (revenue, margins, FCF, balance sheet)
  - `SentimentPanel.tsx`: Displays StockTwits social sentiment breakdown (bullish/bearish/neutral bars, participation metrics)
  - `NewsSentimentPanel.tsx`: Shows synthesized news + sentiment narrative
  - `OverallAnalysisPanel.tsx`: Final 6-month outlook verdict — parses narrative into VERDICT/REASONING/WATCH sections, applies signal styling, displays as a callout card
  - `MATrendBadges.tsx`: **NEW** — displays long (12-month), medium (2-month), short (2-week) MA trend direction badges. Shows alignment indicator when all three timeframes point the same direction
  - `PriceRangePanel.tsx`: **NEW** — statistical price range projection panel. Shows 68%/90%/95% confidence ranges for 2-day, 1-week, 2-week, 1-month horizons using log-normal volatility model with VIX adjustment. Informational only — not a price prediction
  - `PerformanceReport.tsx`: Historical signal accuracy report (modal)
  - `main.tsx`: React entry point (at `src/main.tsx`, not `src/components/`)
- `/src/hooks`: Custom React hooks
  - `useAnalysis.ts`: Handles `POST /api/analyze` requests with loading/error states
  - `usePerformance.ts`: Fetches `GET /api/performance/{ticker}` and manages report modal state
- `/src/types`: TypeScript type definitions
  - `signal.ts`: Signal output, confidence breakdown, request/response types, performance report types, price range projection types (`PriceRangeLevel`, `PriceRangeHorizon`, `PriceRangeProjection`), `StockContextDisplay`
- `/src/lib`: Utility modules
  - `api.ts`: API service layer (analyzeTicker, getSignalHistory)
- `/src/index.css`: Global CSS imports
- `vite.config.ts`: Vite config with `/api` proxy to backend on port 8000
- `tailwind.config.ts`: TailwindCSS configuration
- `postcss.config.cjs`: PostCSS configuration

### Infrastructure (`/signalforge`)
- `docker-compose.yml`: Defines PostgreSQL, Redis, and backend services; backend container auto-runs Alembic migrations on boot
- `Dockerfile`: Backend container (at `backend/Dockerfile`)
- `pyproject.toml`: UV package management configuration with all dependencies
- `alembic/`: Database migration scripts (3 migrations — 001 initial, 002 add price/composite, 003 add horizon for multi-horizon signals)
- `alembic.ini`: Alembic configuration
- `.env.example`: Template for environment variables 
- `.env`: Local environment configuration (not committed)

### Tests (`/tests`)
- `test_stock_data.py`: Unit tests for Alpaca API connectivity and stock data functions (uses mocks + live API fallback)

## Development Commands

### Backend Development
```bash
# From the signalforge/ directory:

# Start all services (PostgreSQL, Redis, backend)
docker-compose up -d

# Install Python dependencies
uv sync

# Run backend directly (for development, hot reload)
uv run uvicorn backend.main:app --reload

# Run database migrations
uv run alembic upgrade head

# Run tests
uv run pytest tests/
```

### Frontend Development
```bash
# From the signalforge/frontend/ directory:
npm install
npm run dev       # serves on http://localhost:5173, proxies /api to backend
```

### Testing and Verification
- Backend API documentation: http://localhost:8000/docs
- Frontend application: http://localhost:5173
- Health check endpoint: http://localhost:8000/health

## Common Tasks

### Understanding the Analysis Pipeline

The backend runs a six-stage LangGraph pipeline. Each narrative-producing agent
appends a `[tag] …` entry to a shared `reasoning` list, which the API layer
extracts into the structured response fields.

| Stage | Node | Agent | Produces |
|---|---|---|---|
| 1 | `market_analysis` | `market_agent.py` | macro regime (VIX, fear/greed, yield curve, indexes, rates, FX, inflation) → `market_narrative`; LLM returns JSON with MACRO/RATES & FX/REGIME/OUTLOOK keys |
| 2 | `sector_analysis` | `sector_agent.py` | sector rotation & momentum → `sector_narrative`; independently determines ticker's sector via FinViz → `sector_narrative` |
| 3 | `stock_analysis` | `stock_agent.py` | Alpaca OHLCV (500 days) + technicals (RSI/MACD/Bollinger) + FinViz/TipRanks fundamentals → `stock_narrative`; seeds `current_price` into state; also computes MA trends + statistical price range (informational only) |
| 4 | `news_sentiment` | `news_sentiment_agent.py` | Alpaca news (10-day window) + StockTwits → `news_sentiment_narrative` (NEWS/SENTIMENT/OUTLOOK format) |
| 5 | `signal_generation` | `engine.py` | three independent horizon signals (swing, position, day_trade) → `signals` dict in state |
| 6 | `overall_analysis` | `overall_analysis_agent.py` | synthesizes all narratives + quantitative signal + current price into 6-month outlook → `overall_analysis_narrative` (VERDICT/REASONING/WATCH format) |

**To understand the pipeline:**
1. Read `/backend/agents/graph.py` — StateGraph definition, node wiring, and error-isolating conditional edges
2. Review `/backend/agents/market_agent.py` — concurrent data fetches, extended MarketContext, market_v2 prompt
3. Review `/backend/agents/sector_agent.py` — FinViz sector determination, sector ETF fetch, rank computation
4. Review `/backend/agents/stock_agent.py` — technicals, MA trends, price range projection, fundamentals
5. Review `/backend/agents/news_sentiment_agent.py`, `overall_analysis_agent.py` — synthesis nodes
6. Examine `/backend/signal/engine.py` — three independent horizon-specific signal functions:
   - **`compute_swing_signal`** (3-5 week): technical-dominant — 45% technical / 20% sector / 15% market / 10% news_sentiment / 10% fundamental. Thresholds ±0.30, hysteresis 0.03. Flags earnings-date proximity as a risk warning.
   - **`compute_position_signal`** (6-month): fundamental-dominant — 40% fundamental_blend (fundamentals + earnings quality) / 20% market / 15% sector / 15% institutional / 10% technical. Thresholds ±0.30, hysteresis 0.03. Reports relative valuation vs. sector P/E benchmark.
   - **`compute_day_trade_signal`** (EXPERIMENTAL, Phase 2 placeholder): 40% volatility_regime / 40% mean_reversion / 20% volume. Thresholds ±0.35. Confidence scaled ×0.6 (capped lower). Requires intraday data in Phase 2.
   - All three share helper logic: `_classify_with_hysteresis`, `_unavailable_signal`, `_trading_days_until`.
   - `compute_all_signals()` returns `{"swing": {...}, "position": {...}, "day_trade": {...}}`.
   - The deprecated `SignalEngine` class and `compute_signal()` (single blended) are retained for backward compatibility — `generate_signal()` delegates to `compute_all_signals()` and returns the position signal.
7. Each signal is computed from the **same** `AnalysisState` but weights inputs appropriate to its horizon. Swing and position can legitimately disagree (e.g. bearish 6-month fundamentals + bullish short-term technicals). Only swing and position are persisted to the database; day_trade is excluded as experimental.


### LLM Response Caching

Every narrative-producing agent caches its OpenRouter response in Redis.

| Agent | Cache TTL | Key format |
|---|---|---|
| Market | 1 hour (3600s) | `llm:market:<ticker>` |
| Sector | 1 hour (3600s) | `llm:sector:<ticker>` |
| Stock | **2 hours (7200s)** | `llm:stock:<ticker>` |
| News/Sentiment | 1 hour (3600s) | `llm:news_sentiment:<ticker>` |
| Overall | 1 hour (3600s) | `llm:overall:<ticker>` |

Re-analyzing the same ticker within the TTL is served from cache — the LLM is **not** called again. Fetched data is cached separately with per-source TTLs (OHLCV: 15min, market/sector: 60min, FinViz/TipRanks/fundamentals: 4hr, FMP earnings quality: 4hr). Pass `"force_refresh": true` on `POST /api/analyze` to bypass data caching. Bump `prompt_version` in the `llm_input` dict to bust the LLM narrative cache without manual flushing.

### API Endpoints

The API is mounted at `/api` (see `backend/routers/analysis.py`).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | Run the full 6-stage pipeline. Body: `{ "ticker": "AAPL", "skip_tipranks"?: true, "force_refresh"?: false }` |
| `GET`  | `/api/signals/history` | Most recent signals from PostgreSQL |
| `GET`  | `/api/performance/{ticker}` | Historical signal accuracy vs. live Alpaca price (12-month rolling window). Accepts `?horizon=swing` (default) or `?horizon=position` to filter by signal horizon. |

`skip_tipranks` (default `true`) preserves the free-tier TipRanks rate limit (5 req/min, 50 req/month).

**Response structure** (`AnalysisResponse`):
- `signal`: `SignalOutput` — includes `signals` (`MultiHorizonSignals` with `swing`, `position`, `day_trade` `HorizonSignal` objects), plus `price_range_projection`, `stock_context` (with MA trends), `fundamentals` (with institutional activity), `earnings_quality`, `stocktwits_sentiment`, all narrative fields, and market/sector LLM detail fields (MACRO, RATES & FX, REGIME, rotation momentum, etc.). The deprecated `signal`/`confidence`/`composite_score` fields on `SignalOutput` are retained for backward compatibility — they mirror the **position** signal (6-month horizon).
- `confidence_breakdown`: market/sector/technical/fundamental contributions
- `analysis_details`: raw per-agent analysis dicts

### Data Sources and API Keys

| Service | Required | Key Variables | Notes |
|---|---|---|---|
| **OpenRouter** | Yes | `OPENROUTER_API_KEY` | Powers all LLM narrative generation. Models: `minimax/minimax-m3:free` (primary), `z-ai/glm-5.2:free` (fallback) |
| **Alpaca Market Data** | Yes | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | Stock OHLCV bars (500 days), latest quotes, news headlines (10-day window). Paper trading keys work for all endpoints. |
| **StockTwits** | No | `STOCKTWITS_ACCESS_TOKEN` | Public stream API used (no auth needed for basic sentiment parsing). Token only for higher rate limits. |
| **TipRanks MCP** | No | `TIPRANKS_API_KEY` | Analyst consensus, price targets, smart score. Free tier: 5 req/min, 50 req/month. |
| **FMP** | No | `FMP_API_KEY` | Earnings quality data (revenue, margins, FCF, balance sheet). Free tier: 250 calls/day. Panel hidden if unset. |
| **FRED** | No | `FRED_API_KEY` | Inflation expectations (breakeven rates), Fed funds rate. Free tier available. |

**Non-API data sources:**
- **Yahoo Finance** — Market indexes (S&P 500, Nasdaq, Dow, Russell), Treasury yields, FX rates (DXY, EURUSD, etc.) via direct chart API
- **FinViz** — Fundamental data + sector/industry classification scraped via curl_cffi + BeautifulSoup (no API key, free)

### HTTP Client Note

`curl_cffi` with Chrome TLS impersonation is used for FinViz, StockTwits, and FMP requests.
This bypasses Cloudflare bot detection by producing a real browser JA3/JA4 fingerprint.
`httpx` is intentionally NOT used for these — do not reintroduce it.

### Fundamentals

Real fundamental data is now scored via FinViz + TipRanks concurrent fetch
(see `backend/data/fundamentals_data.py` and `_compute_fundamental_score()`).
The `fundamental_score` feeds into the overall signal weighting (40% of the stock
component). This is clearly labelled in all signal rationale output.

Scoring components (with weights, normalized -1.0 to +1.0, redistributed proportionally if data unavailable):
- Valuation (P/E, forward P/E): 0.25
- Growth (EPS, Sales trajectories): 0.25
- Profitability (margins, ROE, ROA): 0.25
- Financial health (current ratio, debt/equity): 0.08
- Insider sentiment: 0.08
- **Institutional flow** (`inst_trans_pct` — quarterly change in institutional ownership): 0.09 — **NEW**
- Analyst consensus (TipRanks): 0.00 (reported for context, weight zeroed)
- Smart Score (TipRanks): 0.00 (reported for context, weight zeroed)

### Extending the Application
- To add new data sources: Create new modules in `/backend/data/` following existing patterns (Redis cache + TTL, never raises, returns None on failure)
- To add new analysis agents: Create new agent files in `/backend/agents/` and update the graph in `graph.py` (add node, add edge, add conditional edge for error handling)
- To modify signal generation: Update the weighting logic and thresholds in `/backend/signal/engine.py`. Three horizon functions (`compute_swing_signal`, `compute_position_signal`, `compute_day_trade_signal`) each have independent weights, thresholds, and hysteresis. `compute_all_signals()` is the top-level entry point called by the `signal_generation` graph node.
- To add new LLM narrative agents: Follow the caching pattern in `news_sentiment_agent.py` / `overall_analysis_agent.py` (cache key via `redis_client.get_llm_narrative()`, TTL varies by agent)
- To add new UI components: Create new components in `/frontend/src/components/` and import them in `App.tsx`
- To add informational stock metrics: Extend `StockContext`/`StockContextDisplay`/`AnalysisState` in `state.py` + `models.py`, compute in `stock_data.py`, pass through `stock_agent.py` and `routers/analysis.py`, render in a new frontend component

## Running the Full Stack
1. Copy `.env.example` to `.env` and fill in your API keys (see table above 
2. Run `docker-compose up -d` to start PostgreSQL, Redis, and the backend container (auto-runs migrations on boot)
3. Install backend dependencies: `uv sync`
4. For backend hot-reload (without Docker): `uv run uvicorn backend.main:app --reload`
   (run `uv run alembic upgrade head` first if not using the Dockerized backend)
5. Install frontend dependencies: `cd frontend && npm install`
6. Start the frontend: `cd frontend && npm run dev`
7. Access the application at http://localhost:5173

## Troubleshooting

### Common Issues
- **Database connection errors**: Ensure PostgreSQL container is healthy (`docker-compose ps`); check `POSTGRES_SERVER` in `.env` matches Docker service name
- **Redis connection errors**: Ensure Redis container is healthy (`docker-compose ps`); the app continues without caching if Redis is unavailable
- **Backend import errors**: Verify all Python dependencies are installed (`uv pip list`); check `curl-cffi`, `mcp`, `fredapi`, `beautifulsoup4`, `lxml` are present
- **Frontend API connection issues**: Check that the Vite dev server proxy is configured correctly in `vite.config.ts` (should proxy `/api` to `http://localhost:8000`)
- **FinViz 403 errors**: Cloudflare may block scraping; try upgrading curl_cffi (`uv add curl-cffi --upgrade`)
- **TipRanks MCP errors**: Verify `TIPRANKS_API_KEY` is set and valid; free tier is 5 req/min, 50 req/month
- **FMP API errors**: Verify `FMP_API_KEY` is set; free tier is 250 calls/day
- **WebSocket errors**: WebSocket streaming was removed; the `/ws` proxy in `vite.config.ts` is stale and can be safely ignored

### Logs and Debugging
- View backend logs: `docker-compose logs -f backend`
- View frontend logs: Check browser developer console
- Check container status: `docker-compose ps`
- Rebuild containers: `docker-compose build`
- Inspect Redis cache keys: `redis-cli KEYS "*"` (use `redis-cli KEYS "llm:*"` for LLM cache, `redis-cli KEYS "data:*"` for data cache)
- Check LLM cache: `redis-cli GET "llm:market:AAPL"`
- Run tests: `uv run pytest tests/ -v`

## Known Issues

1. **ConfidenceBreakdown weight legend**: `ConfidenceBreakdown.tsx` displays a legend reading "Market 25%, Sector 25%, Stock 50%", but the actual weights in `engine.py` are Market 20%, Sector 30%, Stock 50%. The legend text is hardcoded and does not match the engine constants. Note: the new `HorizonSignalCard` component correctly displays per-horizon weights from the engine, so the new signal cards reflect the accurate weights.

2. **MarketOverview.tsx uses mock data**: The `MarketOverview` and `SectorHeatmap` components on the default view (before analysis) render hardcoded mock data rather than calling the backend API. They are not connected to live data.

3. **Day-trade signal is data-limited**: `compute_day_trade_signal()` is marked EXPERIMENTAL because it operates on daily-bar data only (VIX regime, RSI/Bollinger extremes, volume trend). It cannot replicate genuine intraday analysis (order book, bid-ask spread, opening range, options positioning). It is not persisted to the database. Phase 2 will integrate intraday feeds.


