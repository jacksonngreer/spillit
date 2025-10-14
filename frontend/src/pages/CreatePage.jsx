import React, { useState, useContext } from "react";
import { useNavigate } from "react-router-dom";
import { GameContext } from "../context/GameContext";
import "../styles/main.css";

function CreatePage() {
  const [name, setName] = useState("");
  const navigate = useNavigate();
  const { setPlayerName, setRoomCode, setIsHost, setPlayers, setSocket } = useContext(GameContext);
  
  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`http://127.0.0.1:8000/create-room/${name}`);
      const data = await res.json();

      if (data.room_code) {
        setPlayerName(name);
        setRoomCode(data.room_code);
        setPlayers(data.players);
        setIsHost(true);

        // ✅ Create WebSocket connection
        const newSocket = new WebSocket(`ws://127.0.0.1:8000/ws/${data.room_code}`);
        setSocket(newSocket);

        newSocket.onopen = () => {
          console.log("Connected to WebSocket room:", data.room_code);
          // Send "join" message to others
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
      } else {
        alert("Failed to create room.");
      }
    } catch (err) {
      console.error("Error creating room:", err);
      alert("Server error. Make sure the backend is running.");
    }
  };



  return (
    <div className="container">
      <div className="card">
        <h2 className="title">Create Room</h2>
        <form onSubmit={handleCreate} className="join-form">
          <input
            type="text"
            placeholder="Enter your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <button className="primary-button" type="submit">
            Create Game
          </button>
        </form>
        <button className="secondary-button" onClick={() => navigate("/")}>
          Back to Home
        </button>
      </div>
    </div>
  );
}

export default CreatePage;
