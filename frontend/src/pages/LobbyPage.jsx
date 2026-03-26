import React, { useContext, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { GameContext } from "../context/GameContext";
import "../styles/main.css";

function LobbyPage() {
  const navigate = useNavigate();
  const { playerName, roomCode, isHost, players, socket, setSocket, setPlayers, clearGame } = useContext(GameContext);

  // Reconnect if socket was lost (e.g. page refresh)
  useEffect(() => {
    if (!socket && roomCode) {
      const newSocket = new WebSocket(`${process.env.REACT_APP_WS_URL}/ws/${roomCode}`);
      setSocket(newSocket);
      newSocket.onopen = () => {
        newSocket.send(JSON.stringify({ type: "join", name: playerName }));
      };
    }
  }, [socket, roomCode, playerName, setSocket]);

  // Always keep onmessage current so navigate and setPlayers are up to date
  useEffect(() => {
    if (!socket) return;
    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "join") {
        setPlayers((prev) => [...new Set([...prev, msg.name])]);
      } else if (msg.type === "leave") {
        setPlayers((prev) => prev.filter((n) => n !== msg.name));
      } else if (msg.type === "sync") {
        setPlayers(msg.players);
      } else if (msg.type === "start_game") {
        navigate("/game");
      }
    };
  }, [socket, setPlayers, navigate]);

  const handleLeave = () => {
    clearGame();
    navigate("/");
  };

  const handleStart = () => {
    if (socket) {
      socket.send(JSON.stringify({ type: "start_game" }));
    }
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
        <button className="secondary-button" onClick={handleLeave}>
          Leave Lobby
        </button>
      </div>
    </div>
  );
}

export default LobbyPage;
