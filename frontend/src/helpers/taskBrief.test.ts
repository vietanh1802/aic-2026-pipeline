import { describe, expect, it } from "vitest";

import { taskBriefText, taskQueryForSearch } from "./taskBrief";

// Hợp đồng mới của hai hàm này chỉ có một câu: trả lại đúng chữ ban tổ chức
// viết. Bộ test cũ khẳng định điều ngược lại — nó chốt cách dựng đề bài lại từ
// `event_labels` ("E1 · Một → E2 · Hai") và cách ghép chúng thành truy vấn
// ("Một. Hai"), kể cả một test round-trip qua `splitQueryParts` để bảo đảm số
// đoạn khớp `n_events`.
//
// Cả hai đã bỏ cùng lúc với việc trình đọc gói thôi tách E1..EN ra khỏi đề
// bài. Chi tiết vì sao nằm trong docstring của taskBrief.ts; phần đáng nhớ:
// nhánh `query_text` luôn ăn trước, nên với bộ SOTUYEN2 — nơi mọi file TRAKE
// mở đầu bằng một dòng dẫn nhập — nhánh ghép mốc không bao giờ chạy, và bốn
// câu tả thật của câu 8 không hề đi vào truy vấn.

describe("taskBriefText", () => {
  it("returns the prose for a KIS task", () => {
    expect(
      taskBriefText({
        type: "kis",
        query_text: "Tìm cảnh người đàn ông mặc áo đỏ",
        event_labels: [],
      })
    ).toBe("Tìm cảnh người đàn ông mặc áo đỏ");
  });

  // Đây là hình dạng thật của một file TRAKE trong SOTUYEN2: một dòng dẫn nhập
  // rồi tới các mốc, tất cả nằm trong cùng một chuỗi.
  it("returns a TRAKE brief verbatim, newlines and all", () => {
    const body =
      "Video về một khu vườn cây ăn trái ở miền Tây Nam Bộ.\n" +
      "E1: Cảnh đầu tiên có trái sầu riêng.\n" +
      "E2: Cảnh đầu tiên có trái măng cụt.";
    expect(
      taskBriefText({ type: "trake", query_text: body, event_labels: [] })
    ).toBe(body);
  });

  // event_labels không còn được đọc. Cột vẫn tồn tại trong DB nên giá trị cũ
  // của những vòng nhập trước đó vẫn có thể có mặt — và phải bị bỏ qua, không
  // được lặng lẽ chen vào chỗ đề bài.
  it("ignores event_labels even when a legacy row still carries them", () => {
    expect(
      taskBriefText({
        type: "trake",
        query_text: "Đề bài nguyên văn",
        event_labels: ["Người mở cửa", "Người bước vào"],
      })
    ).toBe("Đề bài nguyên văn");
  });

  it("returns an empty string when the brief is empty", () => {
    expect(
      taskBriefText({ type: "trake", query_text: "", event_labels: [] })
    ).toBe("");
  });
});

describe("taskQueryForSearch", () => {
  it("collapses whitespace in a prose brief", () => {
    expect(
      taskQueryForSearch({
        type: "kis",
        query_text: "  Hai người   phụ nữ\n cho dê ăn  ",
        event_labels: [],
      })
    ).toBe("Hai người phụ nữ cho dê ăn");
  });

  // Ô search là một dòng, nên xuống dòng phải thành khoảng trắng — nhưng KHÔNG
  // được mất chữ nào. Đây chính là ca câu 8 từng hỏng: bốn mốc bị vứt, chỉ còn
  // dòng dẫn nhập đi vào truy vấn.
  it("carries every line of a TRAKE brief into one line", () => {
    const query = taskQueryForSearch({
      type: "trake",
      query_text:
        "Video về một khu vườn cây ăn trái.\n" +
        "E1: Cảnh đầu tiên có trái sầu riêng.\n" +
        "E2: Cảnh đầu tiên có trái măng cụt.",
      event_labels: [],
    });
    expect(query).toBe(
      "Video về một khu vườn cây ăn trái. " +
        "E1: Cảnh đầu tiên có trái sầu riêng. " +
        "E2: Cảnh đầu tiên có trái măng cụt."
    );
    expect(query).toContain("sầu riêng");
    expect(query).toContain("măng cụt");
  });

  it("ignores event_labels even when a legacy row still carries them", () => {
    expect(
      taskQueryForSearch({
        type: "trake",
        query_text: "Đề bài nguyên văn",
        event_labels: ["Một", "Hai"],
      })
    ).toBe("Đề bài nguyên văn");
  });

  it("returns an empty string when there is nothing to search for", () => {
    expect(
      taskQueryForSearch({ type: "trake", query_text: "", event_labels: [] })
    ).toBe("");
  });
});
