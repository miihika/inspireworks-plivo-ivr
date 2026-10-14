# InspireWorks: Plivo Outbound IVR

A Python/Flask application for the FDE technical assignment. Initiate a real outbound call, authenticate with a hardcoded DDMM birthdate, choose English or Spanish, then play an audio message or connect to the supplied live associate number.

## Requirements

- Python 3.11 or newer
- Windows PowerShell for the automatic launcher, or an HTTPS tunnel for manual setup
- A Plivo account with a voice-enabled source number and permission to call the destination numbers
- Plivo Auth ID and Auth Token
- A receiver phone and an associate/test number, both in international format
- Internet access and sufficient Plivo account balance

## Setup

Download the repository ZIP from GitHub, extract it, and open PowerShell in the extracted project folder. Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` in a text editor and fill in `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_FROM_NUMBER`, `TO_NUMBER`, and `ASSOCIATE_NUMBER`. Use the credentials supplied separately for the assignment or those from your own Plivo account. Real credentials are not included in the repository.

Generate a signing secret:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output into `APP_SECRET` in `.env`. Leave `PUBLIC_BASE_URL` blank when using the automatic launcher. Audio URLs are optional because both language recordings are included.

## Run

In the project folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

The launcher downloads the official Cloudflare tunnel client if needed, starts a public HTTPS tunnel using HTTP/2, updates `PUBLIC_BASE_URL` in `.env`, and starts Flask. Open **http://127.0.0.1:5000** and click **Start demo call**. Keep the terminal running during the demo. Press Ctrl+C to stop. Each launch creates a new public URL and updates the configuration automatically.

### Configuration

| Variable | Purpose |
| --- | --- |
| `PLIVO_AUTH_ID` | Required Plivo account Auth ID |
| `PLIVO_AUTH_TOKEN` | Required Plivo Auth Token |
| `PLIVO_FROM_NUMBER` | Plivo source number, including country code |
| `TO_NUMBER` | Default receiver; can also be entered in the dashboard or CLI |
| `ASSOCIATE_NUMBER` | Live associate destination in international format |
| `PUBLIC_BASE_URL` | Public HTTPS origin; set automatically by the launcher |
| `APP_SECRET` | Random signing secret; configured locally, replace on another computer |
| `AUDIO_URL_EN`, `AUDIO_URL_ES` | Optional public audio URLs; defaults are bundled English/Spanish MP3 files |

The OTP is intentionally hardcoded as a string in `app.py`, per the assignment. It is not generated or sent by SMS. No database is needed. Phone numbers must include country codes. The demo account must permit calling the receiver and associate destinations and have sufficient balance.

## Manual start / alternative tunnel

If Cloudflare cannot establish a tunnel, use an installed ngrok client:

```powershell
ngrok http 5000
```

Copy its HTTPS URL to `PUBLIC_BASE_URL` in `.env`. In another terminal start:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. Restart `app.py` after changing configuration. The public root page is intentionally unavailable: the call-triggering dashboard is for local use. Plivo can still access the public XML endpoints and audio files.

To initiate from the CLI while the server is running:

```powershell
.\.venv\Scripts\python.exe make_call.py
# Or override the destination:
.\.venv\Scripts\python.exe make_call.py --to YOUR_RECEIVER_NUMBER_WITH_COUNTRY_CODE
```

## Call behavior and endpoints

1. Local dashboard or CLI requests an outbound call through the Plivo SDK.
2. On answer, Plivo requests `/answer`, which returns Plivo XML containing `GetDigits` and a spoken OTP prompt.
3. `/verify-otp` loops for wrong, incomplete, or missing OTP input. Correct input creates a signed ticket bound to the call UUID and redirects to the language menu.
4. `/language` and `/select-language` collect one digit: 1 English, 2 Spanish. Invalid input and silence repeat the current menu.
5. `/menu` and `/action` collect one digit in the selected language: 1 audio, 2 live associate. Invalid input and silence preserve the selected language and repeat the action menu.
6. Audio uses `<Play>` with a publicly accessible MP3 served through the tunnel. Playback returns to the action menu so both actions can be demonstrated in one call.
7. Forwarding uses `<Dial><Number>` with the provided associate destination. `/dial-result` returns to the menu after a conversation or explains unavailability after busy, timeout, or failure.

All IVR endpoints return `application/xml`. Callback URLs are absolute and use the public origin. POST methods are explicitly set. OTP collection disables Plivo digit logging. Signed call tickets prevent menu access before OTP authentication and prevent a ticket from being reused for another call. This is an assignment demo: authentication uses the required birthdate, not a production identity system.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests exercise wrong OTP, successful authentication, unauthorized menu access, call-specific tickets, English/Spanish branches, invalid choices, silence, audio files, forwarding results, and mocked outbound API requests. They do not place billable calls. A real phone test is still required to confirm carrier delivery, audible prompts, keypad recognition, and associate availability.

### Real phone test checklist

- Start a call and answer the configured receiver phone.
- Enter `0000`, confirm retry, then enter `2711`.
- Enter `9` at the language menu, confirm retry, then choose `1`.
- Enter `9` at the action menu, confirm retry, then choose `1` and hear the English audio.
- After playback choose `2`, verify that the associate rings/connects. If unavailable, verify the fallback menu.
- Start a second call, authenticate, choose `2` for Spanish, then `1` for Spanish audio and `2` for forwarding.
- Test silence at OTP and both menus; each should repeat its current prompt.

## Required 3–5 minute video

See `DEMO_CHECKLIST.md` for the recording sequence and submission checklist. The code does not create a video of a phone interaction: record the real call after testing. Keep secrets off-screen. Use speakerphone or another recording source so the IVR audio is audible.

## Repository contents

`app.py` contains the Flask routes, Plivo API integration, OTP validation, and XML call flow. `make_call.py` provides a CLI trigger. `templates/index.html` provides the local dashboard. `static/audio/` contains the English and Spanish MP3 recordings. `tests/test_ivr.py` covers the call branches and error cases. `run.ps1` handles the Windows HTTPS tunnel and server startup.

Only `.env.example` contains configuration placeholders. Keep `.env`, local logs, virtual environments, and caches out of the repository. The hardcoded birthdate OTP is part of the required demonstration and is visible in `app.py`.

## Troubleshooting

- **Call does not arrive:** verify credentials, balance, source number permissions, receiver number, and destination restrictions in the Plivo account. The dashboard reports provider failures without exposing credentials.
- **Call arrives but is silent/ends:** check tunnel availability, `PUBLIC_BASE_URL`, Flask terminal errors, and Plivo call/debug logs. Callback URLs must reach this machine.
- **Audio fails:** open the public URL followed by `/static/audio/message-en.mp3` or `/static/audio/message-es.mp3`. Both must return audio without authentication.
- **Associate does not answer:** the code can dial the supplied number but cannot ensure a person answers it. Document the observed status; the assignment permits an alternative test/placeholder associate number if necessary.
- **Port 5000 in use:** stop the earlier Flask instance before restarting. Do not run multiple launchers simultaneously.
- **Tunnel fails:** inspect `tools/tunnel.log`, or use the manual ngrok setup.

## Source references

- [Plivo outbound call quickstart](https://www.plivo.com/docs/voice/quickstart/quickstart)
- [DTMF collection and no-input behavior](https://www.plivo.com/docs/voice/xml/input)
- [Dial, Redirect, and dial-result parameters](https://www.plivo.com/docs/voice/xml/routing)
- [Speak language support and Play](https://www.plivo.com/docs/voice/xml/audio-output)
