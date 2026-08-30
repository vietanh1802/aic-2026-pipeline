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
import Rounds from "./pages/Rounds";
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
  // Name of the round that took over, set when a held task was dropped because
  // its round was retired. Cleared by the next navigation.
  const [roundChanged, setRoundChanged] = useState<string | null>(null);

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

  // Also the guard against working into a round that is no longer live.
  //
  // An admin switching rounds does not reach into anyone's open tab, so a
  // member holding task 07 of the round that was just retired would carry on
  // answering into it — work that no export would ever pick up. Polled on the
  // same timer as presence, and the held task is dropped the moment its round
  // stops being the active one.
  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;
    const check = async () => {
      try {
        const board = await getBoard();
        if (cancelled) {
          return;
        }
        setRowsPerQuery(board.round?.rows_per_query ?? 100);
        setTask((held) => {
          if (!held || !board.round || held.pack_id === board.round.id) {
            return held;
          }
          setRoundChanged(board.round.label);
          setScreen("board");
          return null;
        });
      } catch {
        // A failed poll is not worth a message; the next one is 10s away.
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), HEARTBEAT_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
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
        onNavigate={(next) => {
          setRoundChanged(null);
          setScreen(next);
        }}
        user={user}
        task={task}
        answerCount={answerCount}
        rowsPerQuery={rowsPerQuery}
        onOpenBasket={() => setBasketOpen(true)}
      />

      {roundChanged !== null && (
        <div className="px-4 py-2 bg-[#d4a017]/15 border-b border-[#d4a017] text-[13px] text-[#8a6a0f] font-baloo">
          Vòng thi đã đổi sang <b>{roundChanged}</b>. Task bạn đang mở thuộc vòng
          cũ nên đã được đóng lại — nhận task mới từ bảng bên dưới.
        </div>
      )}

      {screen === "board" && (
        <Board
          onOpenTask={(picked) => {
            setRoundChanged(null);
            setTask(picked);
            setScreen("search");
          }}
        />
      )}
      {screen === "import" && (
        <ImportPack onImported={() => setScreen("rounds")} />
      )}
      {screen === "rounds" && <Rounds />}
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
