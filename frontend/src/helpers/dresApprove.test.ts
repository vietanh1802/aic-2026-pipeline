import { describe, expect, it } from "vitest";

import {
  canSubmitDres,
  describePayload,
  formatMs,
  type DresStatus,
  type DresSubmission,
} from "../api/dres";
import { approveConfirmMessage } from "./dresApprove";

function submission(overrides: Partial<DresSubmission>): DresSubmission {
  return {
    id: 7,
    created_at: "2026-09-24T10:00:00Z",
    proposed_by_name: "vanh",
    reviewed_by_name: null,
    task_type: "kis",
    video_id: "L21_V001",
    frames: [3000],
    times_ms: [100100],
    answer_text: null,
    evaluation_id: "ev-1",
    dres_task_name: "q01",
    payload: {
      answerSets: [{ answers: [{ mediaItemName: "L21_V001", start: 100100, end: 100100 }] }],
    },
    status: "proposed",
    reviewed_at: null,
    verdict: null,
    dres_description: null,
    http_status: null,
    error: null,
    warnings: [],
    ...overrides,
  };
}

describe("dres helpers", () => {
  it("lets admins always submit and members only in everyone mode", () => {
    const status = (submit_mode: DresStatus["submit_mode"]): DresStatus => ({
      configured: true,
      base_url: "x",
      submit_mode,
    });
    expect(canSubmitDres("admin", status("admin_only"))).toBe(true);
    expect(canSubmitDres("member", status("admin_only"))).toBe(false);
    expect(canSubmitDres("member", status("everyone"))).toBe(true);
    // Chưa tải được trạng thái thì coi như chế độ mặc định — không bày nút nộp.
    expect(canSubmitDres("member", null)).toBe(false);
  });

  it("formats milliseconds as mm:ss.mmm", () => {
    expect(formatMs(100100)).toBe("01:40.100");
    expect(formatMs(0)).toBe("00:00.000");
    expect(formatMs(3599999)).toBe("59:59.999");
  });

  it("describes a KIS payload by video and time, a text payload verbatim", () => {
    expect(describePayload(submission({}))).toBe("L21_V001 @ 100100 ms");
    const qa = submission({
      task_type: "qa",
      payload: { answerSets: [{ answers: [{ text: "QA-mau xanh-L21_V001-100100" }] }] },
    });
    expect(describePayload(qa)).toBe("QA-mau xanh-L21_V001-100100");
  });

  it("puts the exact string, the task, the warnings and the penalty in the confirm box", () => {
    const message = approveConfirmMessage(
      submission({
        video_id: "N001-V001",
        task_type: "qa",
        payload: { answerSets: [{ answers: [{ text: "QA-x-N001-V001-5" }] }] },
        warnings: ["Tên video có dấu '-'"],
      })
    );
    expect(message).toContain("QA-x-N001-V001-5");
    expect(message).toContain("q01");
    expect(message).toContain("⚠ Tên video có dấu '-'");
    expect(message).toContain("trừ 10 điểm");
  });
});
