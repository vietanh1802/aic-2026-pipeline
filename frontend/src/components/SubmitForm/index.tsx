import React, { useEffect, useState } from "react";
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
import { addAnswer } from "../../api/answers";
import type { BoardTask } from "../../api/board";
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
}

export const SubmitForm: React.FC<SubmitFormData> = ({
  videoId,
  duration,
  startAt,
  setStartAt,
  frame_detect,
  activeTask = null,
  onBasketChanged,
}) => {
  const [answer, setAnswer] = useState<string>("");
  const [values, setValues] = useState(getValues(startAt, duration));
  const [, setSpreadsheetId] = useState<string | null>(null);

  const submissionFileName = useSubmitStore((state) => state.submissonFileName);

  const submitType = useSubmitStore((state) => state.submitType);
  const setSubmitType = useSubmitStore((state) => state.setSubmitType);

  const { task1, task2, task3, addTask1, addTask2, addTask3 } =
    useSubmitTasks();

  const submitTypeOptions: DropdownOption[] = [
    { id: 0, label: "Task 1 - KIS", value: "Task 1 - kis" as SubmitType },
    { id: 1, label: "Task 2 - Q&A", value: "Task 2 - qna" as SubmitType },
    { id: 2, label: "Task 3 - TRAKE", value: "Task 3 - trake" as SubmitType },
  ];

  // const escape = (val: string) => `"${val.replace(/"/g, "")}"`;
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    script.onload = () => {
      console.log("✅ GIS script loaded");
    };
  }, []);

  // === INIT GOOGLE API + GIS ===
  useEffect(() => {
    function start() {
      gapi.client
        .init({
          apiKey: API_KEY,
          discoveryDocs: DISCOVERY_DOCS,
        })
        .then(() => {
          console.log("✅ GAPI client initialized");
        });
    }
    gapi.load("client", start);
  }, []);

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
    const frame = Math.floor(startAt * frame_detect);

    // Có task đang mở thì đây là đường ghi thật: một hàng trong bảng answers,
    // sống qua F5 và đồng đội thấy được. Giỏ Zustand bên dưới chỉ còn là đường
    // lùi cho lúc chưa nhận task nào — trước đây nó là đường duy nhất, và đó là
    // lý do bấm Add Answer xong số trên thanh nav vẫn đứng yên.
    if (activeTask) {
      const frames =
        activeTask.type === "trake"
          ? Array.from({ length: activeTask.n_events ?? 1 }, () => frame)
          : [frame];
      try {
        await addAnswer(activeTask.id, {
          video_id: videoId,
          frames,
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
        addTask1(videoId, String(Math.floor(startAt * frame_detect)));
        console.log("Task 1 Done");
        break;
      case "Task 2 - qna":
        addTask2(videoId, String(Math.floor(startAt * frame_detect)), answer);
        break;
      case "Task 3 - trake":
        addTask3(
          videoId,
          String(Math.floor(startAt * frame_detect)),
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

          {/* Input */}

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
        </div>

        <div className="flex flex-col gap-3 h-full">
          <Dropdown
            options={submitTypeOptions}
            value={submitType}
            onChange={(opt) => setSubmitType(opt.value as SubmitType)}
            dropDownWidth={194}
            dropDirection="up"
          />
          <div className="flex gap-3 items-stretch">
            <Button
              // leadingIcon={<img src="/send.svg" />}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10 "
              onClick={handleSubmit}
              size="xs"
            >
              Add Answer
            </Button>
            <Button
              // leadingIcon={<img src="/send.svg" />}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10 "
              size="xs"
              onClick={createSheet}
            >
              Create Sheet
            </Button>
          </div>
        </div>
      </div>
    </>
  );
};
