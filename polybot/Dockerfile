# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Make port 8443 available to the world outside this container
EXPOSE 8443

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Run app.py when the container launches
CMD ["python3", "app.py"]