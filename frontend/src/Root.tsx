import { useCallback, useEffect, useState } from "react";

import App from "./App";
import { getAnswers } from "./api/answers";
import { me } from "./api/auth";
import { getBoard, heartbeat, type BoardTask } from "./api/board";
import AnswerBasket from "./components/AnswerBasket";
import AppNav, { type Screen } from "./components/AppNav";
import Board from "./pages/Board";
import ChangePassword from "./pages/ChangePassword";
import ExportPage from "./pages/Export";
import ImportPack from "./pages/ImportPack";
import Login from "./pages/Login";
import { useAuthStore } from "./store/authStore";

const HEARTBEAT_MS = 10000;

/**
 * All of the routing there is. A router library buys nothing while there are
 * four screens and no URL worth sharing, and it would mean restructuring
 * App.tsx — which stays exactly the search screen it already is.
 *
 * Every hook runs before the first return, because the number of hooks a
 * component calls may not change between renders.
 */
export default function Root() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);

  const [screen, setScreen] = useState<Screen>("board");
  const [task, setTask] = useState<BoardTask | null>(null);
  const [answerCount, setAnswerCount] = useState(0);
  const [rowsPerQuery, setRowsPerQuery] = useState(100);
  const [basketOpen, setBasketOpen] = useState(false);

  useEffect(() => {
    if (!token) {
      return;
    }
    // A token restored from localStorage may already be dead, and only the
    // server knows. apiFetch clears the store on 401, so this both refreshes
    // the user and evicts a stale session on reload.
    void me()
      .then((response) => setUser(response.user))
      .catch(() => undefined);
  }, [token, setUser]);

  useEffect(() => {
    if (!token) {
      return;
    }
    void getBoard()
      .then((board) => setRowsPerQuery(board.round?.rows_per_query ?? 100))
      .catch(() => undefined);
  }, [token]);

  // Presence: tells teammates which task you are looking at. Cheap enough to
  // send on a timer, and it is the only thing keeping the viewer list honest.
  useEffect(() => {
    if (!token || !user || user.must_change_password) {
      return;
    }
    const beat = () => void heartbeat(task?.id ?? null).catch(() => undefined);
    beat();
    const timer = window.setInterval(beat, HEARTBEAT_MS);
    return () => window.clearInterval(timer);
  }, [token, user, task]);

  const refreshCount = useCallback(async () => {
    if (!task) {
      setAnswerCount(0);
      return;
    }
    try {
      setAnswerCount((await getAnswers(task.id)).answers.length);
    } catch {
      // The count is decoration; a failed poll is not worth a message.
    }
  }, [task]);

  useEffect(() => {
    void refreshCount();
  }, [refreshCount, basketOpen]);

  if (!token || !user) {
    return <Login />;
  }
  if (user.must_change_password) {
    return <ChangePassword />;
  }

  return (
    <>
      <AppNav
        screen={screen}
        onNavigate={setScreen}
        user={user}
        task={task}
        answerCount={answerCount}
        rowsPerQuery={rowsPerQuery}
        onOpenBasket={() => setBasketOpen(true)}
      />

      {screen === "board" && (
        <Board
          onOpenTask={(picked) => {
            setTask(picked);
            setScreen("search");
          }}
        />
      )}
      {screen === "import" && (
        <ImportPack onImported={() => setScreen("board")} />
      )}
      {screen === "export" && <ExportPage />}

      {/* Kept mounted rather than unmounted, so switching to the board and back
          does not throw away the current search results. */}
      <div hidden={screen !== "search"}>
        <App activeTask={task} onBasketChanged={() => void refreshCount()} />
      </div>

      <AnswerBasket
        task={task}
        rowsPerQuery={rowsPerQuery}
        open={basketOpen}
        onClose={() => {
          setBasketOpen(false);
          void refreshCount();
        }}
      />
    </>
  );
}
