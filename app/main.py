from flask import Flask, request, jsonify
from app.telegram_bot import process_telegram_update

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json(force=True)
    process_telegram_update(update)
    return jsonify({"ok": True})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

