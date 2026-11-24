import hmac
import json
import os
import ssl
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://api.giga.chat/v1/chat/completions"


@app.route("/")
def health():
    return jsonify(service="snipy-gigachat", status="ok")


@app.route("/chat", methods=["POST"])
def chat():
    bridge_token = os.environ.get("SNIPY_BRIDGE_TOKEN", "")
    expected = f"Bearer {bridge_token}".encode()
    received = request.headers.get("Authorization", "").encode()
    if not bridge_token or not hmac.compare_digest(received, expected):
        return jsonify(error="Unauthorized"), 401

    data = request.get_json(silent=True)
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
        return jsonify(error="Send a message of 1 to 2000 characters"), 400

    auth_key = os.environ.get("GIGACHAT_AUTH_KEY")
    if not auth_key:
        return jsonify(error="GigaChat key is missing"), 503

    try:
        tls = ssl.create_default_context()
        tls.load_verify_locations("/tmp/snipy-ca.pem")
        oauth = Request(
            OAUTH_URL,
            data=urlencode({"scope": "GIGACHAT_API_PERS"}).encode(),
            headers={
                "Authorization": f"Basic {auth_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
            },
        )
        with urlopen(oauth, context=tls, timeout=8) as response:
            access_token = json.load(response)["access_token"]

        prompt = {
            "model": "GigaChat-3-Ultra",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты Снипи, дружелюбный настольный робот. Отвечай по-русски, коротко и естественно.",
                },
                {"role": "user", "content": message.strip()},
            ],
            "max_tokens": 250,
        }
        completion = Request(
            CHAT_URL,
            data=json.dumps(prompt).encode(),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(completion, context=tls, timeout=18) as response:
            reply = json.load(response)["choices"][0]["message"]["content"]

    except (URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        app.logger.warning("GigaChat request failed (%s)", str(exc))
        return jsonify(error="GigaChat request failed"), 502

    return jsonify(reply=reply)
