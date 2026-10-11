FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
# insightface compile une extension Cython et importe numpy pendant son build.
RUN pip install --no-cache-dir setuptools wheel cython==3.0.11 numpy==1.26.4 \
 && pip install --no-cache-dir --no-build-isolation insightface==0.7.3 \
 && pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
EXPOSE 4545
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "4545"]
