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

rooms = {}  # { room_code: { "players": [names], "connections": [(ws, name)] } }

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

@app.get("/create-room/{name}")
async def create_room(name: str):
    code = generate_code()
    rooms[code] = {"players": [name], "connections": []}
    return {"room_code": code, "players": [name]}

@app.get("/join-room/{code}/{name}")
async def join_room(code: str, name: str):
    if code not in rooms:
        return {"error": "Room not found"}
    rooms[code]["players"].append(name)
    return {"room_code": code, "players": rooms[code]["players"]}

@app.post("/leave-room")
async def leave_room(request: Request):
    data = await request.json()
    code = data.get("code")
    name = data.get("name")

    if code in rooms and name in rooms[code]["players"]:
        rooms[code]["players"].remove(name)
        rooms[code]["connections"] = [
            (conn, n) for conn, n in rooms[code]["connections"] if n != name
        ]
        broadcast_msg = {"type": "leave", "name": name}
        for conn, _ in rooms[code]["connections"]:
            await conn.send_text(json.dumps(broadcast_msg))

    return {"status": "ok"}

@app.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    await websocket.accept()
    if code not in rooms:
        rooms[code] = {"players": [], "connections": []}

    player_name = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg["type"] == "join":
                player_name = msg["name"]
                rooms[code]["connections"].append((websocket, player_name))
                if player_name not in rooms[code]["players"]:
                    rooms[code]["players"].append(player_name)
                # Broadcast join
                broadcast_msg = {"type": "join", "name": player_name}
                for conn, _ in rooms[code]["connections"]:
                    await conn.send_text(json.dumps(broadcast_msg))

            elif msg["type"] == "leave":
                player_name = msg["name"]
                # Remove player + connection
                rooms[code]["connections"] = [
                    (conn, n) for conn, n in rooms[code]["connections"] if n != player_name
                ]
                if player_name in rooms[code]["players"]:
                    rooms[code]["players"].remove(player_name)
                # Broadcast leave
                broadcast_msg = {"type": "leave", "name": player_name}
                for conn, _ in rooms[code]["connections"]:
                    await conn.send_text(json.dumps(broadcast_msg))


    except WebSocketDisconnect:
        print(f"{player_name} disconnected from room {code}")
        # Remove connection
        rooms[code]["connections"] = [
            (conn, n) for conn, n in rooms[code]["connections"] if conn != websocket
        ]
        # Remove player
        if player_name in rooms[code]["players"]:
            rooms[code]["players"].remove(player_name)
        # Broadcast updated player list
        broadcast_msg = {"type": "leave", "name": player_name}
        for conn, _ in rooms[code]["connections"]:
            await conn.send_text(json.dumps(broadcast_msg))
