# RAG Q&A API for the Hamburg working-student job postings.
#   docker build -t hamburg-werkstudent-rag .
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY hamburg-werkstudent-rag
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# CPU-only PyTorch: the default wheel bundles CUDA libraries (~2 GB) this service never uses.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0

COPY requirements.txt requirements-rag.txt ./
RUN pip install -r requirements-rag.txt

# Bake the embedding model into the image: the container starts fast and needs no internet
# for embeddings. After this step the Hugging Face hub is switched to offline mode.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-small', device='cpu')"
ENV HF_HUB_OFFLINE=1

COPY src/ src/
COPY dictionaries/ dictionaries/
COPY rag/ rag/
# Build the index from the committed history (structured fields only, no ad texts).
# Mount data/rag_index.db at runtime to serve a newer index without rebuilding the image.
COPY data/history.db data/history.db
RUN python -m rag.index

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "rag.api:app", "--host", "0.0.0.0", "--port", "8000"]
