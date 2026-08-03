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

define success driteria.  loop until verified.
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
- **Data sources**: Alpaca Market Data (OHLCV, quotes, news), yfinance (indexes, sector ETFs, rates, FX), FRED/fredapi (inflation expectations, Fed funds), Finviz (fundamentals scraping via curl_cffi), TipRanks MCP (analyst ratings, price targets), StockTwits public stream (social sentiment), FMP (earnings quality)
- **Indicators**: pandas / numpy / `ta` library (RSIIndicator, MACD, Bollinger Bands)
- **HTTP**: `curl_cffi` with Chrome TLS impersonation used for FinViz, StockTwits, and FMP requests to bypass Cloudflare bot detection
- **Cache**: Redis — per-source TTLs for data plus 1-hour caching of all LLM narrative responses
- **Database**: PostgreSQL via SQLAlchemy (async) + asyncpg, with Alembic migrations
- **Package Manager**: UV

## Code Structure

### Backend (`/signalforge/backend`)
- `main.py`: FastAPI application entry point (auto-runs DB migrations on startup)
- `config.py`: Pydantic-based configuration management (all env vars)
- `Dockerfile`: Backend container build instructions (Python 3.11-slim + UV)
- `/agents`: LangGraph agent framework — 6-node pipeline (see Analysis Pipeline below)
  - `graph.py`: StateGraph state machine definition and compilation
  - `state.py`: TypedDict state definitions + Pydantic context models
  - `market_agent.py`: Macro/volatility analysis (VIX, fear/greed, yield curve, indexes, rates, FX, inflation)
  - `sector_agent.py`: Sector rotation and momentum analysis
  - `stock_agent.py`: Individual stock analysis (technicals + fundamentals + news)
  - `news_sentiment_agent.py`: Synthesizes Alpaca news + StockTwits sentiment into a narrative
  - `overall_analysis_agent.py`: Final 6-month outlook synthesis across all narratives + signal
  - `llm_client.py`: OpenRouter API integration with primary/fallback model failover
- `/signal`: Signal generation components
  - `engine.py`: Weighted scoring engine with hysteresis and continuous confidence formula
  - `models.py`: Pydantic models (SignalOutput, ConfidenceBreakdown, AnalysisRequest, AnalysisResponse, plus display models for FundamentalsDisplay, EarningsQualityDisplay, StockTwitsSentiment, FinvizSnapshot, TipRanksSnapshot)
- `/data`: Data collection modules
  - `market_data.py`: VIX, fear/greed, yield curve, indexes, rates, FX, inflation (Yahoo Finance + FRED)
  - `sector_data.py`: Sector ETF performance data (11 GICS sectors)
  - `stock_data.py`: Stock OHLCV bars, latest price/quote, news headlines (Alpaca API)
  - `earnings_quality_data.py`: Earnings quality metrics from FMP API (revenue trends, margins, FCF, balance sheet)
  - `earnings_quality_cache.py`: Redis cache wrapper for earnings quality data
  - `finviz_data.py`: Fundamental data scraping from FinViz via curl_cffi + BeautifulSoup
  - `fundamentals_data.py`: Orchestrates concurrent FinViz + TipRanks fetch and computes real fundamental_score
  - `tipranks_data.py`: Analyst consensus, price targets, smart score via TipRanks MCP SDK
  - `stocktwits_data.py`: Social sentiment from StockTwits public stream API (via curl_cffi)
- `/cache`: Redis client (`redis_client.py`) with typed TTLs and LLM narrative caching
  - `get()` / `set()` — general JSON-cached data (market, sector, stock data)
  - `get_raw()` / `set_raw()` — raw string caching (OHLCV DataFrames, fundamentals JSON)
  - `get_llm_narrative()` / `set_llm_narrative()` — 1-hour LLM response cache keyed `llm:<agent>:<ticker>`
  - Redis connection retries with exponential backoff; app continues without cache on failure
- `/db`: PostgreSQL ORM
  - `models.py`: `Signal` model (ticker, signal, confidence, timestamp, price_at_signal, composite_score)
  - `session.py`: Async engine + session factory with auto-managed lifecycle
- `/routers`: API endpoints
  - `analysis.py`: `POST /api/analyze`, `GET /api/signals/history`, `GET /api/performance/{ticker}`

### Frontend (`/signalforge/frontend`)
- `App.tsx`: Main application component — orchestrates analysis flow, displays results, includes performance report modal
- `/src/components`: Reusable UI components
  - `SignalCard.tsx`: Displays the trading signal (BUY/HOLD/SELL) and confidence score
  - `MarketOverview.tsx`: Shows VIX, fear/greed, yield curve, and index data
  - `SectorHeatmap.tsx`: Visualizes sector rotation performance
  - `StockChart.tsx`: Interactive price charts using Recharts
  - `ConfidenceBreakdown.tsx`: Shows market/sector/technical/fundamental factor contributions
  - `FundamentalPanel.tsx`: Displays FinViz + TipRanks fundamental data
  - `EarningsQualityPanel.tsx`: Shows earnings quality metrics (revenue, margins, FCF, balance sheet)
  - `SentimentPanel.tsx`: Displays StockTwits social sentiment breakdown
  - `NewsSentimentPanel.tsx`: Shows synthesized news + sentiment narrative
  - `OverallAnalysisPanel.tsx`: Final 6-month outlook verdict (VERDICT / REASONING / WATCH)
  - `PerformanceReport.tsx`: Historical signal accuracy report (modal)
  - `main.tsx`: React entry point
- `/src/hooks`: Custom React hooks
  - `useAnalysis.ts`: Handles `POST /api/analyze` requests with loading/error states
  - `usePerformance.ts`: Fetches `GET /api/performance/{ticker}` and manages report modal state
- `/src/types`: TypeScript type definitions
  - `signal.ts`: Signal output, confidence breakdown, request/response types, performance report types
- `/src/lib`: Utility modules
  - `api.ts`: API service layer (analyzeTicker, getSignalHistory)
- `vite.config.ts`: Vite config with `/api` proxy to backend on port 8000
- `tailwind.config.ts`: TailwindCSS configuration

### Infrastructure (`/signalforge`)
- `docker-compose.yml`: Defines PostgreSQL, Redis, and backend services; backend container auto-runs Alembic migrations on boot
- `Dockerfile`: Backend container (at `backend/Dockerfile`)
- `pyproject.toml`: UV package management configuration with all dependencies
- `alembic/`: Database migration scripts (2 migrations as of latest)
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
| 1 | `market_analysis` | `market_agent.py` | macro regime (VIX, fear/greed, yield curve, indexes, rates, FX, inflation) → `market_narrative` |
| 2 | `sector_analysis` | `sector_agent.py` | sector rotation & momentum → `sector_narrative` |
| 3 | `stock_analysis` | `stock_agent.py` | Alpaca OHLCV + technicals (RSI/MACD/Bollinger) + FinViz/TipRanks fundamentals → `stock_narrative`; seeds `current_price` into state |
| 4 | `news_sentiment` | `news_sentiment_agent.py` | Alpaca news + StockTwits → `news_sentiment_narrative` |
| 5 | `signal_generation` | `engine.py` | weighted scoring → BUY/HOLD/SELL + confidence + composite score |
| 6 | `overall_analysis` | `overall_analysis_agent.py` | synthesizes all narratives + quantitative signal into 6-month outlook → `overall_analysis_narrative` |

**To understand the pipeline:**
1. Read `/backend/agents/graph.py` — StateGraph definition, node wiring, and error-isolating conditional edges
2. Review `/backend/agents/market_agent.py`, `sector_agent.py`, `stock_agent.py` — analysis logic
3. Review `/backend/agents/news_sentiment_agent.py`, `overall_analysis_agent.py` — synthesis nodes
4. Examine `/backend/signal/engine.py` — weighted scoring with hysteresis (BUY_THRESHOLD=0.6, SELL_THRESHOLD=-0.2, HYSTERESIS=0.03) and continuous confidence formula (`min(abs(composite) / 0.8, 1.0)`)
5. Weights: market 20%, sector 30%, stock 50% (60% technical + 40% fundamental)

### LLM Response Caching

Every narrative-producing agent caches its OpenRouter response in Redis for **1 hour**,
keyed `llm:<agent>:<ticker>` (e.g. `llm:overall:AAPL`). Re-analyzing the same ticker
within the TTL is served from cache — the LLM is **not** called again. Fetched data is
cached separately with per-source TTLs; pass `"force_refresh": true` on
`POST /api/analyze` to bypass data caching.

### API Endpoints

The API is mounted at `/api` (see `backend/routers/analysis.py`).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | Run the full 6-stage pipeline. Body: `{ "ticker": "AAPL", "skip_tipranks"?: true, "force_refresh"?: false }` |
| `GET`  | `/api/signals/history` | Most recent signals from PostgreSQL |
| `GET`  | `/api/performance/{ticker}` | Historical signal accuracy vs. live Alpaca price (12-month rolling window) |

`skip_tipranks` (default `true`) preserves the free-tier TipRanks rate limit (5 req/min, 50 req/month).

### Data Sources and API Keys

| Service | Required | Key Variables | Notes |
|---|---|---|---|
| **OpenRouter** | Yes | `OPENROUTER_API_KEY` | Powers all LLM narrative generation |
| **Alpaca Market Data** | Yes | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | Stock OHLCV bars (6 months), latest quotes, news headlines (15-day window). Paper trading keys work for all endpoints. |
| **StockTwits** | No | `STOCKTWITS_ACCESS_TOKEN` | Public stream API used (no auth needed for basic sentiment parsing). Token only for higher rate limits. |
| **TipRanks MCP** | No | `TIPRANKS_API_KEY` | Analyst consensus, price targets, smart score. Free tier: 5 req/min, 50 req/month. |
| **FMP** | No | `FMP_API_KEY` | Earnings quality data (revenue, margins, FCF, balance sheet). Free tier: 250 calls/day. Panel hidden if unset. |
| **FRED** | No | `FRED_API_KEY` | Inflation expectations (breakeven rates), Fed funds rate. Free tier available. |

**Non-API data sources:**
- **Yahoo Finance** — Market indexes (S&P 500, Nasdaq, Dow, Russell), Treasury yields, FX rates (DXY, EURUSD, etc.) via direct chart API
- **FinViz** — Fundamental data scraped via curl_cffi + BeautifulSoup (no API key, free)

### HTTP Client Note

`curl_cffi` with Chrome TLS impersonation is used for FinViz, StockTwits, and FMP requests.
This bypasses Cloudflare bot detection by producing a real browser JA3/JA4 fingerprint.
`httpx` is intentionally NOT used for these — do not reintroduce it.

### Fundamentals

Real fundamental data is now scored via FinViz + TipRanks concurrent fetch
(see `backend/data/fundamentals_data.py` and `_compute_fundamental_score()`).
The `fundamental_score` feeds into the overall signal weighting (40% of the stock
component). This is clearly labelled in all signal rationale output.

### Extending the Application
- To add new data sources: Create new modules in `/backend/data/` following existing patterns (Redis cache + TTL, never raises, returns None on failure)
- To add new analysis agents: Create new agent files in `/backend/agents/` and update the graph in `graph.py` (add node, add edge, add conditional edge for error handling)
- To modify signal generation: Update the weighting logic and thresholds in `/backend/signal/engine.py`
- To add new LLM narrative agents: Follow the caching pattern in `news_sentiment_agent.py` / `overall_analysis_agent.py` (cache key via `redis_client.get_llm_narrative()`, 1-hour TTL)
- To add new UI components: Create new components in `/frontend/src/components/` and import them in `App.tsx`

### Running the Full Stack
1. Copy `.env.example` to `.env` and fill in your API keys (see table above)
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