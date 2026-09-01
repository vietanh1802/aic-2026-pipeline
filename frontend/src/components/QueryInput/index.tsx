"use client";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import {
  useQueryStore,
  type SearchType,
  type TranslateLanguage,
} from "../../store/queryStore";
import type { ModelName } from "../../types/api";
import { useState } from "react";

interface QueryInputProps {
  doSearch: () => void;
  disabled?: boolean;
}

export default function QueryInput({ doSearch, disabled = false }: QueryInputProps) {
  const resultLimit = useQueryStore((state) => state.resultLimit);
  const setResultLimit = useQueryStore((state) => state.setResultLimit);
  const queryText = useQueryStore((state) => state.queryText);
  const setQueryText = useQueryStore((state) => state.setQueryText);

  const searchType = useQueryStore((state) => state.searchType);
  const setSearchType = useQueryStore((state) => state.setSearchType);
  const singleModel = useQueryStore((state) => state.singleModel);
  const setSingleModel = useQueryStore((state) => state.setSingleModel);

  const topM = useQueryStore((state) => state.topM);
  const setTopM = useQueryStore((state) => state.setTopM);
  const useRerank = useQueryStore((state) => state.useRerank);
  const setUseRerank = useQueryStore((state) => state.setUseRerank);

  const ocrStripDiacritics = useQueryStore((state) => state.ocrStripDiacritics);
  const setOcrStripDiacritics = useQueryStore(
    (state) => state.setOcrStripDiacritics
  );
  const isOcr = searchType === "ocr";

  const translateLang = useQueryStore((state) => state.translateLang);
  const setTranslateLang = useQueryStore((state) => state.setTranslateLang);
  // `queryTranslated` chỉ còn được GHI, không đọc: bản dịch giờ nằm ngay trong
  // ô nhập nên không có gì để hiển thị riêng nữa.
  const setQueryTranslated = useQueryStore(
    (state) => state.setQueryTranslated
  );
  // Advanced controls (Show Top, Top-M, Rerank, Language, Translate, Search
  // Type) collapse behind a toggle, closed by default — during a round the
  // user just types and hits Enter, and rarely touches these controls.
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  /**
   * Dịch xong thì ghi thẳng vào ô nhập bên dưới, không hiện bảng xem trước.
   *
   * Cách cũ đặt bản dịch vào một ô chỉ-đọc nằm PHÍA TRÊN cụm tuỳ chọn, kèm
   * tiêu đề "Dịch" và nút X. Bản dịch nằm ở đó thì không tìm được gì cả —
   * nút Search vẫn đọc ô dưới, tức là vẫn câu tiếng Việt — nên vẫn phải tự
   * bôi đen, copy, rồi dán xuống. Ba thao tác cho một việc đáng lẽ là không
   * thao tác nào, cộng thêm hai dòng chiếm chỗ trên màn hình.
   *
   * Bản gốc không giữ lại được: muốn quay về thì đổi chiều dịch (en-vi) rồi
   * bấm Translate lần nữa. Vẫn ghi vào `queryTranslated` để biết câu đang nằm
   * trong ô là do máy dịch ra.
   */
  const handleTranslate = async () => {
    if (!queryText) return;
    const targetLang = translateLang === "vi-en" ? "en" : "vi";
    try {
      const res = await fetch(
        `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=${encodeURIComponent(
          queryText
        )}`
      );
      const data = await res.json();
      const translated = data[0];
      const texts = translated.map((item: string[]) => item[0]);
      const result = texts.join("");
      if (!result) return;
      setQueryTranslated(result);
      setQueryText(result);
    } catch (err) {
      // Dịch hỏng thì giữ nguyên câu đang gõ. Ném ra ngoài sẽ thành lỗi
      // không ai bắt, mà thứ người dùng vừa gõ thì biến mất.
      console.error("Không dịch được:", err);
    }
  };

  // The OCR route can go deeper: it calls no model, so 2000 rows cost only a
  // few dozen extra milliseconds. On the visual route every row is a reranked
  // FAISS vector, where 500 is both plenty and the backend's ceiling.
  const resultLimitOptions: DropdownOption[] = isOcr
    ? [
        { id: 0, label: "50", value: "50" },
        { id: 1, label: "100", value: "100" },
        { id: 2, label: "500", value: "500" },
        { id: 3, label: "2000", value: "2000" },
      ]
    : [
        { id: 0, label: "10", value: "10" },
        { id: 1, label: "50", value: "50" },
        { id: 2, label: "100", value: "100" },
        { id: 3, label: "500", value: "500" },
      ];

  const topMOptions: DropdownOption[] = [
    { id: 0, label: "20", value: "20" },
    { id: 1, label: "50", value: "50" }, // paper dùng M=50
    { id: 2, label: "100", value: "100" },
    { id: 3, label: "200", value: "200" },
  ];

  const transLangOptions: DropdownOption[] = [
    { id: 0, label: "vi-en", value: "vi-en" as TranslateLanguage },
    { id: 1, label: "en-vi", value: "en-vi" as TranslateLanguage },
  ];

  // Khớp đúng /ensemble-search (Alg.3 đầy đủ), /single-search (Q4: so model
  // đơn với ensemble), /temporal-search-text (Alg.4) và /trake-search-text
  // (N sự kiện tuần tự) — 2 cái sau nhận query bằng cách tách 1 chuỗi theo
  // dấu "." ở backend, khung nhập KHÔNG đổi gì (vẫn 1 ô input như cũ).
  const searchOptions: DropdownOption[] = [
    { id: 0, label: "Ensemble (BEiT3+CLIP)", value: "ensemble" as SearchType },
    { id: 1, label: "Single Model", value: "single" as SearchType },
    { id: 2, label: "Temporal Search (Alg.4)", value: "temporal" as SearchType },
    { id: 3, label: "TRAKE (N sự kiện)", value: "trake" as SearchType },
    // id 5, không phải 4: nhánh feature/asr-multimodal-retrieval chèn
    // "Visual + Speech" vào id 2 và đẩy temporal/trake thành 3/4. Lấy 4 ở đây
    // là sau khi merge có hai mục cùng id — Dropdown dùng id để định danh và
    // điều hướng bàn phím (xem DropDown/index.tsx), nên trùng id làm chọn sai
    // mục mà không báo lỗi gì.
    { id: 5, label: "OCR — chữ trên màn hình", value: "ocr" as SearchType },
  ];

  const modelOptions: DropdownOption[] = [
    { id: 0, label: "BEiT3", value: "beit3" as ModelName },
    { id: 1, label: "CLIP", value: "clip" as ModelName },
  ];

  return (
    <div className="bg-white border p-5 border-proto-line rounded-xl flex flex-col gap-y-5 font-baloo">
      {/* Khối "Dịch" (tiêu đề + nút X + ô chỉ-đọc) đã bỏ — xem handleTranslate. */}

      {showAdvanced && (
      <div className="w-full flex flex-row justify-between flex-wrap gap-y-3">
        <div className="flex flex-row gap-x-4 items-center font-baloo flex-wrap gap-y-2">
          <div className="items-center">
            <p className="font-bold">Show Top:</p>
            <Dropdown
              options={resultLimitOptions}
              value={resultLimit}
              onChange={(opt) => setResultLimit(opt.value)}
              dropDownWidth={100}
              dropDirection="up"
            />
          </div>

          {/* Top-M and Rerank are Alg.3/Alg.2 parameters. The OCR route calls
              no model, so both are meaningless there - hidden rather than
              left sitting on screen doing nothing. */}
          {!isOcr && (
            <>
              <div className="items-center">
                <p className="font-bold">Top-M mỗi model</p>
                <Dropdown
                  options={topMOptions}
                  value={String(topM)}
                  onChange={(opt) => setTopM(Number(opt.value))}
                  dropDownWidth={90}
                  dropDirection="up"
                />
              </div>

              <div className="flex flex-col items-start">
                <p className="font-bold">Rerank (Alg.2)</p>
                <label className="flex items-center gap-x-1 cursor-pointer p-2">
                  <input
                    type="checkbox"
                    checked={useRerank}
                    onChange={(e) => setUseRerank(e.target.checked)}
                  />
                  <span className="text-sm">bật</span>
                </label>
              </div>
            </>
          )}

          {/* Nhãn cũ ghi "bật — bắt cả lỗi dấu", và đó là lời quảng cáo sai.
              Đo trên 300 cụm chữ có thật trong kho: gõ CÓ dấu thì bật hay tắt
              ra y hệt ở 48% truy vấn, phần còn lại chỉ hơn 7%.
              Công dụng thật nằm chỗ khác — gõ KHÔNG dấu:
                  bật  →  300/300 tìm thấy
                  tắt  →   22/300
              Nên nhãn phải nói đúng điều đó. */}
          {isOcr && (
            <div className="flex flex-col items-start">
              <p className="font-bold">Bỏ dấu</p>
              <label
                className="flex items-center gap-x-1 cursor-pointer p-2"
                title={
                  "Bật: gõ 'quan an cho lon' vẫn ra 'Quán ăn Chợ Lớn'. " +
                  "Tắt: phải gõ đúng dấu mới khớp."
                }
              >
                <input
                  type="checkbox"
                  checked={ocrStripDiacritics}
                  onChange={(e) => setOcrStripDiacritics(e.target.checked)}
                />
                <span className="text-sm">
                  {ocrStripDiacritics
                    ? "bật — gõ không dấu vẫn ra"
                    : "tắt — phải gõ đúng dấu"}
                </span>
              </label>
            </div>
          )}

          {searchType === "single" && (
            <div className="items-center">
              <p className="font-bold">Model</p>
              <Dropdown
                options={modelOptions}
                value={singleModel}
                onChange={(opt) => setSingleModel(opt.value as ModelName)}
                dropDownWidth={100}
                dropDirection="up"
              />
            </div>
          )}
        </div>
        <div className="flex flex-row items-center gap-x-3">
          {/* Translation exists for BEiT3/CLIP, which only understand English.
              Text on screen is native Vietnamese - translating the query into
              English would stop it matching the corpus at all. */}
          {!isOcr && (
            <>
              <div>
                <p className="font-bold">Language</p>
                <Dropdown
                  options={transLangOptions}
                  value={translateLang}
                  onChange={(opt) =>
                    setTranslateLang(opt.value as TranslateLanguage)
                  }
                  dropDownWidth={100}
                  dropDirection="up"
                />
              </div>
              <div>
                <Button
                  className="h-full bg-gray-500 hover:bg-gray-700"
                  onClick={handleTranslate}
                >
                  Translate
                </Button>
              </div>
            </>
          )}

          <div className="items-center font-baloo">
            <p className="font-bold">Search Type</p>
            <Dropdown
              options={searchOptions}
              value={searchType}
              onChange={(opt) => setSearchType(opt.value as SearchType)}
              dropDownWidth={194}
              dropDirection="up"
            />
          </div>
        </div>
      </div>
      )}

      {/* Gợi ý cú pháp khi chọn Temporal/TRAKE — KHÔNG thêm field nào, chỉ
          text hướng dẫn. Ô nhập bên dưới vẫn là 1 input duy nhất như cũ. */}
      {(searchType === "temporal" || searchType === "trake") && (
        <p className="text-xs text-proto-muted -mt-2">
          {searchType === "temporal"
            ? "Nhập đúng 2 đoạn, cách nhau bằng dấu \".\" — vd: \"người bước lên sân khấu. khán giả vỗ tay\""
            : "Nhập từ 2 đoạn trở lên, theo thứ tự thời gian, cách nhau bằng dấu \".\" — vd: \"cắt nấm. cắt đậu hũ. bật bếp\""}
        </p>
      )}

      {/* Đoạn hướng dẫn dài cho tuyến OCR đã bỏ. Nó chiếm bốn dòng ngay trên ô
          nhập, mà cả nhóm đọc đúng một lần rồi thôi — từ lần thứ hai trở đi nó
          chỉ đẩy ô nhập xuống. Phần đáng nhớ nhất vẫn còn ở chỗ gõ vào được:
          placeholder của ô nhập nêu sẵn ví dụ có thật. */}

      {/* Toggle lives on the same line as the query row — closed state
          (default) is a single compact row: input + toggle + Search. */}
      <div className="w-full flex flex-row gap-x-3">
        <input
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          className="p-3 w-full rounded-[8px] bg-proto-soft border border-proto-line"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !disabled) doSearch();
          }}
          placeholder={
            searchType === "temporal"
              ? "vd: người bước lên sân khấu. khán giả vỗ tay"
              : searchType === "trake"
              ? "vd: cắt nấm. cắt đậu hũ. bật bếp"
              : isOcr
              ? "vd: Quán ăn Chợ Lớn · Dầu Diesel · Trường Quốc tế Á Châu"
              : "Enter your query"
          }
        />
        <button
          type="button"
          onClick={() => setShowAdvanced((prev) => !prev)}
          className="shrink-0 whitespace-nowrap rounded-[8px] border border-proto-line px-3 py-2 text-xs font-bold text-proto-muted hover:bg-proto-soft"
        >
          {showAdvanced ? "Ẩn tuỳ chọn" : "Tuỳ chọn"}
        </button>
        <Button onClick={doSearch} disabled={disabled}>
          Search
        </Button>
      </div>
    </div>
  );
}
