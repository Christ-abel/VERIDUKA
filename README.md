# VeriDuka

Signal-based merchant checks for Kenyan online shops. Look up a paybill, phone, Instagram handle, KRA PIN, or shop name. The trust score uses a legal record and what buyers actually reported. The same score answers ThriveWave SMS.

Docker is only for a hosted deploy. You do not need it to use the app or to contribute.

## Run without Docker

Install Python 3.11+ and Node.js 20+, then from this folder:

```powershell
.\start.ps1
```

Or double click `start.bat`. The script creates `.env` from `.env.example` when needed, installs dependencies, and opens http://localhost:5173.

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

## API keys

Copy `.env.example` to `.env`. Empty values keep the built-in mocks.

| Variable | What it unlocks |
| --- | --- |
| `THRIVEWAVE_API_KEY` and `THRIVEWAVE_LIVE=true` | Real SMS dispatch |
| `META_ACCESS_TOKEN` and `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Comments on an Instagram account that authorized the app |
| `KRA_API_URL`, `KRA_API_KEY`, `BRS_API_URL`, `BRS_API_KEY` | Live registry adapters, when those clients are added |
| `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET` | Reserved for a Safaricom till-name check |

## Social comments

A comment moves the score only when two things are true: the text has a clear pattern, and it includes a public post link.

Anyone can open a shop, choose Social comments, and paste comments from Instagram, Facebook, TikTok, X, or a WhatsApp chat. One comment per line.

A connected shop is different. Meta's Graph API can read comments on an Instagram professional account that authorized this app. Use Sync connected Instagram after the token and account id are in `.env`. VeriDuka does not log into Instagram, and it does not pull comments from an account that has not granted access. WhatsApp has no public comment feed, so those notes are pasted by a buyer or, later, received from a shop that opts in to the WhatsApp Business webhook.

## Try these

| Lookup | What you should see |
| --- | --- |
| Paybill `400200` | Nairobi Tech Hub Electronics, legal match, high signal |
| `@trendyclothez_ke` | Trendy Clothez Kenya, no registry match, fraud alert |
| `0722113344` | Mama Boaz Organic Veggies, BRS pending, moderate risk |
| SMS `VERIFY 522522` | No record. Do not pay upfront |

## Score

Start at 50. Active KRA or registered BRS adds 25. Each verified positive review adds 5, capped at 20. Each unresolved scam removes 20. Each delivery or service complaint removes 5. A negative report newer than 30 days counts double. The gauge keeps the total between 0 and 100.

- 80 to 100: Verified signal
- 50 to 79: Moderate risk
- 0 to 49: High noise / fraud alert

## Optional Docker deploy

For a single container on RumptyCloud:

```powershell
docker compose up --build
```

Open http://localhost:8000. The database file is stored at `/data/veriduka.db`.
