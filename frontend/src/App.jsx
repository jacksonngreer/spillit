import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import CreatePage from "./pages/CreatePage";
import LandingPage from "./pages/LandingPage";
import LobbyPage from "./pages/LobbyPage";
import JoinPage from "./pages/JoinPage";
import GamePage from "./pages/GamePage";


function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/create" element={<CreatePage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="/game" element={<GamePage />} />
        <Route path="/lobby" element={<LobbyPage />} />
      </Routes>
    </Router>
  );
}

export default App;
