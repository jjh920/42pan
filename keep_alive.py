# keep_alive.py
import os
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route("/")
def home():
    return "I'm alive"

def run():
    # Render가 제공하는 PORT를 사용해야 Health Check 통과
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run, daemon=True)  # 데몬 스레드로 백그라운드 실행
    t.start()
