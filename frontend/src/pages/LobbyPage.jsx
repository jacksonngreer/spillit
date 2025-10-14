import React, { useContext, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { GameContext } from "../context/GameContext";
import "../styles/main.css";

function LobbyPage() {
  const navigate = useNavigate();
  const { playerName, roomCode, players, socket, setSocket, setPlayers } = useContext(GameContext);

  useEffect(() => {
  if (!socket && roomCode) {
    const newSocket = new WebSocket(`ws://127.0.0.1:8000/ws/${roomCode}`);
    setSocket(newSocket);

    newSocket.onopen = () => {
      console.log("Reconnected to room:", roomCode);
      newSocket.send(JSON.stringify({ type: "join", name: playerName }));
    };

    newSocket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "join") {
        setPlayers((prev) => [...new Set([...prev, msg.name])]);
      } else if (msg.type === "leave") {
        setPlayers((prev) => prev.filter((n) => n !== msg.name));
      }
    };
  }
}, [socket, roomCode, playerName, setPlayers, setSocket]);



  const handleStart = () => {
    console.log("Game started!");
    navigate("/game");
  };

  return (
    <div className="container">
      <div className="card">
        <h2 className="title">Lobby</h2>
        <p className="room-code">Room Code: <span>{roomCode}</span></p>
        <div className="player-list">
          {players.map((player, index) => (
            <p key={index} className="player-name">{player}</p>
          ))}
        </div>
        {isHost ? (
          <button className="primary-button" onClick={handleStart}>
            Start Game
          </button>
        ) : (
          <p className="waiting-text">Waiting for host to start...</p>
        )}
        <button className="secondary-button" onClick={() => navigate("/")}>
          Leave Lobby
        </button>
      </div>
    </div>
  );
}

export default LobbyPage;
