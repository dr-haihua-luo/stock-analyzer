# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

don't assume. don't hide confusion.surface tradeoff.
minimum code to solve the problem.
touch only what you must.  clean up only your own code.
define success driteria.  loop until verified.

## Repository Overview

This repository contains the SignalForge trading analysis application, a sophisticated trading signal generation system that uses AI agents to analyze market data, sector rotation, and individual stock fundamentals to generate BUY/HOLD/SELL signals.

The application consists of:
- A backend built with Python 3.11, FastAPI, and LangGraph for AI agent orchestration
- A frontend built with React 18, Vite, TypeScript, and TailwindCSS
- Infrastructure components including PostgreSQL, Redis, and Docker Compose
- Integration with OpenRouter API for LLM access (nvidia/nemotron-super-49b-v1:free model)

## Code Structure

### Backend (`/backend`)
- `main.py`: FastAPI application entry point
- `config.py`: Pydantic-based configuration management
- `/agents`: LangGraph agent framework for analysis pipeline
  - `graph.py`: State machine definition
  - `state.py`: Analysis state definitions
  - `market_agent.py`: Macro/volatility analysis (VIX, yield curve)
  - `sector_agent.py`: Sector rotation analysis
  - `stock_agent.py`: Individual stock analysis
  - `llm_client.py`: OpenRouter API integration
- `/signal`: Signal generation components
  - `engine.py`: Weighted scoring engine for BUY/HOLD/SELL signals
  - `models.py`: Pydantic models for signal output and confidence breakdowns
- `/data`: Data collection modules
  - `market_data.py`: VIX, fear/greed, yield curve data
  - `sector_data.py`: Sector ETF performance data
  - `stock_data.py`: Stock OHLCV, fundamentals, technical indicators
- `/cache`: Redis client with typed TTLs
- `/db`: PostgreSQL ORM models and async session management
- `/routers`: API endpoints
  - `analysis.py`: POST /api/analyze, GET /api/signals/history
  - `stream.py`: WebSocket /ws/analysis/{ticker} for real-time updates

### Frontend (`/frontend`)
- `/src/components`: Reusable UI components
  - `SignalCard.tsx`: Displays trading signal and confidence
  - `MarketOverview.tsx`: Shows VIX and yield curve data
  - `SectorHeatmap.tsx`: Visualizes sector rotation performance
  - `StockChart.tsx`: Interactive price charts using Recharts
  - `ConfidenceBreakdown.tsx`: Shows factor contributions to signal confidence
  - `StreamingLog.tsx`: Real-time analysis updates feed
- `/src/hooks`: Custom React hooks
  - `useAnalysis.ts`: Handles API requests for analysis
  - `useWebSocket.ts`: Manages WebSocket connections
- `/src/types`: TypeScript type definitions
  - `signal.ts`: Signal output, confidence breakdown, and request/response types
- `/src/lib`: Utility modules
  - `api.ts`: API service layer

### Infrastructure
- `docker-compose.yml`: Defines services for PostgreSQL, Redis, and backend
- `Dockerfile`: Backend container build instructions
- `pyproject.toml`: UV package management configuration
- `alembic/`: Database migration scripts
- `.env.example`: Template for environment variables

## Development Commands

### Backend Development
```bash
# Start all services (PostgreSQL, Redis, backend)
docker-compose up -d

# Install Python dependencies
uv sync

# Run backend directly (for development)
uv run uvicorn backend.main:app --reload

# Run database migrations
uv run alembic upgrade head
```

### Frontend Development
```bash
# Install frontend dependencies
cd frontend && npm install

# Start frontend development server
cd frontend && npm run dev
```

### Testing and Verification
- Backend API documentation: http://localhost:8000/docs
- Frontend application: http://localhost:5173
- Health check endpoint: http://localhost:8000/health

## Common Tasks

### Understanding the Analysis Pipeline
1. Read `/backend/agents/graph.py` to understand the LangGraph state machine
2. Review `/backend/agents/market_agent.py`, `sector_agent.py`, and `stock_agent.py` for analysis logic
3. Examine `/backend/signal/engine.py` to understand signal generation and confidence scoring

### Alpaca API keys (required for stock data only)

SignalForge uses Alpaca's Market Data API for all stock-level data:
OHLCV bars, real-time quotes, and news headlines.

You can use **Paper Trading keys** — they work for all data endpoints

**Authentication method**: API Key + Secret Key passed directly into
each Alpaca client constructor which alpaca-py handles internally.

**Data plan**: 
The app uses:
- StockHistoricalDataClient → daily bars (6 months), latest quote, snapshot
- NewsClient → last 30 days of headlines per ticker

**Note on fundamentals**: The fundamental_score in SignalForge uses a
price-momentum + 52-week-high proxy instead. This is clearly labelled
in all signal rationale output. To add real fundamentals, replace
`compute_fundamental_score()` in backend/data/stock_data.py with a
call to Polygon.io or Financial Modeling Prep (both have free tiers).

### Extending the Application
- To add new data sources: Create new modules in `/backend/data/` following existing patterns
- To add new analysis agents: Create new agent files in `/backend/agents/` and update the graph in `graph.py`
- To modify signal generation: Update the weighting logic in `/backend/signal/engine.py`
- To add new UI components: Create new components in `/frontend/src/components/` and import them in `App.tsx`

### Running the Full Stack
1. Copy `.env.example` to `.env` and add your OpenRouter API key
2. Run `docker-compose up -d` to start infrastructure services
3. Install backend dependencies with `uv sync`
4. Start the backend with `uv run uvicorn backend.main:app --reload`
5. Install frontend dependencies with `cd frontend && npm install`
6. Start the frontend with `cd frontend && npm run dev`
7. Access the application at http://localhost:5173

## Troubleshooting

### Common Issues
- **Database connection errors**: Ensure PostgreSQL container is healthy (`docker-compose ps`)
- **Redis connection errors**: Ensure Redis container is healthy (`docker-compose ps`)
- **Backend import errors**: Verify all Python dependencies are installed (`uv pip list`)
- **Frontend API connection issues**: Check that the Vite dev server proxy is configured correctly in `vite.config.ts`

### Logs and Debugging
- View backend logs: `docker-compose logs backend`
- View frontend logs: Check browser developer console
- Check container status: `docker-compose ps`
- Rebuild containers: `docker-compose compose build`