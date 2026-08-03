# SignalForge

A trading-analysis application that uses AI agents to generate **BUY / HOLD / SELL**
signals by combining macro conditions, sector rotation, stock fundamentals &
technicals, and news/social sentiment — then synthesizing everything into a
concise 6-month outlook verdict.

> The application source lives in the `signalforge/` subdirectory. Commands in this
> guide are run from there. This file sits at the repository root.

## Tech Stack

- **Frontend**: React 18 + Vite + TypeScript + TailwindCSS + Recharts
- **Backend**: Python 3.10+ + FastAPI + Pydantic v2
- **Agent Framework**: LangGraph — deterministic state-machine orchestration
- **LLM**: `openai/gpt-oss-20b:free` (primary) + `inclusionai/ling-3.0-flash:free` (fallback) via OpenRouter
- **Data sources**:
  - Alpaca Market Data — stock OHLCV bars, real-time quotes, news (primary stock feed)
  - yfinance — market indexes (S&P 500, Nasdaq) and sector-ETF data
  - FRED (`fredapi`) — interest rates, yield curve, inflation expectations
  - Finviz + TipRanks — fundamentals, analyst ratings, price targets (web / MCP)
  - pandas, numpy, `ta` (RSIIndicator / MACD / BollingerBands) — data wrangling & indicators
- **Cache**: Redis — TTLs per data source **plus** 1-hour caching of LLM narratives
- **Database**: PostgreSQL via SQLAlchemy (async) + asyncpg, with Alembic migrations
- **Package Manager**: UV

## Project Structure

```
signalforge/
├── docker-compose.yml          # postgres, redis, backend
├── pyproject.toml              # uv + dependencies
├── .env.example
├── alembic/                    # database migrations
├── alembic.ini
├── backend/
│   ├── main.py                 # FastAPI app + router inclusion
│   ├── config.py               # Pydantic settings (env vars)
│   ├── agents/                 # LangGraph nodes (see Analysis Pipeline)
│   ├── data/                   # market / sector / stock / sentiment collectors
│   ├── cache/                  # Redis client + typed TTLs
│   ├── db/                     # SQLAlchemy models + async session
│   ├── routers/                # API endpoints
│   └── signal/                 # weighted scoring engine + output models
└── frontend/
    └── src/
        ├── components/         # SignalCard, charts, and result panels
        ├── hooks/              # useAnalysis, usePerformance
        └── types/              # TypeScript models
```

## Analysis Pipeline

The backend runs a six-stage LangGraph pipeline. Each narrative-producing agent
appends a `[tag] …` entry to a shared `reasoning` list, which the API layer
extracts into the structured response fields.

| Stage | Node | Produces |
|---|---|---|
| 1 | `market_analysis` | macro regime (VIX, fear/greed, yield curve, indexes, rates, FX, inflation) → `market_narrative` |
| 2 | `sector_analysis` | sector rotation & momentum → `sector_narrative` |
| 3 | `stock_analysis` | Alpaca OHLCV + technicals (RSI/MACD/Bollinger) + fundamentals → `stock_narrative`; seeds `current_price` into state |
| 4 | `news_sentiment` | Alpaca news headlines + StockTwits → `news_sentiment_narrative` |
| 5 | `signal_generation` | weighted scoring engine → BUY/HOLD/SELL + confidence + composite score |
| 6 | `overall_analysis` *(last)* | synthesizes **all four narratives + the quantitative signal, confidence, composite score, and `current_price`** into a 6-month outlook (`VERDICT` / `REASONING` / `WATCH`) → `overall_analysis_narrative` |

The final `overall_analysis` node is error-isolating: on failure it falls back to
a deterministic verdict (from the computed signal) and never breaks the pipeline.

### LLM response caching
Every narrative-producing agent caches its OpenRouter response in Redis for **1 hour**,
keyed `llm:<agent>:<TICKER>` (e.g. `llm:overall:AAPL`). Re-analyzing the same ticker
within the TTL is served from cache — the LLM is **not** called again. Fetched data is
cached separately with per-source TTLs; pass `"force_refresh": true` on
`POST /api/analyze` to bypass data caching.

## Getting Started

### Prerequisites
- Docker + Docker Compose
- [UV](https://docs.astral.sh/uv/) package manager
- Node.js 18+
- An OpenRouter API key and an Alpaca Market Data key

### Installation
From the `signalforge/` directory:

1. `cp .env.example .env` and fill in your API keys (see table below).
2. `docker-compose up -d` — starts PostgreSQL, Redis, **and** the backend
   (app on `http://localhost:8000`; the container auto-runs `alembic upgrade head`
   on boot).
3. `cd frontend && npm install`
4. Run the services you want:
   - Backend (hot reload): `uv run uvicorn backend.main:app --reload`
     (run `uv run alembic upgrade head` once first if you are *not* using the
     Dockerized backend).
   - Frontend dev server: `npm run dev` (served on `http://localhost:5173`,
     proxies `/api` to the backend).

API docs are available at `http://localhost:8000/docs`.

## Configuration (`.env`)

| Variable | Required | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | Powers every LLM narrative |
| `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` | Yes | Stock bars, quotes, news |
| `DATABASE_URL` | Yes | PostgreSQL async URL |
| `REDIS_URL` | Yes | Redis connection |
| `FMP_API_KEY` | No | Earnings-quality panel (hidden if unset) |
| `TIPRANKS_API_KEY` | No | Analyst ratings (free MCP tier) |
| `FRED_API_KEY` | No | Some rate/inflation series |
| `ALLOWED_ORIGINS` | No | CORS allow-list (default `http://localhost:5173`) |
| `LOG_LEVEL` | No | `INFO` |

## API Endpoints

The API is mounted at `/api` (see `backend/routers/analysis.py`).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | Run the full pipeline for a ticker. Body: `{ "ticker": "AAPL", "skip_tipranks"?: true, "force_refresh"?: false }` |
| `GET`  | `/api/signals/history` | Most recent signals |
| `GET`  | `/api/performance/{ticker}` | Historical signal accuracy vs. the live Alpaca price |

`skip_tipranks` (default `true`) keeps free-tier TipRanks usage low; set it to
`false` for full analyst coverage.

## License

MIT
