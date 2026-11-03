import logging
import os
import re
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, make_response, request
from openai import OpenAI, OpenAIError
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_NAME = os.getenv("BOT_NAME", "Assistente virtual")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CHATBOT_SYSTEM_PROMPT = os.getenv(
    "CHATBOT_SYSTEM_PROMPT", ""
).strip() or (
        f"Você é {BOT_NAME}, um assistente virtual de propósito geral no WhatsApp. "
        "Ajude com dúvidas, explicações, escrita, organização, ideias e tarefas do dia a dia. "
        "Responda no idioma do usuário, com cordialidade e clareza. Seja conciso, faça perguntas "
        "quando faltar contexto e não invente fatos. Se não souber algo, diga isso com transparência."
)
MAX_HISTORY_MESSAGES = max(2, int(os.getenv("MAX_HISTORY_MESSAGES", "12")))
MAX_CONVERSATIONS = max(1, int(os.getenv("MAX_CONVERSATIONS", "1000")))
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").strip()
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")
N8N_TIMEOUT_SECONDS = float(os.getenv("N8N_TIMEOUT_SECONDS", "3"))
if N8N_TIMEOUT_SECONDS <= 0:
    raise ValueError("N8N_TIMEOUT_SECONDS must be greater than zero")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


TWILIO_VALIDATE_SIGNATURE = _environment_flag(
    "TWILIO_VALIDATE_SIGNATURE",
    os.getenv("APP_ENV", "").lower() == "production",
)

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_conversation_history: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
_conversation_locks: dict[str, threading.Lock] = {}
_state_guard = threading.Lock()
_n8n_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="n8n-webhook")


def _twiml_response(message: str) -> str:
    response = MessagingResponse()
    response.message(message)
    return str(response)


def validate_twilio_request() -> bool:
    if not TWILIO_VALIDATE_SIGNATURE:
        return True
    if not TWILIO_AUTH_TOKEN:
        logger.error("Twilio signature validation is enabled but TWILIO_AUTH_TOKEN is missing")
        return False
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(request.url, request.form, signature)


def generate_response(history: list[dict[str, str]]) -> str:
    if openai_client is None:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    completion = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": CHATBOT_SYSTEM_PROMPT}, *history],
    )
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("The AI provider returned an empty response")
    return content.strip()


def deliver_n8n_event(payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = N8N_WEBHOOK_SECRET

    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=N8N_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Delivered n8n event %s", payload["event"])
    except requests.RequestException:
        logger.exception("Could not deliver event %s to n8n", payload["event"])


def dispatch_n8n_event(event_name: str, data: dict[str, Any]) -> Future[None] | None:
    if not N8N_WEBHOOK_URL:
        return None
    payload = {
        "event": event_name,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": "whatsapp-chatbot",
        "data": data,
    }
    try:
        return _n8n_executor.submit(deliver_n8n_event, payload)
    except RuntimeError:
        logger.exception("Could not queue event %s for n8n", event_name)
        return None


def _conversation_lock(sender: str) -> threading.Lock:
    with _state_guard:
        return _conversation_locks.setdefault(sender, threading.Lock())


def _get_history(sender: str) -> list[dict[str, str]]:
    with _state_guard:
        history = _conversation_history.get(sender)
        if history is None:
            return []
        _conversation_history.move_to_end(sender, last=True)
        return list(history)


def _save_history(sender: str, history: list[dict[str, str]]) -> None:
    with _state_guard:
        _conversation_history[sender] = history[-MAX_HISTORY_MESSAGES:]
        _conversation_history.move_to_end(sender, last=True)
        while len(_conversation_history) > MAX_CONVERSATIONS:
            _conversation_history.popitem(last=False)


def _clear_history(sender: str) -> None:
    with _state_guard:
        _conversation_history.pop(sender, None)


def _is_reset_command(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", message.strip().casefold())
    return normalized in {
        "reiniciar",
        "reiniciar conversa",
        "limpar conversa",
        "começar de novo",
        "comecar de novo",
        "reset",
    }


@app.get("/health")
def health() -> Response:
    return jsonify(
        {
            "status": "ok",
            "ai_configured": openai_client is not None,
            "n8n_configured": bool(N8N_WEBHOOK_URL),
        }
    ), 200


@app.post("/whatsapp")
def whatsapp_reply() -> Response:
    if not validate_twilio_request():
        return make_response(jsonify({"error": "Invalid Twilio signature"}), 403)

    incoming_message = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").strip()
    if not incoming_message or not sender:
        return make_response(
            jsonify({"error": "Both From and Body are required"}), 400
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    with _conversation_lock(sender):
        if _is_reset_command(incoming_message):
            _clear_history(sender)
            reply = "Conversa reiniciada. Como posso ajudar?"
        else:
            history = _get_history(sender)
            history.append({"role": "user", "content": incoming_message})
            try:
                reply = generate_response(history)
            except RuntimeError as error:
                logger.error("Chatbot is not ready to answer: %s", error)
                reply = "No momento não consigo responder. Tente novamente em instantes."
            except OpenAIError:
                logger.exception("AI provider request failed")
                reply = "Tive um problema ao responder. Tente novamente em instantes."
            history.append({"role": "assistant", "content": reply})
            _save_history(sender, history)

    dispatch_n8n_event(
        "message.received",
        {"phone": sender, "message": incoming_message, "received_at": timestamp},
    )
    dispatch_n8n_event(
        "message.responded",
        {"phone": sender, "message": incoming_message, "response": reply, "responded_at": timestamp},
    )
    return make_response(
        _twiml_response(reply),
        200,
        {"Content-Type": "application/xml; charset=utf-8"},
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
    )
