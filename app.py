"""InspireWorks outbound IVR. Run locally with python app.py."""
import os
import re
import secrets
from functools import wraps
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, tostring

import plivo
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

load_dotenv()
# Assignment requires a hardcoded birthdate, including leading zeros if present.
OTP = "2711"
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
TEXT = {
    "en": {
        "menu": "Press 1 to play a short audio message. Press 2 to connect to a live associate.",
        "invalid": "Invalid selection. Please try again.",
        "timeout": "We did not receive your selection. Please try again.",
        "connect": "Please hold while we connect you to a live associate.",
        "unavailable": "The associate is unavailable. Please choose again.",
        "returned": "Your conversation has ended. Please choose another option.",
    },
    "es": {
        "menu": "Presione 1 para escuchar un mensaje de audio. Presione 2 para hablar con un agente.",
        "invalid": "Opción no válida. Inténtelo de nuevo.",
        "timeout": "No recibimos su selección. Inténtelo de nuevo.",
        "connect": "Espere mientras lo conectamos con un agente.",
        "unavailable": "El agente no está disponible. Seleccione otra opción.",
        "returned": "Su conversación ha terminado. Seleccione otra opción.",
    },
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("APP_SECRET") or secrets.token_urlsafe(32),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
        PLIVO_AUTH_ID=os.getenv("PLIVO_AUTH_ID", ""),
        PLIVO_AUTH_TOKEN=os.getenv("PLIVO_AUTH_TOKEN", ""),
        PLIVO_FROM_NUMBER=os.getenv("PLIVO_FROM_NUMBER", ""),
        TO_NUMBER=os.getenv("TO_NUMBER", ""),
        ASSOCIATE_NUMBER=os.getenv("ASSOCIATE_NUMBER", ""),
        AUDIO_URL_EN=os.getenv("AUDIO_URL_EN", ""),
        AUDIO_URL_ES=os.getenv("AUDIO_URL_ES", ""),
    )
    if test_config:
        app.config.update(test_config)
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="ivr-authentication")
    dashboard_token = secrets.token_urlsafe(32)

    def public_url(endpoint, **values):
        base = app.config["PUBLIC_BASE_URL"]
        return base + url_for(endpoint, **values)

    def xml(root):
        return Response(tostring(root, encoding="unicode"), mimetype="application/xml")

    def speak(root, text, lang="en"):
        SubElement(root, "Speak", {"language": "es-ES" if lang == "es" else "en-US"}).text = text

    def redirect(root, endpoint, **values):
        SubElement(root, "Redirect", {"method": "POST"}).text = public_url(endpoint, **values)

    def collect(root, prompt, endpoint, count, fallback, voice_lang="en", **values):
        digits = SubElement(root, "GetDigits", {
            "action": public_url(endpoint, **values), "method": "POST",
            "numDigits": str(count), "timeout": "10", "digitTimeout": "5",
            "retries": "1", "finishOnKey": "#", "redirect": "true", "log": "false",
        })
        speak(digits, prompt, voice_lang)
        # Plivo continues after GetDigits when no digits arrive; explicitly loop.
        redirect(root, fallback, reason="timeout", **values)

    def authenticated(handler):
        @wraps(handler)
        def guarded(*args, **kwargs):
            try:
                payload = signer.loads(request.args.get("ticket", ""), max_age=7200)
                call_id = request.values.get("CallUUID") or request.values.get("DialALegUUID")
                if not call_id or payload["call"] != call_id:
                    raise BadSignature("Ticket is not for this call")
            except (BadSignature, SignatureExpired, KeyError):
                root = Element("Response")
                speak(root, "Please authenticate before accessing the menu.")
                redirect(root, "answer")
                return xml(root)
            return handler(*args, **kwargs)
        return guarded

    def language_menu(message=None):
        root = Element("Response")
        if message:
            speak(root, message)
        collect(root, "Press 1 for English. Para español, presione 2.", "select_language", 1,
                "language", ticket=request.args.get("ticket", ""))
        return xml(root)

    def action_menu(message=None):
        root = Element("Response")
        lang = request.args.get("lang", "en")
        if lang not in TEXT:
            return language_menu("Please select a language.")
        if message:
            speak(root, message, lang)
        collect(root, TEXT[lang]["menu"], "action", 1, "menu", voice_lang=lang, lang=lang,
                ticket=request.args.get("ticket", ""))
        return xml(root)

    @app.get("/")
    def index():
        if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return "Open the dashboard locally at http://127.0.0.1:5000", 403
        return render_template("index.html", target=app.config["TO_NUMBER"],
                               base=app.config["PUBLIC_BASE_URL"], token=dashboard_token)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/api/call")
    def initiate_call():
        # The local UI is allowed to trigger calls; public tunnel visitors are not.
        if request.host.split(":")[0] not in ("127.0.0.1", "localhost") or request.headers.get("X-Demo-Token") != dashboard_token:
            return jsonify(error="Use the local dashboard to initiate calls."), 403
        target = re.sub(r"[\s()-]", "", str((request.get_json(silent=True) or {}).get("to", app.config["TO_NUMBER"])))
        if not PHONE_PATTERN.fullmatch(target):
            return jsonify(error="Enter a phone number with a plus sign and country code."), 400
        base = urlparse(app.config["PUBLIC_BASE_URL"])
        if base.scheme != "https" or not base.netloc:
            return jsonify(error="Set PUBLIC_BASE_URL to your public HTTPS tunnel URL and restart the server."), 400
        if not app.config["PLIVO_AUTH_ID"] or not app.config["PLIVO_AUTH_TOKEN"]:
            return jsonify(error="Set Plivo credentials in .env and restart."), 400
        try:
            client = plivo.RestClient(app.config["PLIVO_AUTH_ID"], app.config["PLIVO_AUTH_TOKEN"])
            result = client.calls.create(
                from_=app.config["PLIVO_FROM_NUMBER"], to_=target,
                answer_url=public_url("answer"), answer_method="POST")
            return jsonify(message="Call requested. Answer your phone.", request_uuid=result.request_uuid)
        except Exception as exc:
            # Do not expose credentials or raw provider request bodies to the browser.
            app.logger.warning("Call initiation failed (%s)", type(exc).__name__)
            return jsonify(error="Plivo rejected the call or could not be reached. Check account balance, number permissions, credentials, and connectivity."), 502

    @app.route("/answer", methods=["GET", "POST"])
    def answer():
        root = Element("Response")
        if request.args.get("reason") == "timeout":
            speak(root, "No input received. Please try again.")
        collect(root, "Welcome to InspireWorks. Please enter your four digit birthdate code, day followed by month.",
                "verify_otp", 4, "answer")
        return xml(root)

    @app.post("/verify-otp")
    def verify_otp():
        root = Element("Response")
        if request.values.get("Digits", "") != OTP:
            speak(root, "Incorrect code. Please try again.")
            collect(root, "Enter your four digit birthdate code.", "verify_otp", 4, "answer")
        elif not request.values.get("CallUUID"):
            speak(root, "The call could not be identified. Please try again.")
            redirect(root, "answer")
        else:
            ticket = signer.dumps({"call": request.values["CallUUID"]})
            speak(root, "Authentication successful.")
            redirect(root, "language", ticket=ticket)
        return xml(root)

    @app.route("/language", methods=["GET", "POST"])
    @authenticated
    def language():
        return language_menu("No input received. Please try again." if request.args.get("reason") == "timeout" else None)

    @app.post("/select-language")
    @authenticated
    def select_language():
        digit = request.values.get("Digits", "")
        if digit not in ("1", "2"):
            return language_menu("Invalid selection. Please try again.")
        root = Element("Response")
        redirect(root, "menu", lang="en" if digit == "1" else "es", ticket=request.args["ticket"])
        return xml(root)

    @app.route("/menu", methods=["GET", "POST"])
    @authenticated
    def menu():
        lang = request.args.get("lang", "en")
        return action_menu(TEXT.get(lang, TEXT["en"])["timeout"] if request.args.get("reason") == "timeout" else None)

    @app.post("/action")
    @authenticated
    def action():
        lang = request.args.get("lang", "en")
        if lang not in TEXT:
            return language_menu("Please select a language.")
        digit = request.values.get("Digits", "")
        if digit not in ("1", "2"):
            return action_menu(TEXT[lang]["invalid"])
        root = Element("Response")
        ticket = request.args["ticket"]
        if digit == "1":
            SubElement(root, "Play").text = app.config["AUDIO_URL_" + lang.upper()] or public_url("static", filename=f"audio/message-{lang}.mp3")
            redirect(root, "menu", lang=lang, ticket=ticket)
        else:
            speak(root, TEXT[lang]["connect"], lang)
            dial = SubElement(root, "Dial", {"action": public_url("dial_result", lang=lang, ticket=ticket),
                                              "method": "POST", "timeout": "25", "callerId": app.config["PLIVO_FROM_NUMBER"]})
            SubElement(dial, "Number").text = app.config["ASSOCIATE_NUMBER"]
        return xml(root)

    @app.post("/dial-result")
    @authenticated
    def dial_result():
        lang = request.args.get("lang", "en")
        texts = TEXT.get(lang, TEXT["en"])
        connected = request.values.get("DialStatus", "").lower() == "completed"
        return action_menu(texts["returned"] if connected else texts["unavailable"])

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
