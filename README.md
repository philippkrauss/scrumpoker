# 🃏 Scrum Poker

Real-time planning poker for agile teams. No login required, no database – everything runs in memory.

## Features

- **Real-time voting** via WebSockets (Socket.IO)
- **Multiple card sets**: Fibonacci, T-Shirt Sizes, Powers of 2
- **Card flip animation** when votes are revealed
- **Live result statistics** with average, min, max
- **Mobile-friendly** responsive design
- **No persistence** – all data in memory, rooms disappear when all users leave

## Local Development

```bash
cd scrumpoker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Deploy to Render.com

1. Push this repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New → Blueprint** and connect the repo
4. Render will auto-detect `render.yaml` and deploy

Or manually:
1. **New → Web Service**
2. Connect the repo, set root directory to `scrumpoker`
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --bind 0.0.0.0:$PORT app:app`

> **Note:** Use only **1 worker** (`-w 1`) since the app stores data in memory.

## How It Works

1. One person creates a room and shares the link/code
2. Team members join using their name
3. Everyone picks a card to vote
4. Click **Reveal** to show all votes with a flip animation
5. Click **New Round** to reset and vote again

