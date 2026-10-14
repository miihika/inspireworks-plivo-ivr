import re
from urllib.parse import urlsplit
from xml.etree.ElementTree import fromstring
from unittest.mock import patch
from plivo.base import ResponseObject
import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "PUBLIC_BASE_URL": "https://demo.example",
                      "PLIVO_AUTH_ID": "test", "PLIVO_AUTH_TOKEN": "test",
                      "PLIVO_FROM_NUMBER": "+12025550100", "ASSOCIATE_NUMBER": "+12025550102"})
    return app.test_client()


def post(client, url, **data):
    parsed = urlsplit(url)
    response = client.post(parsed.path + ("?" + parsed.query if parsed.query else ""), data={"CallUUID": "call-123", **data})
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    return fromstring(response.data)


def login(client):
    root = post(client, "/verify-otp", Digits="2711")
    return root.find("Redirect").text


def action_url(client, lang):
    root = post(client, login(client))
    root = post(client, root.find("GetDigits").get("action"), Digits="1" if lang == "en" else "2")
    return post(client, root.find("Redirect").text).find("GetDigits").get("action")


@pytest.mark.parametrize("digits", ["0000", "271", "", "1127", "27111"])
def test_wrong_otp_never_unlocks(client, digits):
    root = post(client, "/verify-otp", Digits=digits)
    assert root.find("GetDigits").get("numDigits") == "4"
    assert "verify-otp" in root.find("GetDigits").get("action")
    assert "ticket=" not in str(root.attrib)


def test_otp_timeout_repeats(client):
    root = post(client, "/answer")
    assert "answer?reason=timeout" in root.find("Redirect").text
    assert root.find("GetDigits").get("log") == "false"


@pytest.mark.parametrize("endpoint", ["/language", "/select-language", "/menu", "/action", "/dial-result"])
def test_menu_cannot_bypass_authentication(client, endpoint):
    root = post(client, endpoint, Digits="1")
    assert root.find("Redirect").text.endswith("/answer")


def test_ticket_bound_to_call(client):
    root = post(client, login(client), CallUUID="other-call")
    assert root.find("Redirect").text.endswith("/answer")


def test_invalid_language_and_timeout(client):
    root = post(client, login(client))
    root = post(client, root.find("GetDigits").get("action"), Digits="9")
    assert "Invalid" in root.find("Speak").text
    root = post(client, root.find("Redirect").text)
    assert "No input" in root.find("Speak").text


@pytest.mark.parametrize("lang", ["en", "es"])
def test_playback_and_return(client, lang):
    root = post(client, action_url(client, lang), Digits="1")
    assert root.find("Play").text.endswith(f"message-{lang}.mp3")
    assert client.get(f"/static/audio/message-{lang}.mp3").status_code == 200
    root = post(client, root.find("Redirect").text)
    assert root.find("GetDigits/Speak").get("language") == ("en-US" if lang == "en" else "es-ES")


@pytest.mark.parametrize("lang", ["en", "es"])
def test_invalid_action_and_timeout_keep_language(client, lang):
    root = post(client, action_url(client, lang), Digits="9")
    assert root.find("Speak").get("language") == ("en-US" if lang == "en" else "es-ES")
    root = post(client, root.find("Redirect").text)
    assert root.find("Speak").text
    assert f"lang={lang}" in root.find("GetDigits").get("action")


@pytest.mark.parametrize("status", ["completed", "busy", "failed", "timeout", "no-answer"])
def test_forwarding_and_result(client, status):
    root = post(client, action_url(client, "es"), Digits="2")
    assert root.find("Dial/Number").text == "+12025550102"
    result = post(client, root.find("Dial").get("action"), CallUUID="", DialALegUUID="call-123", DialStatus=status)
    assert result.find("GetDigits") is not None
    assert ("terminado" if status == "completed" else "disponible") in result.find("Speak").text


def token(client):
    return re.search(r'data-token="([^"]+)"', client.get("/").text).group(1)


def test_call_request_uses_provider(client):
    with patch("app.plivo.RestClient") as constructor:
        constructor.return_value.calls.create.return_value = ResponseObject({"request_uuid": "request-123"})
        response = client.post("/api/call", json={"to": "+1 2025550101"}, headers={"X-Demo-Token": token(client)})
        assert response.status_code == 200
        args = constructor.return_value.calls.create.call_args.kwargs
        assert args["to_"] == "+12025550101"
        assert args["answer_url"] == "https://demo.example/answer"
        assert args["answer_method"] == "POST"


def test_invalid_number_and_unauthorized_call(client):
    assert client.post("/api/call", json={"to": "invalid"}, headers={"X-Demo-Token": token(client)}).status_code == 400
    assert client.post("/api/call", json={}).status_code == 403
    assert client.get("/", base_url="https://demo.example").status_code == 403


def test_provider_failure_returns_useful_error(client):
    with patch("app.plivo.RestClient", side_effect=RuntimeError("secret")):
        response = client.post("/api/call", json={"to": "+12025550101"}, headers={"X-Demo-Token": token(client)})
        assert response.status_code == 502
        assert "secret" not in response.text
