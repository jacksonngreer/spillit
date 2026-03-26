import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
import random, string

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://spillit.live",
        "https://www.spillit.live",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Question bank ──────────────────────────────────────────────────────────────
QUESTIONS = [
    "Who is most likely to accidentally like a 5-year-old post while stalking someone?",
    "Who is most likely to lie about watching a movie they've never seen?",
    "Who is most likely to ghost someone and then act surprised when they're upset?",
]

# ── Room store ─────────────────────────────────────────────────────────────────
# rooms = {
#   room_code: {
#     "players":         [name, ...],        – active players in the current round
#     "pending_players": [name, ...],        – joined mid-round; join at next question
#     "connections":     [(ws, name), ...],  – active WebSocket connections
#     "host":            name,
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
    return ''.join(random.choices(string.ascii_uppercase, k=4))


def make_game_state():
    return {
        "phase": "lobby",
        "question_index": 0,
        "votes": {},
        "scores": {},
    }


async def broadcast(code: str, msg: dict):
    text = json.dumps(msg)
    for conn, _ in rooms[code]["connections"]:
        await conn.send_text(text)


def _tally_round(code: str) -> dict:
    """Count votes received by each active player this round."""
    tally = {p: 0 for p in rooms[code]["players"]}
    for _, voted_for in rooms[code]["game"]["votes"].items():
        if voted_for in tally:
            tally[voted_for] += 1
    return tally


async def _do_reveal(code: str):
    """Reveal round results unconditionally (used by skip and auto-reveal)."""
    game = rooms[code]["game"]
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


async def _maybe_reveal(code: str):
    """Auto-reveal once every active player has cast a vote."""
    game = rooms[code]["game"]
    if game["phase"] != "voting":
        return
    active = rooms[code]["players"]
    if not active:
        return
    active_cast = sum(1 for voter in game["votes"] if voter in active)
    if active_cast >= len(active):
        await _do_reveal(code)


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@app.get("/create-room/{name}")
async def create_room(name: str):
    code = generate_code()
    rooms[code] = {
        "players": [name],
        "pending_players": [],
        "connections": [],
        "host": name,
        "game": make_game_state(),
    }
    return {"room_code": code, "players": [name]}


@app.get("/join-room/{code}/{name}")
async def join_room(code: str, name: str):
    if code not in rooms:
        return {"error": "Room not found"}
    game = rooms[code]["game"]
    # During an active round, queue new players so they don't affect vote totals
    if name not in rooms[code]["players"] and name not in rooms[code]["pending_players"]:
        if game["phase"] in ("voting", "results"):
            rooms[code]["pending_players"].append(name)
        else:
            rooms[code]["players"].append(name)
    return {
        "room_code": code,
        "players": rooms[code]["players"],
        "game_phase": game["phase"],
    }


@app.post("/leave-room")
async def leave_room(request: Request):
    data = await request.json()
    code = data.get("code")
    name = data.get("name")

    if code in rooms:
        # Remove from pending if they hadn't fully joined yet
        rooms[code]["pending_players"] = [
            p for p in rooms[code]["pending_players"] if p != name
        ]
        if name in rooms[code]["players"]:
            rooms[code]["players"].remove(name)
            rooms[code]["connections"] = [
                (conn, n) for conn, n in rooms[code]["connections"] if n != name
            ]
            await broadcast(code, {"type": "leave", "name": name})
            if rooms[code]["host"] == name and rooms[code]["players"]:
                new_host = rooms[code]["players"][0]
                rooms[code]["host"] = new_host
                await broadcast(code, {"type": "host_change", "name": new_host})
            # Player leaving may complete the round if everyone else already voted
            await _maybe_reveal(code)

    return {"status": "ok"}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    await websocket.accept()

    if code not in rooms:
        rooms[code] = {
            "players": [],
            "pending_players": [],
            "connections": [],
            "host": None,
            "game": make_game_state(),
        }

    player_name = None

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # ── join ───────────────────────────────────────────────────────────
            if msg["type"] == "join":
                player_name = msg["name"]

                # Replace any stale connection for this name
                rooms[code]["connections"] = [
                    (conn, n) for conn, n in rooms[code]["connections"]
                    if n != player_name
                ]
                rooms[code]["connections"].append((websocket, player_name))

                game = rooms[code]["game"]

                if player_name in rooms[code]["pending_players"]:
                    # Mid-round joiner – hold them in pending and show waiting screen
                    await websocket.send_text(json.dumps({
                        "type": "sync",
                        "game_phase": "waiting_for_round",
                        "players": rooms[code]["players"],
                        "host": rooms[code]["host"],
                    }))
                elif player_name not in rooms[code]["players"]:
                    # Brand-new player
                    if game["phase"] in ("voting", "results"):
                        # Game already running – queue for next round
                        rooms[code]["pending_players"].append(player_name)
                        await websocket.send_text(json.dumps({
                            "type": "sync",
                            "game_phase": "waiting_for_round",
                            "players": rooms[code]["players"],
                            "host": rooms[code]["host"],
                        }))
                    else:
                        rooms[code]["players"].append(player_name)
                        await broadcast(code, {"type": "join", "name": player_name})
                else:
                    # Reconnecting active player – send current state to catch up
                    sync_payload = {
                        "type": "sync",
                        "players": rooms[code]["players"],
                        "host": rooms[code]["host"],
                        "game_phase": game["phase"],
                    }
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
                game["scores"] = {p: 0 for p in rooms[code]["players"]}
                await broadcast(code, {"type": "start_game"})

            # ── request_state ─────────────────────────────────────────────────
            elif msg["type"] == "request_state":
                if not player_name:
                    continue

                game = rooms[code]["game"]

                # Pending mid-round joiner gets the waiting screen
                if player_name in rooms[code]["pending_players"]:
                    await websocket.send_text(json.dumps({
                        "type": "game_state",
                        "phase": "waiting_for_round",
                        "host": rooms[code]["host"],
                        "players": rooms[code]["players"],
                    }))
                    continue

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
                    active_cast = sum(1 for voter in game["votes"] if voter in rooms[code]["players"])
                    state["vote_update"] = {
                        "cast": active_cast,
                        "total": player_count,
                    }
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
                    continue

                game["votes"][player_name] = msg["for"]

                active = rooms[code]["players"]
                active_cast = sum(1 for voter in game["votes"] if voter in active)
                total = len(active)

                await broadcast(code, {
                    "type": "vote_update",
                    "cast": active_cast,
                    "total": total,
                })
                await _maybe_reveal(code)

            # ── skip_to_results (host only) ───────────────────────────────────
            elif msg["type"] == "skip_to_results":
                if rooms[code]["game"]["phase"] == "voting":
                    await _do_reveal(code)

            # ── next_question ─────────────────────────────────────────────────
            elif msg["type"] == "next_question":
                game = rooms[code]["game"]
                next_idx = game["question_index"] + 1

                # Promote pending players into active players for the new round
                for pending in rooms[code]["pending_players"]:
                    if pending not in rooms[code]["players"]:
                        rooms[code]["players"].append(pending)
                        game["scores"][pending] = 0
                rooms[code]["pending_players"] = []

                if next_idx < len(QUESTIONS):
                    game["question_index"] = next_idx
                    game["votes"] = {}
                    game["phase"] = "voting"
                    await broadcast(code, {
                        "type": "question",
                        "index": next_idx,
                        "text": QUESTIONS[next_idx],
                        "total": len(QUESTIONS),
                        "player_count": len(rooms[code]["players"]),
                        "players": rooms[code]["players"],
                    })
                else:
                    game["phase"] = "end"
                    await broadcast(code, {
                        "type": "game_over",
                        "scores": game["scores"],
                    })

            # ── leave (explicit Leave button) ──────────────────────────────────
            elif msg["type"] == "leave":
                name_leaving = msg["name"]
                rooms[code]["connections"] = [
                    (conn, n) for conn, n in rooms[code]["connections"]
                    if n != name_leaving
                ]
                rooms[code]["pending_players"] = [
                    p for p in rooms[code]["pending_players"] if p != name_leaving
                ]
                if name_leaving in rooms[code]["players"]:
                    rooms[code]["players"].remove(name_leaving)
                await broadcast(code, {"type": "leave", "name": name_leaving})

                if rooms[code]["host"] == name_leaving and rooms[code]["players"]:
                    new_host = rooms[code]["players"][0]
                    rooms[code]["host"] = new_host
                    await broadcast(code, {"type": "host_change", "name": new_host})

                await _maybe_reveal(code)

    except WebSocketDisconnect:
        rooms[code]["connections"] = [
            (conn, n) for conn, n in rooms[code]["connections"]
            if conn != websocket
        ]

        if player_name:
            print(f"{player_name} disconnected from room {code}")
            # Clean up from pending if they hadn't fully joined
            rooms[code]["pending_players"] = [
                p for p in rooms[code]["pending_players"] if p != player_name
            ]
            if player_name in rooms[code]["players"]:
                rooms[code]["players"].remove(player_name)
                await broadcast(code, {"type": "leave", "name": player_name})

                if rooms[code]["host"] == player_name and rooms[code]["players"]:
                    new_host = rooms[code]["players"][0]
                    rooms[code]["host"] = new_host
                    await broadcast(code, {"type": "host_change", "name": new_host})

                await _maybe_reveal(code)
