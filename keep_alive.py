from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "I am alive"

def run():
  port = int(os.environ.get("PORT", 8000))
  try:
      app.run(host='0.0.0.0', port=port)
  except Exception as e:
      print(f"⚠️ Web server error (Port {port}): {e}")

def keep_alive():
    t = Thread(target=run)
    t.start()
