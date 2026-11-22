FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt
COPY config ./config
COPY o2j ./o2j
RUN mkdir input output && chown 1000:1000 input output

USER 1000:1000
EXPOSE 8765
ENTRYPOINT ["python", "-m", "o2j"]
CMD ["extract"]
