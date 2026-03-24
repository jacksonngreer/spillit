import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
import random, string

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Question bank ──────────────────────────────────────────────────────────────
# Add more prompts here to expand the game. Each is a "Who is most likely to…"
# style question that players vote on.
QUESTIONS = [
    "Who is most likely to accidentally like a 5-year-old post while stalking someone?",
    "Who is most likely to lie about watching a movie they've never seen?",
    "Who is most likely to ghost someone and then act surprised when they're upset?",
]

# ── Room store ─────────────────────────────────────────────────────────────────
# rooms = {
#   room_code: {
#     "players":     [name, ...],        – ordered list of player names
#     "connections": [(ws, name), ...],  – active WebSocket connections
#     "host":        name,               – current host (transfers if host leaves)
#     "game": {
#       "phase":          "lobby" | "voting" | "results" | "end",
#       "question_index": int,
#       "votes":          { voter_name: voted_for_name },
#       "scores":         { player_name: cumulative_vote_count },
#     }
#   }
# }
rooms = {}


def generate_code():
    """Return a random 4-letter uppercase room code."""
    return ''.join(random.choices(string.ascii_uppercase, k=4))


def make_game_state():
    """Return a fresh game state dict for a new room."""
    return {
        "phase": "lobby",
        "question_index": 0,
        "votes": {},
        "scores": {},
    }


async def broadcast(code: str, msg: dict):
    """Send a JSON message to every connected player in the room."""
    text = json.dumps(msg)
    for conn, _ in rooms[code]["connections"]:
        await conn.send_text(text)


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@app.get("/create-room/{name}")
async def create_room(name: str):
    """Create a new room with the caller as the first player and host."""
    code = generate_code()
    rooms[code] = {
        "players": [name],
        "connections": [],
        "host": name,
        "game": make_game_state(),
    }
    return {"room_code": code, "players": [name]}


@app.get("/join-room/{code}/{name}")
async def join_room(code: str, name: str):
    """Add a player to an existing room. Idempotent – safe to call on reconnect."""
    if code not in rooms:
        return {"error": "Room not found"}
    if name not in rooms[code]["players"]:
        rooms[code]["players"].append(name)
    return {"room_code": code, "players": rooms[code]["players"]}


@app.post("/leave-room")
async def leave_room(request: Request):
    """
    Called via navigator.sendBeacon when a player closes or refreshes their tab.
    Removes the player and notifies everyone remaining.
    """
    data = await request.json()
    code = data.get("code")
    name = data.get("name")

    if code in rooms and name in rooms[code]["players"]:
        rooms[code]["players"].remove(name)
        rooms[code]["connections"] = [
            (conn, n) for conn, n in rooms[code]["connections"] if n != name
        ]
        await broadcast(code, {"type": "leave", "name": name})

        # If the leaving player was the host, promote the next player
        if rooms[code]["host"] == name and rooms[code]["players"]:
            new_host = rooms[code]["players"][0]
            rooms[code]["host"] = new_host
            await broadcast(code, {"type": "host_change", "name": new_host})

    return {"status": "ok"}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    await websocket.accept()

    # Ensure the room exists even if the HTTP create call is somehow missed
    if code not in rooms:
        rooms[code] = {
            "players": [],
            "connections": [],
            "host": None,
            "game": make_game_state(),
        }

    # player_name is set once a "join" message is received
    player_name = None

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # ── join ───────────────────────────────────────────────────────────
            if msg["type"] == "join":
                player_name = msg["name"]

                # Replace any stale connection for this name (e.g. page refresh)
                rooms[code]["connections"] = [
                    (conn, n) for conn, n in rooms[code]["connections"]
                    if n != player_name
                ]
                rooms[code]["connections"].append((websocket, player_name))

                if player_name not in rooms[code]["players"]:
                    # Genuinely new player – broadcast to everyone
                    rooms[code]["players"].append(player_name)
                    await broadcast(code, {"type": "join", "name": player_name})
                else:
                    # Reconnecting player – send them the current state to catch up
                    game = rooms[code]["game"]
                    sync_payload = {
                        "type": "sync",
                        "players": rooms[code]["players"],
                        "host": rooms[code]["host"],
                        "game_phase": game["phase"],
                    }
                    # Include the active question if one is in progress
                    if game["phase"] in ("voting", "results") and game["question_index"] < len(QUESTIONS):
                        idx = game["question_index"]
                        sync_payload["question"] = {
                            "index": idx,
                            "text": QUESTIONS[idx],
                            "total": len(QUESTIONS),
                        }
                    if game["phase"] == "results":
                        sync_payload["results"] = {
                            "votes": game["votes"],
                            "round_scores": _tally_round(code),
                            "scores": game["scores"],
                        }
                    await websocket.send_text(json.dumps(sync_payload))

            # ── start_game ────────────────────────────────────────────────────
            elif msg["type"] == "start_game":
                game = rooms[code]["game"]
                game["phase"] = "voting"
                game["question_index"] = 0
                game["votes"] = {}
                # Initialise every current player's cumulative score to 0
                game["scores"] = {p: 0 for p in rooms[code]["players"]}

                # Only tell clients to navigate – each GamePage will request its
                # own state once mounted, avoiding the race where `question`
                # arrives before GamePage's onmessage handler is registered.
                await broadcast(code, {"type": "start_game"})

            # ── request_state ─────────────────────────────────────────────────
            elif msg["type"] == "request_state":
                # Sent by GamePage immediately after it wires up its onmessage
                # handler so it can catch up on whatever phase the game is in.
                game = rooms[code]["game"]
                player_count = len(rooms[code]["players"])
                state: dict = {
                    "type": "game_state",
                    "phase": game["phase"],
                    "host": rooms[code]["host"],
                    "players": rooms[code]["players"],
                }
                if game["phase"] in ("voting", "results") and game["question_index"] < len(QUESTIONS):
                    idx = game["question_index"]
                    state["question"] = {
                        "index": idx,
                        "text": QUESTIONS[idx],
                        "total": len(QUESTIONS),
                        "player_count": player_count,
                    }
                if game["phase"] == "voting":
                    state["vote_update"] = {
                        "cast": len(game["votes"]),
                        "total": player_count,
                    }
                    # Let a reconnecting voter know they already voted this round
                    state["my_vote"] = game["votes"].get(player_name)
                if game["phase"] == "results":
                    state["results"] = {
                        "votes": game["votes"],
                        "round_scores": _tally_round(code),
                        "scores": game["scores"],
                    }
                if game["phase"] == "end":
                    state["scores"] = game["scores"]
                await websocket.send_text(json.dumps(state))

            # ── vote ──────────────────────────────────────────────────────────
            elif msg["type"] == "vote":
                game = rooms[code]["game"]
                if game["phase"] != "voting":
                    continue  # Ignore late votes

                voted_for = msg["for"]
                game["votes"][player_name] = voted_for

                cast = len(game["votes"])
                total = len(rooms[code]["players"])

                # Broadcast live vote progress (counts only – no names until reveal)
                await broadcast(code, {
                    "type": "vote_update",
                    "cast": cast,
                    "total": total,
                })

                # Once everyone has voted, reveal results automatically
                if cast >= total:
                    round_scores = _tally_round(code)
                    for name, count in round_scores.items():
                        game["scores"][name] = game["scores"].get(name, 0) + count
                    game["phase"] = "results"
                    await broadcast(code, {
                        "type": "results",
                        "votes": game["votes"],
                        "round_scores": round_scores,
                        "scores": game["scores"],
                    })

            # ── next_question ─────────────────────────────────────────────────
            elif msg["type"] == "next_question":
                game = rooms[code]["game"]
                next_idx = game["question_index"] + 1

                if next_idx < len(QUESTIONS):
                    # Advance to the next round
                    game["question_index"] = next_idx
                    game["votes"] = {}
                    game["phase"] = "voting"
                    await broadcast(code, {
                        "type": "question",
                        "index": next_idx,
                        "text": QUESTIONS[next_idx],
                        "total": len(QUESTIONS),
                        # Authoritative count so the frontend progress bar is correct
                        "player_count": len(rooms[code]["players"]),
                    })
                else:
                    # All questions done – send final scores
                    game["phase"] = "end"
                    await broadcast(code, {
                        "type": "game_over",
                        "scores": game["scores"],
                    })

            # ── leave (explicit, e.g. Leave button) ───────────────────────────
            elif msg["type"] == "leave":
                name_leaving = msg["name"]
                rooms[code]["connections"] = [
                    (conn, n) for conn, n in rooms[code]["connections"]
                    if n != name_leaving
                ]
                if name_leaving in rooms[code]["players"]:
                    rooms[code]["players"].remove(name_leaving)
                await broadcast(code, {"type": "leave", "name": name_leaving})

                # Transfer host if needed
                if rooms[code]["host"] == name_leaving and rooms[code]["players"]:
                    new_host = rooms[code]["players"][0]
                    rooms[code]["host"] = new_host
                    await broadcast(code, {"type": "host_change", "name": new_host})

    except WebSocketDisconnect:
        # Remove this socket from the connection list
        rooms[code]["connections"] = [
            (conn, n) for conn, n in rooms[code]["connections"]
            if conn != websocket
        ]

        # Only take action if this socket had completed a join handshake
        if player_name:
            print(f"{player_name} disconnected from room {code}")
            if player_name in rooms[code]["players"]:
                rooms[code]["players"].remove(player_name)
            await broadcast(code, {"type": "leave", "name": player_name})

            # If the host disconnected, promote the next available player
            if rooms[code]["host"] == player_name and rooms[code]["players"]:
                new_host = rooms[code]["players"][0]
                rooms[code]["host"] = new_host
                await broadcast(code, {"type": "host_change", "name": new_host})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tally_round(code: str) -> dict:
    """
    Count how many votes each current player received this round.
    Returns { player_name: vote_count } for every player still in the room.
    """
    tally = {p: 0 for p in rooms[code]["players"]}
    for _, voted_for in rooms[code]["game"]["votes"].items():
        if voted_for in tally:
            tally[voted_for] += 1
    return tally
