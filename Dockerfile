FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build_graph.py schema.json ./

CMD ["python", "build_graph.py"]
