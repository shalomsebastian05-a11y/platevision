FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install flask flask-bcrypt flask-sqlalchemy Pillow python-dotenv gunicorn
COPY . .
EXPOSE 5000
CMD ["python3", "app.py"]
