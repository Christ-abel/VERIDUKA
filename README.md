# VeriDuka

VeriDuka is a trust check for Kenyan online shops. A buyer can look up a paybill, phone number, Instagram handle, KRA PIN, or shop name and see one score, from 0 to 100, before sending money on M-Pesa.

The score mixes two kinds of evidence. The first is a legal record: an active KRA PIN or a registered business name. The second is what buyers reported, after the classifier accepts the text. The same score answers a text message, so someone with a feature phone can check a shop without opening the website. Instagram, Facebook, and TikTok are links on the shop so a buyer can read those reviews on the platform.

This is a working prototype. The bundled BRS and KRA records are a local mock, and ThriveWave SMS stays mocked until you turn live dispatch on. The shape of the product is real: search, dossier, report, public page links, and SMS all share one score.

## The problem

A lot of Kenyan shopping now happens in Instagram comments, WhatsApp chats, and paybill screenshots. A polished page can belong to a registered company or to a ghost shop that disappears after payment. Star ratings on their own are easy to flood. A company search on its own misses the shops that never registered.

VeriDuka treats those as noise and signal:

- **Signal** is a matching legal record plus reviews that include a public proof link.
- **Noise** is spam, a comment with no post link, or a burst of praise that has already hit the cap.

## What a buyer can do

1. Search by paybill, phone, `@handle`, KRA PIN, or name.
2. Read the gauge, the band, and the advice (pay normally, pay on delivery, or do not pay upfront).
3. Check badges for BRS, KRA, and M-Pesa.
4. Open the legal record, incident reports, public pages, and the service rating.
5. File a new report. The classifier previews the category before the report is saved.
6. Open Public pages and read saved reviews one by one, with no new analysis.
7. Text `VERIFY` for the score, or `COMMENTS` and then `NEXT` to read those reviews on a feature phone.
8. Register a shop from the header, or by texting `REGISTER Name, 07..., paybill`. A new shop starts at 50.

If the identifier is unknown, a report can open a shadow shop. That profile starts with no legal record. A later registry check can attach one.

## Trust score

The formula is named `signal-v1`. It starts at **50** and stays between **0 and 100**.

| Evidence | Effect |
| --- | --- |
| Active KRA PIN or registered BRS | +25, once |
| Verified positive review | +5 each, capped at +20 |
| Unresolved scam | −20 |
| Delayed delivery, non-delivery, or poor service | −5 |
| Negative report newer than 30 days | that penalty counts double |
| Spam, or a social comment with no public link | saved, and the score does not move |
| M-Pesa confirmation code already used | saved, and the score does not move |

Praise does not get a recency bonus. Only penalties double, so a fresh complaint is louder than an old one. Extra praise after the +20 cap still shows in the service rating, with 0 points and a note that the cap is reached.

| Score | Band | Advice |
| --- | --- | --- |
| 80 to 100 | Verified signal | Safe to order via M-Pesa |
| 50 to 79 | Moderate risk | Use pay on delivery or escrow before sending the full amount |
| 0 to 49 | High noise / fraud alert | High risk of a ghost vendor. Do not pay upfront |

A positive review counts toward the score when it has a proof link and the classifier is confident it is praise. A pending KRA PIN or a pending business name is shown on the legal tab, and it does not earn the +25.

A pasted M-Pesa confirmation code, such as `QK72H8L9P0` at the start of a Safaricom SMS, is hashed and stored with the report. The first report to carry that code can still move the score. The same code filed again, including on a different shop, stays on file with a written reason and adds nothing. The raw code is not given its own field.

On a fresh database the three seeded shops land at:

| Shop | Score | Why |
| --- | --- | --- |
| Nairobi Tech Hub Electronics | 95 | 50, plus 25 for an active registry match, plus the +20 praise cap |
| Mama Boaz Organic Veggies | 65 | 50, plus the +20 praise cap, minus 5 for an older late delivery. The registry file is pending |
| Trendy Clothez Kenya | 25 | 50, minus 20 for an unresolved scam, minus 5 for a delivery complaint. Two spam texts are stored and ignored |

## Public pages, not a social login

This prototype does not have Meta or TikTok access, so it does not pull comments. Each shop stores an Instagram handle, a Facebook page, and a TikTok handle. The Public pages tab turns those into links:

- `https://www.instagram.com/{handle}/`
- `https://www.facebook.com/{page}`
- `https://www.tiktok.com/@{handle}`

A buyer who can open those apps reads the live page there. Those visits do not change the trust score.

A buyer who only has a feature phone, or who just saw a poster, does not need those apps. Public pages has a reader, and SMS has `COMMENTS`, then `NEXT`. Both walk the reviews already saved on the shop, one at a time, in the words they were written. That reader does not run the classifier and does not move the score. A review moves the score only when someone files it with Add a report and the classifier accepts it.

## Register a shop

Choose **Register a shop** in the header, or text:

```text
REGISTER Kayole Greens, 0711222333, 556677
```

The shop is added at a score of 50, with no KRA or BRS bonus. The form can also store Instagram, Facebook, and TikTok handles, which become the public links above. A paybill or phone that is already on file is refused, so a shop cannot register a second copy of an existing till.

A shop can also answer a report in public. The reply sits under the complaint. It does not change the score. A scam stops costing points only after a reviewer marks that report resolved.

A shop that later connects its own WhatsApp Business number can forward messages it is allowed to share. `POST /api/v1/whatsapp/connect` stores that number. The webhook ignores every other number. Those messages can move the score only when they include a public link and the classifier accepts them. The feature-phone reader still shows saved text without rescoring it.

An optional Graph API path remains in `backend/social.py` for a later deployment that has a shop's own token. The dashboard does not call it.

## SMS

ThriveWave carries the same check to a handset. The dashboard includes a phone sandbox. Inbound texts hit `POST /api/v1/sms/webhook` as JSON, form data, or raw text.

| Text | Reply |
| --- | --- |
| `HELP` | VERIFY, COMMENTS, NEXT, and REGISTER |
| `VERIFY 400200` | Shop name, score, and band, in 160 characters or fewer. Says when reviews can be read |
| `COMMENTS 400200` | The first saved review, with no score change |
| `NEXT` | The next review for the shop you just opened |
| `REGISTER Kayole Greens, 0711222333, 556677` | Puts that shop on file at 50 |
| `VERIFY 522522` | No trusted record. Do not pay upfront |

`THRIVEWAVE_LIVE=false` returns a mock dispatch receipt. Set the API key and `THRIVEWAVE_LIVE=true` when a real ThriveWave route is available.

## What is live and what is mocked

| Piece | Today |
| --- | --- |
| Search, score, reports, dossier, shop registration | Live, stored in SQLite |
| Comment reader and SMS COMMENTS | Live. Shows saved reviews. Does not rescore them |
| Comment classifier | Live, rule based |
| Instagram, Facebook, and TikTok links | Live. The buyer opens the page. Comments are not imported |
| Instagram sync | Optional code path only. The dashboard does not call it without a token |
| BRS and KRA | Local mock of three official records. `KRA_*` and `BRS_*` are reserved for a real client |
| M-Pesa till name | Seeded badge when Daraja keys are empty. With Daraja configured, a lookup must match the KRA/BRS registered name for the badge to show |
| ThriveWave | Mock dispatch until `THRIVEWAVE_LIVE=true` |

The mock registry includes a decoy company, Savanna Hardware Limited in Mombasa, so a PIN from one business is not stamped onto an unrelated shop.

## Tech stack

The dashboard is a React 18 single page app, built with Vite 6 and styled with Tailwind CSS 3. The API is Python: FastAPI, Pydantic, and SQLAlchemy on SQLite, served by Uvicorn. `python-dotenv` loads `.env`.

Search, the trust score, reports, and SMS all go through that one API. The browser talks to it in development through the Vite proxy. A hosted deploy can skip the proxy and serve the built dashboard from the same FastAPI process.

Docker and Docker Compose are optional, for a single container on a host such as RumptyCloud. Day to day use runs with PowerShell (`start.ps1`) or `start.bat`, plus Node.js and Python.

## Project layout

```
VERIDUKA/
├── start.ps1                 # Windows start: env, API, dashboard
├── start.bat
├── .env.example
├── Dockerfile                # optional single container
├── docker-compose.yml
├── backend/
│   ├── main.py               # HTTP API
│   ├── database.py           # SQLite, search, seed shops
│   ├── models.py
│   ├── schemas.py
│   ├── scoring.py            # signal-v1
│   ├── receipts.py           # one M-Pesa confirmation code, one shop
│   ├── classifier.py
│   ├── reading.py            # plain review text, not a score input
│   ├── social.py             # optional import, unused by the dashboard
│   ├── thrivewave.py
│   └── config.py             # loads .env
└── frontend/
    └── src/                  # React + Tailwind dashboard
```

## Run it

You need Python 3.11+ and Node.js 20+. Docker is not required.

From this folder:

```powershell
.\start.ps1
```

Or double click `start.bat`. The script creates `.env` from `.env.example` when needed, creates the Python virtualenv, installs dependencies, and opens http://localhost:5173.

API docs: http://127.0.0.1:8000/docs.

To run the two processes yourself:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

The first API start creates `backend/veriduka.db` and seeds the three shops. Delete that file if you want a clean seed again.

### Try these

| Lookup | What you should see |
| --- | --- |
| Paybill `400200` | Nairobi Tech Hub Electronics, legal match, verified signal |
| `@trendyclothez_ke` | Trendy Clothez Kenya, no registry match, fraud alert |
| `0722113344` | Mama Boaz Organic Veggies, BRS pending, moderate risk |
| SMS `COMMENTS 400200` then `NEXT` | Reviews one at a time, score unchanged |
| SMS `VERIFY 522522` | No record. Do not pay upfront |

Reporter phones are masked on the dossier (`07****01`). The shop's own phone is shown in full, because that is how buyers reach it.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/search?q=` | Directory match on name, paybill, phone, handle, or PIN |
| `GET` | `/api/v1/vendor/{id}` | Dossier, breakdown, and reports |
| `POST` | `/api/v1/classify` | Preview a report category |
| `POST` | `/api/v1/vendors` | Register a shop. Score starts at 50 |
| `GET` | `/api/v1/vendor/{id}/reading` | Saved reviews in reading order, not rescored |
| `POST` | `/api/v1/reports` | Save a buyer report and return the new score |
| `POST` | `/api/v1/reports/{id}/replies` | Public merchant reply. Does not change the score |
| `POST` | `/api/v1/reports/{id}/resolve` | Reviewer marks a scam resolved so the penalty stops |
| `POST` | `/api/v1/verify-legal` | Recheck a shop against the registry |
| `POST` | `/api/v1/social/import` | Import pasted comments |
| `POST` | `/api/v1/social/sync` | Pull comments for a connected Instagram account |
| `POST` | `/api/v1/sms/webhook` | ThriveWave inbound SMS |
| `POST` | `/api/v1/whatsapp/connect` | A shop connects its own WhatsApp Business number |
| `POST` | `/api/v1/whatsapp/webhook` | Messages from that connected number only |

## Configuration

Copy `.env.example` to `.env`. Empty values keep the built-in mocks. `.env` is gitignored.

The Daraja till-name check uses OAuth and requires the name-inquiry endpoint to be enabled for your Daraja app. Recheck a vendor's legal details from the dossier to query its paybill. A badge is shown only when the returned name matches the official KRA/BRS registered name and that record is active or registered. When both consumer credentials are empty, the seeded M-Pesa badge behavior is unchanged.

| Variable | What it unlocks |
| --- | --- |
| `PORT` | API port. Default `8000` |
| `DATABASE_URL` | Leave unset locally so the API uses `backend/veriduka.db` |
| `THRIVEWAVE_API_URL`, `THRIVEWAVE_API_KEY`, `THRIVEWAVE_SENDER_ID`, `THRIVEWAVE_CALLBACK_URL` | SMS route |
| `THRIVEWAVE_LIVE` | `true` sends real dispatches. `false` returns a mock receipt |
| `META_GRAPH_VERSION` | Graph API version, default `v21.0` |
| `META_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Comments on an Instagram account that authorized this app |
| `KRA_API_URL`, `KRA_API_KEY`, `BRS_API_URL`, `BRS_API_KEY` | Reserved for live registry clients |
| `DARAJA_CONSUMER_KEY`, `DARAJA_CONSUMER_SECRET`, `DARAJA_ENVIRONMENT` | Daraja OAuth credentials and environment (`sandbox` or `production`) |
| `DARAJA_NAME_LOOKUP_URL` | Enabled Daraja name-inquiry endpoint. VeriDuka sends `POST {"ShortCode":"<paybill>"}` with a bearer token and expects `{"MerchantName":"<registered name>"}` |
| `REVIEW_API_KEY` | When set, resolving a report or connecting WhatsApp requires this value in `X-Review-Key` |
| `WHATSAPP_VERIFY_TOKEN` | Handshake token for a shop's own WhatsApp webhook. Empty disables the handshake |
| `WHATSAPP_APP_SECRET` | When set, WhatsApp deliveries must carry a valid `X-Hub-Signature-256` |

## Contributing

Issues are the best place to start. Each one is a slice that makes the check harder to fake:

1. [Match an M-Pesa till name to the registered business](https://github.com/Christ-abel/VERIDUKA/issues/1)
2. [Classify reports and SMS written in Swahili](https://github.com/Christ-abel/VERIDUKA/issues/2)
3. [Weight reports by reporter reputation](https://github.com/Christ-abel/VERIDUKA/issues/3)
4. [Reject a reused M-Pesa receipt](https://github.com/Christ-abel/VERIDUKA/issues/4) (done)
5. [Let a merchant post a public reply](https://github.com/Christ-abel/VERIDUKA/issues/5)
6. [Receive WhatsApp messages a shop opts in to share](https://github.com/Christ-abel/VERIDUKA/issues/6)

Fork the repo, run `.\start.ps1`, and open a pull request against `main`. Keep secrets out of the diff. A new integration should keep working when its env values are empty, so the demo still runs for the next person.

Ideas beyond those six, if you want a larger project: a USSD menu for feature phones, a county map of recent scam reports, a graph of shops that share one phone or paybill, and a weekly public digest of score changes with phone numbers removed.

## Optional Docker deploy

Docker is for a hosted deploy, including RumptyCloud. Local use and contributions do not need it.

```powershell
docker compose up --build
```

Open http://localhost:8000. The container serves the built dashboard and the API together. The database file is stored at `/data/veriduka.db`.
