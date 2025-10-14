import React, { useState, useContext } from "react";
import { useNavigate } from "react-router-dom";
import { GameContext } from "../context/GameContext";
import "../styles/main.css";

function JoinPage() {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const navigate = useNavigate();
  const { setPlayerName, setRoomCode, setIsHost, setPlayers, setSocket } = useContext(GameContext);

  const handleJoin = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`http://127.0.0.1:8000/join-room/${code}/${name}`);
      const data = await res.json();

      if (data.error) {
        alert("Room not found.");
        return;
      }

      setPlayerName(name);
      setRoomCode(data.room_code);
      setPlayers(data.players);
      setIsHost(false);

      // ✅ Connect to WebSocket
      const newSocket = new WebSocket(`ws://127.0.0.1:8000/ws/${data.room_code}`);
      setSocket(newSocket);

      newSocket.onopen = () => {
        console.log("Connected to WebSocket room:", data.room_code);
        // Send join message to notify other players
        newSocket.send(JSON.stringify({ type: "join", name }));
      };

      newSocket.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === "join") {
          setPlayers((prev) => [...new Set([...prev, msg.name])]);
        } else if (msg.type === "leave") {
          setPlayers((prev) => prev.filter((n) => n !== msg.name));
        }
      };

              // 🧩 Send a synchronous "leave" signal when tab closes
        window.addEventListener("beforeunload", () => {
          const payload = JSON.stringify({ code: data.room_code, name });
          navigator.sendBeacon("http://127.0.0.1:8000/leave-room", payload);
        });



      navigate("/lobby");
    } catch (err) {
      console.error("Error joining room:", err);
      alert("Server error. Make sure the backend is running.");
    }
  };



  return (
    <div className="container">
      <div className="card">
        <h2 className="title">Join Room</h2>
        <form onSubmit={handleJoin} className="join-form">
          <input
            type="text"
            placeholder="Enter your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            type="text"
            placeholder="Enter room code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <button className="primary-button" type="submit">
            Join Game
          </button>
        </form>
        <button className="secondary-button" onClick={() => navigate("/")}>
          Back to Home
        </button>
      </div>
    </div>
  );
}

export default JoinPage;
