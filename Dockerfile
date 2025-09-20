FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service and tools
COPY app/ ./app/
COPY tools/ ./tools/

# Optional: enable SVG rendering (Mermaid CLI)
# RUN apt-get update && apt-get install -y nodejs npm && npm i -g @mermaid-js/mermaid-cli && apt-get clean

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
