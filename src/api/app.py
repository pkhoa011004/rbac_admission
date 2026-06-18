# Lab 2 buổi chiều: Flask app với /metrics
import os
import random
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)  # Tự thêm /metrics

ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
VERSION = os.getenv("VERSION", "v1")
SECRET_FILE_PATH = os.getenv("SECRET_FILE_PATH", "/etc/secrets/db-password")

@app.get("/")
def index():
    db_password = "not found"
    if os.path.exists(SECRET_FILE_PATH):
        try:
            with open(SECRET_FILE_PATH, "r") as f:
                db_password = f.read().strip()
        except Exception as e:
            db_password = f"error: {str(e)}"

    if random.random() < ERROR_RATE:
        return jsonify(error="injected", version=VERSION), 500
    return jsonify(ok=True, version=VERSION, db_password=db_password)

@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
