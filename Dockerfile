FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy validation script and schemas
COPY tools/ tools/
COPY schemas/ schemas/
COPY data/ data/

# Run validation by default
CMD ["python", "tools/validate.py"]