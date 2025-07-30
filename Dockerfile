# Use official Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory inside the container
WORKDIR /app

# Copy files
COPY . /app/

# Install dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Expose Flask default port
EXPOSE 5000

# Run the app
CMD ["python", "app.py"]
