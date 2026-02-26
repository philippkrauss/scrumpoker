import os
import uuid
import time
from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from openai import OpenAI

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ---------------------------------------------------------------------------
# GitHub-hosted LLM client
# ---------------------------------------------------------------------------
ai_client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.environ.get("GITHUB_TOKEN", ""),
)

# ---------------------------------------------------------------------------
# In-memory data store
# ---------------------------------------------------------------------------
# rooms = {
#     "room_id": {
#         "name": "Sprint 42",
#         "created_at": float,
#         "participants": {
#             "user_id": {"name": "Alice", "vote": None, "sid": "..."}
#         },
#         "revealed": False,
#         "card_set": "fibonacci",
#     }
# }
rooms: dict[str, dict] = {}

CARD_SETS = {
    "fibonacci": ["0", "1", "2", "3", "5", "8", "13", "21", "34", "55", "89", "?", "☕"],
    "tshirt": ["XS", "S", "M", "L", "XL", "XXL", "?", "☕"],
    "powers": ["0", "1", "2", "4", "8", "16", "32", "64", "?", "☕"],
}


def _room_state(room_id: str) -> dict:
    """Return a sanitised snapshot of the room that is safe to broadcast."""
    room = rooms[room_id]
    participants = []
    for uid, p in room["participants"].items():
        participants.append({
            "id": uid,
            "name": p["name"],
            "voted": p["vote"] is not None,
            "vote": p["vote"] if room["revealed"] else None,
        })
    return {
        "room_id": room_id,
        "room_name": room["name"],
        "revealed": room["revealed"],
        "card_set": room["card_set"],
        "cards": CARD_SETS[room["card_set"]],
        "participants": participants,
    }


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/room/<room_id>")
def room_page(room_id):
    if room_id not in rooms:
        return render_template("index.html", error="Room not found."), 404
    return render_template("room.html", room_id=room_id, room=rooms[room_id], card_sets=CARD_SETS)


# ---------------------------------------------------------------------------
# Socket.IO events
# ---------------------------------------------------------------------------
@socketio.on("create_room")
def handle_create_room(data):
    room_id = uuid.uuid4().hex[:8]
    card_set = data.get("card_set", "fibonacci")
    if card_set not in CARD_SETS:
        card_set = "fibonacci"
    rooms[room_id] = {
        "name": data.get("room_name", "Scrum Poker").strip() or "Scrum Poker",
        "created_at": time.time(),
        "participants": {},
        "revealed": False,
        "card_set": card_set,
    }
    emit("room_created", {"room_id": room_id})


@socketio.on("join")
def handle_join(data):
    room_id = data["room_id"]
    user_name = data.get("user_name", "Anonymous").strip() or "Anonymous"
    if room_id not in rooms:
        emit("error", {"message": "Room not found"})
        return

    user_id = data.get("user_id") or uuid.uuid4().hex[:12]
    room = rooms[room_id]

    room["participants"][user_id] = {
        "name": user_name,
        "vote": room["participants"].get(user_id, {}).get("vote"),
        "sid": request.sid,
    }
    join_room(room_id)

    emit("joined", {"user_id": user_id, "state": _room_state(room_id)})
    emit("room_update", _room_state(room_id), to=room_id)


@socketio.on("vote")
def handle_vote(data):
    room_id = data["room_id"]
    user_id = data["user_id"]
    card = data["card"]
    if room_id not in rooms:
        return
    room = rooms[room_id]
    if room["revealed"]:
        return
    if user_id in room["participants"]:
        current = room["participants"][user_id]["vote"]
        # Toggle: clicking same card again removes vote
        room["participants"][user_id]["vote"] = None if current == card else card
    emit("room_update", _room_state(room_id), to=room_id)


@socketio.on("reveal")
def handle_reveal(data):
    room_id = data["room_id"]
    if room_id not in rooms:
        return
    rooms[room_id]["revealed"] = True
    emit("room_update", _room_state(room_id), to=room_id)


@socketio.on("reset")
def handle_reset(data):
    room_id = data["room_id"]
    if room_id not in rooms:
        return
    room = rooms[room_id]
    room["revealed"] = False
    for uid in room["participants"]:
        room["participants"][uid]["vote"] = None
    emit("room_update", _room_state(room_id), to=room_id)


@socketio.on("leave")
def handle_leave(data):
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    if room_id and room_id in rooms and user_id:
        rooms[room_id]["participants"].pop(user_id, None)
        leave_room(room_id)
        if not rooms[room_id]["participants"]:
            del rooms[room_id]
        else:
            emit("room_update", _room_state(room_id), to=room_id)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    for room_id, room in list(rooms.items()):
        for uid, p in list(room["participants"].items()):
            if p["sid"] == sid:
                del room["participants"][uid]
                if not room["participants"]:
                    del rooms[room_id]
                else:
                    emit("room_update", _room_state(room_id), to=room_id)
                break


# ---------------------------------------------------------------------------
# AI vote analysis
# ---------------------------------------------------------------------------
@socketio.on("analyze_votes")
def handle_analyze_votes(data):
    room_id = data.get("room_id")
    if room_id not in rooms:
        emit("ai_analysis", {"error": "Room not found"})
        return
    room = rooms[room_id]
    if not room["revealed"]:
        emit("ai_analysis", {"error": "Votes not revealed yet"})
        return

    # Build vote summary
    vote_lines = []
    for uid, p in room["participants"].items():
        vote_lines.append(f"- {p['name']}: {p['vote'] if p['vote'] else 'did not vote'}")
    votes_text = "\n".join(vote_lines)

    prompt = (
        f"You are a helpful Scrum Poker assistant. The team just voted on a story using the "
        f"'{room['card_set']}' card set. Here are the votes:\n\n"
        f"{votes_text}\n\n"
        f"Please provide a brief summary (2-4 sentences). "
        f"Highlight any outlying votes that are significantly different from the majority. "
        f"If there is strong consensus, say so. "
        f"Suggest whether the team should discuss further or can agree on an estimate. "
        f"Keep it concise and friendly. Use one or two emojis."
    )

    try:
        response = ai_client.chat.completions.create(
            model="openai/gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a concise Scrum Poker assistant. Respond in plain text, no markdown."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        summary = response.choices[0].message.content.strip()
        emit("ai_analysis", {"summary": summary}, to=room_id)
    except Exception as e:
        emit("ai_analysis", {"error": f"AI analysis failed: {str(e)}"})


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

