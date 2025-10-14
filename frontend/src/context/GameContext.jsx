import React, { createContext, useState, useEffect } from "react";

export const GameContext = createContext();

export const GameProvider = ({ children }) => {
  const [playerName, setPlayerName] = useState(localStorage.getItem("playerName") || "");
  const [roomCode, setRoomCode] = useState(localStorage.getItem("roomCode") || "");
  const [isHost, setIsHost] = useState(localStorage.getItem("isHost") === "true");
  const [players, setPlayers] = useState(
    JSON.parse(localStorage.getItem("players") || "[]")
  );
  const [socket, setSocket] = useState(null);

  // 💾 Save to localStorage whenever values change
  useEffect(() => {
    localStorage.setItem("playerName", playerName);
    localStorage.setItem("roomCode", roomCode);
    localStorage.setItem("isHost", isHost);
    localStorage.setItem("players", JSON.stringify(players));
  }, [playerName, roomCode, isHost, players]);

  const addPlayer = (name) => setPlayers((prev) => [...prev, name]);

  const clearGame = () => {
    setPlayerName("");
    setRoomCode("");
    setIsHost(false);
    setPlayers([]);
    if (socket) socket.close();
    setSocket(null);
    localStorage.clear(); // 🔥 Clear saved data too
  };

  return (
    <GameContext.Provider
      value={{
        playerName,
        setPlayerName,
        roomCode,
        setRoomCode,
        isHost,
        setIsHost,
        players,
        setPlayers,
        addPlayer,
        socket,
        setSocket,
        clearGame,
      }}
    >
      {children}
    </GameContext.Provider>
  );
};
