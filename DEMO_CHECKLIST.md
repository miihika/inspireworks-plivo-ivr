# Recording and submission checklist

## Four-minute demo sequence

1. **0:00–0:25:** Introduce InspireWorks and explain outbound calls, birthdate authentication, two menu levels, and Plivo XML.
2. **0:25–1:20:** Show the local dashboard, start the call, answer on speakerphone. Enter wrong OTP `0000`, hear the retry, then enter correct OTP `2711`.
3. **1:20–2:30:** Choose English (`1`), choose audio (`1`), hear the message. The menu returns. Choose forwarding (`2`) and show the connection or observed associate availability.
4. **2:30–3:30:** Start another call. Authenticate, choose Spanish (`2`), demonstrate Spanish prompts/audio (`1`) and forwarding (`2`).
5. **3:30–4:00:** Briefly show XML endpoint code and README. Explain invalid-input/silence retries and the configuration. Do not open `.env` on the recording.

Record actual call behavior. A successful HTTP call request alone does not demonstrate the phone flow. If a supplied associate number is unavailable, disclose the result rather than claiming a completed connection.

## Deliverables

- [ ] Application source, templates, tests, and both audio files.
- [ ] README with setup, credential variable names, running and testing instructions.
- [ ] 3–5 minute video with audible phone interaction.
- [ ] Include the receiver phone number used for the demo in the submission email.
- [ ] Exclude `.env`, `.venv`, caches, logs, and the downloaded tunnel executable from any submission ZIP.

