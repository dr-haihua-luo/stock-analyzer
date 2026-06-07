# Use Python 3.11 slim image
FROM python:3.11-slim

# Install UV (Astral's Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy the entire project
COPY . .

# Install setuptools and wheel (build dependencies) and then install the project dependencies
RUN uv pip install --system setuptools wheel && uv pip install --system -r pyproject.toml

# Expose the port the app runs on
EXPOSE 8000

# Default command
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]