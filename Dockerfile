FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY contractgate ./contractgate
RUN pip install --no-cache-dir . && useradd --create-home demo
USER demo
EXPOSE 8000
CMD ["uvicorn", "contractgate.api:app", "--host", "0.0.0.0", "--port", "8000"]
