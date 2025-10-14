import React from "react";
import { useNavigate } from "react-router-dom";
import "../styles/main.css";

function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="container">
      <h1 className="title">spillit</h1>
      <div className="button-group">
        <button className="primary-button" onClick={() => navigate("/create")}>
          Create New Room
        </button>
        <button className="secondary-button" onClick={() => navigate("/join")}>
          Join Existing Room
        </button>
      </div>
    </div>
  );
}

export default LandingPage;
