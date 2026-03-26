import React, { useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GameContext } from "../context/GameContext";
import "../styles/main.css";

/**
 * GamePage – shown to all players once the host starts the game.
 *
 * Phases:
 *   "waiting"   – navigated here but no question has arrived yet
 *   "voting"    – active question; each player picks someone to vote for
 *   "results"   – all votes are in; round breakdown + running scores shown
 *   "game_over" – all questions done; final leaderboard shown
 *
 * Host controls:
 *   • "Next Question" / "See Final Results" button only appears for the host
 *   • If the host disconnects, the backend promotes the next player and sends
 *     a host_change message so the new host gets the control buttons
 */
function GamePage() {
  const navigate = useNavigate();
  const { playerName, roomCode, players, socket, isHost, setPlayers, clearGame } =
    useContext(GameContext);

  // ── Local game state ───────────────────────────────────────────────────────

  /** Current phase of the game. */
  const [phase, setPhase] = useState("waiting");

  /** Active question: { index, text, total } */
  const [question, setQuestion] = useState(null);

  /**
   * Name of the current host. Starts from context isHost flag, but updates
   * dynamically when a host_change message arrives.
   */
  const [hostName, setHostName] = useState(() =>
    isHost ? playerName : null
  );

  /** The name this player voted for in the current round (null = not yet voted). */
  const [myVote, setMyVote] = useState(null);

  /** Live vote progress: { cast, total } – updated by vote_update messages. */
  const [voteProgress, setVoteProgress] = useState({ cast: 0, total: 0 });

  /**
   * Results for the completed round:
   *   votes       – { voterName: votedForName }
   *   roundScores – { playerName: votesThisRound }
   *   scores      – { playerName: cumulativeVotes }
   */
  const [results, setResults] = useState(null);

  /** Final cumulative scores when the game ends: { playerName: totalVotes } */
  const [finalScores, setFinalScores] = useState(null);

  // Derived: is the current user the host right now?
  const amHost = playerName === hostName;

  // ── Socket message handler ─────────────────────────────────────────────────

  useEffect(() => {
    if (!socket) return;

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        // ── game_state: full snapshot sent in response to request_state ───────
        // Used on initial mount (after start_game navigation) and on reconnect.
        case "game_state": {
          if (msg.players) setPlayers(msg.players);
          if (msg.host)    setHostName(msg.host);

          // Mid-game joiner waiting for the next round to start
          if (msg.phase === "waiting_for_round") {
            setPhase("waiting_mid_game");
            break;
          }

          if (msg.phase === "voting" && msg.question) {
            setQuestion(msg.question);
            setPhase("voting");
            setResults(null);
            // Restore this player's vote if they already voted before reconnecting
            setMyVote(msg.my_vote ?? null);
            if (msg.vote_update) {
              setVoteProgress({ cast: msg.vote_update.cast, total: msg.vote_update.total });
            } else {
              setVoteProgress({ cast: 0, total: msg.question.player_count });
            }
          } else if (msg.phase === "results" && msg.question && msg.results) {
            setQuestion(msg.question);
            setResults({
              votes: msg.results.votes,
              roundScores: msg.results.round_scores,
              scores: msg.results.scores,
            });
            setPhase("results");
          } else if (msg.phase === "end" && msg.scores) {
            setFinalScores(msg.scores);
            setPhase("game_over");
          }
          break;
        }

        // ── question: next round starting (broadcast to all GamePages) ────────
        case "question":
          // players list may have grown (pending players promoted at next_question)
          if (msg.players) setPlayers(msg.players);
          setQuestion({ index: msg.index, text: msg.text, total: msg.total });
          setPhase("voting");
          setMyVote(null);
          // player_count comes from the backend so it's always accurate
          setVoteProgress({ cast: 0, total: msg.player_count });
          setResults(null);
          break;

        // Someone voted – update the live counter (not who voted for whom)
        case "vote_update":
          setVoteProgress({ cast: msg.cast, total: msg.total });
          break;

        // All votes are in – show breakdown and running scores
        case "results":
          setResults({
            votes: msg.votes,
            roundScores: msg.round_scores,
            scores: msg.scores,
          });
          setPhase("results");
          break;

        // All questions answered – show final leaderboard
        case "game_over":
          setFinalScores(msg.scores);
          setPhase("game_over");
          break;

        // A player joined mid-game (e.g. reconnect) – keep list current
        case "join":
          setPlayers((prev) => [...new Set([...prev, msg.name])]);
          break;

        // A player left – remove from list
        case "leave":
          setPlayers((prev) => prev.filter((n) => n !== msg.name));
          break;

        // Host transferred to another player
        case "host_change":
          setHostName(msg.name);
          break;

        default:
          break;
      }
    };

    // Request the full game state now that the handler is registered.
    // This is the fix for the start_game timing race: the backend's `question`
    // broadcast can arrive before this onmessage is set, so we pull state
    // explicitly instead of relying on that broadcast for the first question.
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "request_state" }));
    } else {
      // Socket still connecting (mid-game join) – chain onto onopen so join
      // fires first, then request_state, guaranteeing player_name is set server-side.
      const prevOnOpen = socket.onopen;
      socket.onopen = (e) => {
        if (prevOnOpen) prevOnOpen(e);
        socket.send(JSON.stringify({ type: "request_state" }));
      };
    }
  }, [socket, setPlayers]);

  // ── Actions ────────────────────────────────────────────────────────────────

  /** Cast a vote for another player. Each player can only vote once per round. */
  const handleVote = (name) => {
    if (myVote || !socket) return;
    setMyVote(name);
    socket.send(JSON.stringify({ type: "vote", for: name }));
  };

  /** Host advances to the next question (or triggers game_over). */
  const handleNextQuestion = () => {
    if (socket) socket.send(JSON.stringify({ type: "next_question" }));
  };

  /** Host skips straight to results before all votes are in. */
  const handleSkipToResults = () => {
    if (socket) socket.send(JSON.stringify({ type: "skip_to_results" }));
  };

  /** Leave the game – clears all session state and returns to the landing page. */
  const handleLeave = () => {
    clearGame();
    navigate("/");
  };

  // ── Render helpers ─────────────────────────────────────────────────────────

  /**
   * Sort { name: count } score objects descending by count.
   * Returns [{ name, count }, ...].
   */
  const sortedScores = (scoreObj) =>
    Object.entries(scoreObj)
      .sort(([, a], [, b]) => b - a)
      .map(([name, count]) => ({ name, count }));

  // ── Phase: waiting (mid-game join) ────────────────────────────────────────
  if (phase === "waiting_mid_game") {
    return (
      <div className="container">
        <div className="card">
          <h2 className="title">spillit</h2>
          <p className="waiting-text">Waiting for next round…</p>
        </div>
      </div>
    );
  }

  // ── Phase: waiting ─────────────────────────────────────────────────────────
  if (phase === "waiting") {
    return (
      <div className="container">
        <div className="card">
          <h2 className="title">spillit</h2>
          <p className="waiting-text">Waiting for the game to start…</p>
        </div>
      </div>
    );
  }

  // ── Phase: voting ──────────────────────────────────────────────────────────
  if (phase === "voting") {
    // Other players to vote for – you can't vote for yourself
    const votablePlayers = players.filter((p) => p !== playerName);

    return (
      <div className="container">
        <div className="card game-card">
          {/* Question header */}
          <p className="question-number">
            Question {question.index + 1}
          </p>
          <h2 className="question-text">{question.text}</h2>

          {/* Vote progress bar */}
          <div className="vote-progress-bar">
            <div
              className="vote-progress-fill"
              style={{
                width: voteProgress.total
                  ? `${(voteProgress.cast / voteProgress.total) * 100}%`
                  : "0%",
              }}
            />
          </div>
          <p className="vote-count">
            {voteProgress.cast} / {voteProgress.total} voted
          </p>

          {/* Voting buttons or confirmation message */}
          {!myVote ? (
            <div className="vote-grid">
              {votablePlayers.map((name) => (
                <button
                  key={name}
                  className="vote-button"
                  onClick={() => handleVote(name)}
                >
                  {name}
                </button>
              ))}
            </div>
          ) : (
            <p className="waiting-text">
              You voted for <strong className="highlight">{myVote}</strong>.
              Waiting for others…
            </p>
          )}

          {amHost && (
            <button className="secondary-button" onClick={handleSkipToResults}>
              Skip to Results
            </button>
          )}

          <button className="secondary-button leave-btn" onClick={handleLeave}>
            Leave
          </button>
        </div>
      </div>
    );
  }

  // ── Phase: results ─────────────────────────────────────────────────────────
  if (phase === "results" && results) {
    const isLastQuestion = question && question.index + 1 >= question.total;

    return (
      <div className="container">
        <div className="card game-card">
          <h2 className="title">Results</h2>
          <p className="question-subtext">{question?.text}</p>

          {/* Who got how many votes this round */}
          <p className="section-label">This Round</p>
          <div className="results-list">
            {sortedScores(results.roundScores).map(({ name, count }) => (
              <div key={name} className="result-row">
                <span className="result-name">{name}</span>
                <span className="result-votes">
                  {count} vote{count !== 1 ? "s" : ""}
                </span>
              </div>
            ))}
          </div>

          {/* Running cumulative scores */}
          <p className="section-label">Running Scores</p>
          <div className="scores-list">
            {sortedScores(results.scores).map(({ name, count }, i) => (
              <div
                key={name}
                className={`score-row ${i === 0 && count > 0 ? "leading" : ""}`}
              >
                <span className="score-name">
                  {i === 0 && count > 0 ? "👑 " : ""}
                  {name}
                </span>
                <span className="score-count">{count}</span>
              </div>
            ))}
          </div>

          {/* Host controls */}
          {amHost ? (
            <button className="primary-button" onClick={handleNextQuestion}>
              {isLastQuestion ? "See Final Results →" : "Next Question →"}
            </button>
          ) : (
            <p className="waiting-text">Waiting for host to continue…</p>
          )}

          <p className="room-code">Room: <span>{roomCode}</span></p>
          <button className="secondary-button leave-btn" onClick={handleLeave}>
            Leave
          </button>
        </div>
      </div>
    );
  }

  // ── Phase: game_over ───────────────────────────────────────────────────────
  if (phase === "game_over" && finalScores) {
    const ranked = sortedScores(finalScores);
    const winner = ranked[0];

    return (
      <div className="container">
        <div className="card game-card">
          <h2 className="title">Game Over!</h2>
          {winner && winner.count > 0 && (
            <p className="winner-label">
              👑 {winner.name} wins with {winner.count} vote
              {winner.count !== 1 ? "s" : ""}!
            </p>
          )}

          <p className="section-label">Final Scores</p>
          <div className="scores-list final-scores">
            {ranked.map(({ name, count }, i) => (
              <div
                key={name}
                className={`score-row ${i === 0 && count > 0 ? "winner" : ""}`}
              >
                <span className="score-rank">#{i + 1}</span>
                <span className="score-name">{name}</span>
                <span className="score-count">{count}</span>
              </div>
            ))}
          </div>

          <button className="secondary-button" onClick={handleLeave}>
            Leave Game
          </button>
        </div>
      </div>
    );
  }

  // Fallback while state is settling
  return (
    <div className="container">
      <div className="card">
        <p className="waiting-text">Loading…</p>
      </div>
    </div>
  );
}

export default GamePage;
