from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "I am alive"

def run():
  base_port = int(os.environ.get("PORT", 8000))
  for port in range(base_port, base_port + 11):
      try:
          app.run(host='0.0.0.0', port=port)
          break # Muvaffaqiyatli ishga tushsa chiqish
      except Exception as e:
          if "Address already in use" in str(e) or "WinError 10048" in str(e):
               print(f"⚠️ Port {port} band, keyingisiga o'tilmoqda...")
               continue
          else:
               print(f"⚠️ Web server error (Port {port}): {e}")
               break

def keep_alive():
    t = Thread(target=run)
    t.start()
