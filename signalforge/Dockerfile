# Use Python 3.11 slim image
FROM python:3.11-slim

# Install UV (Astral's Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy pyproject.toml and install dependencies
COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Default command (can be overridden by docker-compose)
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]