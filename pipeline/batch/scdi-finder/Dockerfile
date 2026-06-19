# Use an official Python runtime as a parent image (linux/arm64 — built for Graviton Batch)
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY ./src/ .

# Specify the command to run on container start
CMD ["python", "scdi_finder.py"]