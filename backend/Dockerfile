FROM python:3.11-slim

WORKDIR /app

# Install only production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /app/app
COPY alembic /app/alembic
COPY .env.example /app/.env.example

# Do NOT commit .env with real secrets; use environment variables at runtime

# Run database migrations on container start
# FastAPI with uvicorn production configuration

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]