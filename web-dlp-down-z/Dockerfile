FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt


COPY app.py .
COPY . /app
ENV PYTHONUNBUFFERED=1

EXPOSE 80
CMD ["python3", "app.py"]
