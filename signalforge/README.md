# SignalForge

A sophisticated trading analysis application that uses AI agents to generate trading signals based on macroeconomic data, sector rotation, and individual stock analysis.

## Tech Stack

- **Frontend**: React 18 + Vite + TypeScript + TailwindCSS + Recharts
- **Backend**: Python 3.11 + FastAPI + WebSockets + Pydantic v2
- **Agent Framework**: LangGraph (for deterministic state-machine orchestration)
- **LLM**: nvidia/nemotron-3-super-120b-a12b:free via OpenRouter API
- **Data**: yfinance, fredapi, requests, pandas, numpy, ta (technical indicators)
- **Cache**: Redis (docker-compose) with TTL per data type
- **Database**: PostgreSQL via SQLAlchemy async + asyncpg
- **Package Manager**: UV

## Project Structure

```
signalforge/
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── alembic/
├── alembic.ini
├── backend/
└── frontend/
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- UV package manager
- Node.js 18+
- OpenRouter API key

### Installation

1. Clone the repository
2. Install UV package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. Copy environment variables: `cp .env.example .env`
4. Edit `.env` with your API keys
5. Start the services: `docker-compose up -d`
6. Install backend dependencies: `uv sync`
7. Install frontend dependencies: `cd frontend && npm install`
8. Start the application:
   - Backend: `uv run uvicorn backend.main:app --reload`
   - Frontend: `cd frontend && npm run dev`

## API Endpoints

- `POST /api/analyze` - Trigger analysis for a ticker
- `GET /api/signals/history` - Get historical signals
- `WebSocket /ws/analysis/{ticker}` - Real-time analysis updates

## Development

### Backend
- Runs on `http://localhost:8000`
- API docs available at `http://localhost:8000/docs`

### Frontend
- Runs on `http://localhost:5173`
- Proxy configured to backend API

## License

MIT