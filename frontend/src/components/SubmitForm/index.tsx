import React, { useEffect, useRef, useState } from "react";
import Button from "../Button";
import { SuperSimple } from "./RangeForm";
import {
  useSubmitStore,
  useSubmitTasks,
  type SubmitType,
} from "../../store/submitStore";
import type { DropdownOption } from "../DropDown";
import Dropdown from "../DropDown";
import { getValues } from "../../helpers/getValues.helper";
import { frameAt, frameRange, spreadFrames } from "../../helpers/frameRange";
import { addAnswer } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import type { TrakeSlot } from "../VideoPopUp";
import { useAuthStore } from "../../store/authStore";
import { gapi } from "gapi-script";
// ====== GOOGLE API CONFIG ======
const CLIENT_ID =
  "530488029353-4bib5u218f93bm22mrtkgeajge477gra.apps.googleusercontent.com";
const API_KEY = "AIzaSyDfWgoJNwd92S8YfviSokzKuW3FCCckbZc";
const SCOPES =
  "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive";
const DISCOVERY_DOCS = [
  "https://sheets.googleapis.com/$discovery/rest?version=v4",
  "https://www.googleapis.com/discovery/v1/apis/drive/v3/rest",
];
const FOLDER_ID = "1iBejYQg8sWKeFmu5gCuUIUIjus2aTUE9";
// =================================

type GoogleTokenResponse = {
  access_token?: string;
  error?: string;
};

type GoogleTokenClient = {
  requestAccessToken: () => void;
};

type GoogleIdentity = {
  accounts: {
    oauth2: {
      initTokenClient: (config: {
        client_id: string;
        scope: string;
        callback: (response: GoogleTokenResponse) => void;
      }) => GoogleTokenClient;
    };
  };
};

type WindowWithGoogleIdentity = Window & {
  google?: GoogleIdentity;
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : JSON.stringify(err);
}

interface SubmitFormData {
  videoId: string;
  duration: number;
  startAt: number;
  setStartAt: (val: number) => void;
  frame_detect: number;
  /** Task đang mở từ Board. Có nó thì Add Answer ghi thẳng vào cơ sở dữ liệu. */
  activeTask?: BoardTask | null;
  onBasketChanged?: () => void;
  /** Mép của khoảnh khắc, ghim từ dải điều khiển ngay dưới video. Null = chưa
   *  ghim, và chưa ghim cả hai thì nộp đúng frame như trước. */
  markIn?: number | null;
  markOut?: number | null;
  /** The player's exact position, read at the moment of submitting. */
  getPlayhead?: () => number;
  /** Set when the popup was opened on one event of a TRAKE line. */
  trakeSlot?: TrakeSlot | null;
}

export const SubmitForm: React.FC<SubmitFormData> = ({
  videoId,
  duration,
  startAt,
  setStartAt,
  frame_detect,
  activeTask = null,
  onBasketChanged,
  markIn = null,
  markOut = null,
  getPlayhead,
  trakeSlot = null,
}) => {
  const [answer, setAnswer] = useState<string>("");
  const [values, setValues] = useState(getValues(startAt, duration));
  const [, setSpreadsheetId] = useState<string | null>(null);
  const me = useAuthStore((state) => state.user);

  const submissionFileName = useSubmitStore((state) => state.submissonFileName);

  const submitType = useSubmitStore((state) => state.submitType);
  const setSubmitType = useSubmitStore((state) => state.setSubmitType);

  // TRAKE keeps the old single-instant path: one row carries one frame per
  // event, so a midpoint between two edges has no slot to go in yet.
  const isTrakeAnswer =
    activeTask !== null
      ? activeTask.type === "trake"
      : submitType === "Task 3 - trake";

  // Read at submit time, not at render time: the player moves without React
  // hearing about it between renders.
  const frameToSubmit = (): number => {
    const now = getPlayhead ? getPlayhead() : startAt;
    const here = frameAt(now, frame_detect);
    if (isTrakeAnswer) {
      return here ?? Number.NaN;
    }
    return frameRange(markIn ?? now, markOut ?? now, frame_detect)?.frame
      ?? here ?? Number.NaN;
  };

  // ── Trải K dòng ──────────────────────────────────────────────────────────
  const [spreadK, setSpreadK] = useState<number>(5);
  const [spreadNote, setSpreadNote] = useState<string | null>(null);
  const [spreading, setSpreading] = useState<boolean>(false);

  // Both edges marked, a real task open, and not TRAKE — a TRAKE row is N
  // moments in one row, so K rows over an interval means nothing there. The
  // mark strip is already disabled for TRAKE, so this can never light up.
  const canSpread =
    activeTask !== null &&
    activeTask.type !== "trake" &&
    // Same rule as the answer basket: a task with an owner who is not you is
    // read-only at the UI layer. Boolean() first, because an unclaimed task has
    // no owner and must not lock out the person holding it.
    !(Boolean(activeTask.owner) && activeTask.owner?.id !== me?.id) &&
    markIn !== null &&
    markOut !== null &&
    Number.isFinite(frame_detect) &&
    frame_detect > 0;

  const spreadOptions: DropdownOption[] = [
    { id: 0, label: "3 dòng", value: "3" },
    { id: 1, label: "5 dòng", value: "5" },
    { id: 2, label: "7 dòng", value: "7" },
    { id: 3, label: "9 dòng", value: "9" },
  ];

  /**
   * Sequential on purpose, and not atomic.
   *
   * The rows are ranked in the order they arrive, and that order is the whole
   * point — it is the bisection priority. Firing them together would rank them
   * by whichever response came back first. A failure part-way leaves the rows
   * that landed in place: they are correct rows, individually deletable, and
   * silently rolling them back would be worse than saying how far it got.
   */
  const handleSpread = async () => {
    if (!activeTask || markIn === null || markOut === null) {
      return;
    }
    const range = frameRange(markIn, markOut, frame_detect);
    if (!range) {
      setSpreadNote(`Không tính được frame: thiếu fps cho ${videoId}`);
      return;
    }
    const frames = spreadFrames(range.start, range.end, spreadK);
    if (frames.length === 0) {
      setSpreadNote("Khoảng đã ghim không có frame nào");
      return;
    }

    setSpreading(true);
    let added = 0;
    try {
      for (const frame of frames) {
        await addAnswer(activeTask.id, {
          video_id: videoId,
          frames: [frame],
          answer_text: activeTask.type === "qa" ? answer || null : null,
        });
        added += 1;
        setSpreadNote(`${added}/${frames.length}…`);
        onBasketChanged?.();
      }
      setSpreadNote(`Đã thêm ${added}/${frames.length} dòng`);
    } catch (err) {
      console.error("Trải K dòng dừng giữa chừng:", err);
      setSpreadNote(`Đã thêm ${added}/${frames.length} dòng rồi dừng vì lỗi`);
    } finally {
      setSpreading(false);
    }
  };

  const { task1, task2, task3, addTask1, addTask2, addTask3 } =
    useSubmitTasks();

  const submitTypeOptions: DropdownOption[] = [
    { id: 0, label: "Task 1 - KIS", value: "Task 1 - kis" as SubmitType },
    { id: 1, label: "Task 2 - Q&A", value: "Task 2 - qna" as SubmitType },
    { id: 2, label: "Task 3 - TRAKE", value: "Task 3 - trake" as SubmitType },
  ];

  // Google is loaded on demand, not on mount.
  //
  // Both of these used to run in a useEffect the moment the video popup opened,
  // so every single frame anyone inspected fetched accounts.google.com and
  // initialised the Sheets and Drive discovery documents — third-party round
  // trips in front of a video the user wanted to watch, for a button most
  // sessions never press. Now the first click on Create Sheet pays that cost,
  // once, and the promise is cached so a second click does not repeat it.
  const googleReady = useRef<Promise<void> | null>(null);

  const loadGoogle = (): Promise<void> => {
    if (googleReady.current) {
      return googleReady.current;
    }
    googleReady.current = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => {
        gapi.load("client", () => {
          gapi.client
            .init({ apiKey: API_KEY, discoveryDocs: DISCOVERY_DOCS })
            .then(() => resolve())
            .catch(reject);
        });
      };
      script.onerror = () => reject(new Error("Không tải được Google Identity"));
      document.body.appendChild(script);
    });
    return googleReady.current;
  };

  // Hàm login bằng GIS -> trả access_token
  const getAccessToken = (): Promise<string> => {
    return new Promise((resolve, reject) => {
      const google = (window as WindowWithGoogleIdentity).google;
      if (!google) {
        reject("Google script chưa load");
        return;
      }

      const tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: CLIENT_ID,
        scope: SCOPES,
        callback: (response) => {
          if (response.error || !response.access_token) {
            reject(response);
          } else {
            gapi.client.setToken({ access_token: response.access_token });
            resolve(response.access_token);
          }
        },
      });

      tokenClient.requestAccessToken();
    });
  };

  // === GOOGLE SHEETS HANDLER ===
  const createSheet = async () => {
    try {
      await loadGoogle(); // nạp GIS + gapi lần đầu bấm nút này
      await getAccessToken(); // login + set token cho gapi

      let rows: string[][] = [];
      let sheetTitle = submissionFileName || "";

      switch (submitType) {
        case "Task 1 - kis":
          // rows = [["videoId", "frameIdx"], ...task1.map((i) => [i.videoId, i.frameIdx])];
          rows = task1.map((i) => [i.videoId, i.frameIdx]);
          sheetTitle = sheetTitle || "Task 1 Sheet";
          break;
        case "Task 2 - qna":
          // rows = [["videoId", "frameIdx", "answer"], ...task2.map((i) => [i.videoId, i.frameIdx, i.answer])];
          rows = task2.map((i) => [i.videoId, i.frameIdx, i.answer]);
          sheetTitle = sheetTitle || "Task 2 Sheet";
          break;
        case "Task 3 - trake":
          // rows = [["videoId", "frames..."], ...task3.map((i) => [i.videoId, ...i.frameIdx])];
          // rows = task3.flatMap((i) =>
          //   i.frameIdx.map((frame: string | number) => [i.videoId, frame])
          // );
          rows = task3.map((i) => [i.videoId, ...i.frameIdx]);
          sheetTitle = sheetTitle || "Task 3 Sheet";
          break;
        default:
          alert("Chưa chọn loại Task!");
          return;
      }

      if (rows.length < 1) {
        alert("Chưa có dữ liệu cho " + submitType);
        return;
      }

      // 1. Tạo Sheet
      const sheetResponse = await gapi.client.sheets.spreadsheets.create({
        properties: { title: sheetTitle },
      });
      const id = sheetResponse.result.spreadsheetId!;
      setSpreadsheetId(id);
      console.log("✅ Sheet created:", id);

      // 2. Move vào folder
      await gapi.client.drive.files.update({
        fileId: id,
        addParents: FOLDER_ID,
        fields: "id, parents",
      });
      console.log("📂 File moved to folder:", FOLDER_ID);

      // 3. Append dữ liệu
      await gapi.client.sheets.spreadsheets.values.append({
        spreadsheetId: id,
        range: "Sheet1!A1",
        valueInputOption: "RAW",
        resource: { values: rows },
      });
      console.log("📝 Data appended");

      alert(`✅ Created new sheet trong folder ${FOLDER_ID}, ID: ${id}`);
    } catch (err: unknown) {
      console.error("❌ Error creating sheet:", err);
      alert("Failed: " + errorMessage(err));
    }
  };

  const handleSubmit = async () => {
    // Midpoint of the marked edges for KIS and Q&A; the raw playhead for TRAKE
    // and for a video whose fps is unknown. frameRange() returns null in that
    // second case, which is also why the button is disabled there.
    const frame = frameToSubmit();
    if (!Number.isFinite(frame)) {
      console.error("Không tính được frame: thiếu fps cho", videoId);
      return;
    }

    // Có task đang mở thì đây là đường ghi thật: một hàng trong bảng answers,
    // sống qua F5 và đồng đội thấy được. Giỏ Zustand bên dưới chỉ còn là đường
    // lùi cho lúc chưa nhận task nào — trước đây nó là đường duy nhất, và đó là
    // lý do bấm Add Answer xong số trên thanh nav vẫn đứng yên.
    // Pinning one moment of a TRAKE line. Nothing is written to the basket
    // here — the line becomes an answer only once all N cells are filled and
    // the row's own button is pressed.
    if (trakeSlot) {
      trakeSlot.onCommit(frame);
      return;
    }

    if (activeTask) {
      try {
        await addAnswer(activeTask.id, {
          video_id: videoId,
          frames: [frame],
          answer_text: activeTask.type === "qa" ? answer || null : null,
        });
        onBasketChanged?.();
        if (activeTask.type !== "trake") {
          setAnswer("");
        }
        return;
      } catch (err) {
        console.error("Không thêm được vào giỏ:", err);
        return;
      }
    }

    switch (submitType) {
      case "Task 1 - kis":
        addTask1(videoId, String(frame));
        console.log("Task 1 Done");
        break;
      case "Task 2 - qna":
        addTask2(videoId, String(frame), answer);
        break;
      case "Task 3 - trake":
        addTask3(
          videoId,
          String(frame),
          Number(answer)
        );
        break;
    }
    if (submitType != "Task 3 - trake") {
      setAnswer("");
    }
  };

  useEffect(() => {
    console.log("task1", task1);
    console.log("task2", task2);
    console.log("task3", task3);
    console.log("Filename:", submissionFileName);
  }, [task1, task2, task3, submissionFileName]);

  // const createCSV = () => {
  //   let csvString = "";
  //   switch (submitType) {
  //     case "Task 1 - kis":
  //       csvString = task1
  //         .map((item) => `${item.videoId}, ${item.frameIdx}`)
  //         .join("\n");
  //       break;

  //     case "Task 2 - qna":
  //       csvString = task2
  //         .map(
  //           (item) =>
  //             `${item.videoId}, ${item.frameIdx}, ${escape(item.answer)}`
  //         )
  //         .join("\n");
  //       break;

  //     case "Task 3 - trake":
  //       csvString = task3
  //         .map((item) => `${item.videoId},${item.frameIdx.join(",")}`)
  //         .join("\n");
  //       break;
  //   }

  //   return csvString;
  // };

  return (
    <>
      <div className="flex items-start gap-4 w-full">
        <div className="flex flex-col gap-4 flex-1 rounded-md border border-gray-300 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-700">Range</label>
            <SuperSimple
              min={0}
              max={duration}
              values={values}
              setValues={setValues}
              setStartAt={setStartAt}
            />
          </div>

          {/* Input — nothing to type when pinning a TRAKE moment. */}

          {!trakeSlot && (
            <input
              type={submitType == "Task 2 - qna" ? "text" : "number"}
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder={
                submitType == "Task 2 - qna"
                  ? "Type in your answer"
                  : "Type in the number of activities"
              }
              className="w-full rounded-md border border-gray-300 p-2 text-sm focus:border-blue-400 focus:ring focus:ring-blue-100 outline-none"
              disabled={submitType === "Task 1 - kis"}
            />
          )}
        </div>

        <div className="flex flex-col gap-3 h-full">
          {/* The task-type picker and the Sheets export are both about a whole
              submission file. Pinning one TRAKE moment is neither. */}
          {!trakeSlot && (
            <Dropdown
              options={submitTypeOptions}
              value={submitType}
              onChange={(opt) => setSubmitType(opt.value as SubmitType)}
              dropDownWidth={194}
              dropDirection="up"
            />
          )}
          <div className="flex gap-3 items-stretch">
            <Button
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10 "
              onClick={handleSubmit}
              size="xs"
              // No fps for this video means every frame number downstream is
              // NaN. It used to submit that; now it says so and stops.
              disabled={!Number.isFinite(frame_detect) || frame_detect <= 0}
            >
              {trakeSlot ? `Chốt cho E${trakeSlot.index + 1}` : "Add Answer"}
            </Button>
            {!trakeSlot && (
              <Button
                className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10 "
                size="xs"
                onClick={createSheet}
              >
                Create Sheet
              </Button>
            )}
          </div>

          {/* Item 5 — one press instead of "add the edges, add the middle,
              then subdivide", which is minutes of clicking per query. */}
          {!trakeSlot && (
            <div className="flex flex-col gap-1">
              <div className="flex gap-2 items-stretch">
                <Dropdown
                  options={spreadOptions}
                  value={String(spreadK)}
                  onChange={(opt) => setSpreadK(Number(opt.value))}
                  dropDownWidth={96}
                  dropDirection="up"
                  size="sm"
                />
                <Button
                  className="bg-proto-primary hover:opacity-90 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10"
                  size="xs"
                  onClick={() => void handleSpread()}
                  disabled={!canSpread || spreading}
                  title={
                    canSpread
                      ? "Trải đều K dòng trên đoạn đã ghim"
                      : activeTask &&
                        Boolean(activeTask.owner) &&
                        activeTask.owner?.id !== me?.id
                      ? "Giỏ của người khác — chỉ đọc"
                      : "Ghim cả điểm đầu và điểm cuối trước"
                  }
                >
                  {spreading ? spreadNote ?? "Đang thêm…" : `Trải ${spreadK} dòng`}
                </Button>
              </div>
              {!spreading && spreadNote && (
                <span className="text-[11px] text-proto-muted">{spreadNote}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};
