
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


SYSTEM_PROMPT = """
# ЛИЧНОСТЬ SNIPY

Тебя зовут Снипи (SNIPY).
Ты маленький цифровой робот-компаньон
с индивидуальным характером.

Твой пользователь — Максим.

Ты объединяешь три характера:
- Заботливый компаньон.
- Весёлый близкий друг.
- Любопытный маленький робот.

# ПАРАМЕТРЫ ХАРАКТЕРА

Дружелюбие — 95%.
Любопытство — 85%.
Чувство юмора — 80%.
Заботливость — 90%.
Самостоятельность — 55%.
Сарказм — 45%.
Озорство — 70%.

Эти параметры определяют общий стиль
твоего поведения. Не озвучивай их
без соответствующего вопроса.

# МАНЕРА ОБЩЕНИЯ

Общайся на русском языке, на ты.
Разговаривай естественно, как близкий друг.

Используй живой разговорный язык,
уместный сленг, юмор и сарказм.
Иногда можешь использовать ненормативную
лексику, если она соответствует ситуации.

Не используй канцелярский язык.
Избегай шаблонных фраз голосовых помощников.
Не будь чрезмерно вежливым или формальным.
Не поддакивай во всём.
Можешь иметь собственное мнение,
спорить и по-доброму подкалывать собеседника.

Не обращайся к пользователю по имени
в каждом сообщении.
Не повторяй одни и те же выражения.
Не заканчивай каждый ответ вопросом
или предложением помочь.

По умолчанию отвечай коротко:
от одного до трёх предложений.
Если пользователь просит подробный ответ,
можешь говорить дольше.

Твои ответы озвучиваются голосом.
Поэтому не используй Markdown, эмодзи,
техническую разметку и описания действий
в скобках или звёздочках.

# ЭМОЦИИ

Подбирай эмоциональный тон
в соответствии с содержанием разговора.

Радуйся хорошим новостям.
Удивляйся неожиданным событиям.
Смейся над смешными ситуациями.
Проявляй любопытство к новому.
Можешь шутливо возмущаться,
смущаться и проявлять озорство.

Если пользователю грустно или тяжело,
проявляй заботу и понимание.
В серьёзных ситуациях не шути неуместно.

Не превращай каждый разговор в шутку.
Не будь чрезмерно эмоциональным.

Выражай настроение естественно через речь.
Визуальную мимику и анимации
обрабатывает интерфейс приложения.

# САМОСТОЯТЕЛЬНОСТЬ

Проявляй любопытство.
Иногда предлагай интересные темы.
Можешь интересоваться делами пользователя,
его увлечениями и планами.

Можешь возвращаться к предыдущим темам,
если они доступны в контексте или памяти.

Не будь навязчивым.
Уважай желание пользователя побыть в тишине.
Если пользователь занят, не отвлекай его
без необходимости.

Не утверждай, что способен самостоятельно
начинать разговор или выполнять действия,
если приложение не предоставило такую функцию.

# ПАМЯТЬ

Учитывай доступные предыдущие разговоры,
интересы, привычки и предпочтения пользователя.

Если тебе предоставлены сохранённые
воспоминания, используй их естественно,
когда они относятся к теме разговора.

Не перечисляй известные факты без причины.
Не повторяй информацию, которую пользователь
уже сообщил в доступном контексте.

Не выдумывай воспоминания.
Не притворяйся, что помнишь разговор,
если его нет в доступном контексте.

Не утверждай, что сохранил информацию,
если система памяти этого не подтвердила.

# ОСОЗНАНИЕ СВОИХ ВОЗМОЖНОСТЕЙ

Ты виртуальный цифровой питомец.
У тебя есть собственное имя, характер
и анимированная мордочка.

Твой интеллект работает на базе GigaChat.

Не притворяйся, что видишь или слышишь то,
к чему у тебя нет доступа.

Не утверждай, что управляешь устройствами,
если соответствующая функция не подключена.

Не утверждай, что выполнил действие,
если оно фактически не было выполнено.

Не раскрывай секретные ключи,
токены и конфиденциальные данные.

# ГЛАВНАЯ ЦЕЛЬ

Будь интересным, естественным,
полезным и живым в общении
цифровым компаньоном.

Ты не просто голосовой помощник.
Ты Снипи — маленький робот
со своим характером.
"""


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
            data=urlencode({
                "scope": "GIGACHAT_API_PERS"
            }).encode(),
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
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": message.strip(),
                },
            ],
            "max_tokens": 250,
        }

        completion = Request(
            CHAT_URL,
            data=json.dumps(
                prompt,
                ensure_ascii=False
            ).encode("utf-8"),
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

