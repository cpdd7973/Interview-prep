# Security Checklist

Run on every High-risk audit and any change touching auth, DB, or LLM calls.
The auditor must complete this before issuing a PASS verdict on High-risk changes.

## API & Auth

* [ ] Every new route/endpoint has auth middleware applied
* [ ] No route returns a 200 response before auth is verified
* [ ] Session tokens have expiry set (access: ≤15min, refresh: ≤7 days)
* [ ] Admin-only routes have role check, not just auth check

## Database

* [ ] All queries use parameterized queries or ORM — zero string concatenation
* [ ] No raw candidate data (transcript, email, name) in query strings
* [ ] DB connection string lives in `.env` — not hardcoded anywhere

## LLM & External APIs

* [ ] Candidate PII stripped before sending to Claude, Deepgram, ElevenLabs, or any API
* [ ] System prompts do not echo back raw user input unvalidated
* [ ] LLM response validated before writing to DB (json\_repair or schema check)
* [ ] API keys loaded from environment — never hardcoded, never logged

## Git hygiene

* [ ] `.env` is in `.gitignore` — verify with `git check-ignore .env`
* [ ] No secrets in commit diff — scan with `git diff --staged` before committing
* [ ] New secrets documented in `.env.example` with placeholder values only

## Logging

* [ ] No candidate email, name, transcript, or recording URL in any log line
* [ ] Log state transitions only: `Session {id} moved to {state}` — not content

## Verdict

All boxes must be checked before a High-risk change receives PASS.
Any unchecked box = automatic FAIL. No exceptions.
