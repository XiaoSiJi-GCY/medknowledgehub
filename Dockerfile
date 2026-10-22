FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml requirements-lock.txt /app/
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY . /app
RUN pip install --no-cache-dir --no-build-isolation --no-deps .
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
