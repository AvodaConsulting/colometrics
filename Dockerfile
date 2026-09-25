FROM python:3.12-slim

WORKDIR /app

# Application code and pre-built morphology index (CC-BY, see README/About)
COPY server.py colometry.py hebrew.py morphology.py sefaria_client.py book_index.json ./
COPY static ./static
COPY morph_data ./morph_data

# Render (and most PaaS) inject PORT; listen on all interfaces
ENV HOST=0.0.0.0 \
    PORT=10000

EXPOSE 10000

CMD ["python", "server.py"]
