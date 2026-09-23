"use client";
// frontend/src/components/QueryInput/index.tsx
import { useState } from "react";
import { Filter, X } from "lucide-react";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import TextIndexStatus from "../TextIndexStatus";
import {
  useQueryStore,
  type SearchType,
  type TextFilterMode,
  type TranslateLanguage,
} from "../../store/queryStore";
import type { ModelName } from "../../types/api";
import { expandQuery, type ExpansionResult } from "../../api/expansion";

// Longest text filter the backend accepts: keep in sync with TEXT_FILTER_MAX_CHARS
// in backend/app/text_signal.py. A longer value is rejected with HTTP 422 for the
// WHOLE search request, so the input cuts a long paste instead of failing the search.
// (maxLength counts UTF-16 units and the backend counts characters, so an astral
// character such as an emoji counts double here: the limit is never exceeded.)
const TEXT_FILTER_MAX_CHARS = 200;

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

  // ── Text-signal filter (ASR/OCR annotation, /ensemble-search only) ────────
  const textFilter = useQueryStore((state) => state.textFilter);
  const setTextFilter = useQueryStore((state) => state.setTextFilter);
  const textFilterMode = useQueryStore((state) => state.textFilterMode);
  const setTextFilterMode = useQueryStore((state) => state.setTextFilterMode);
  // Hidden by default; starts open if a filter is already set (e.g. this
  // component remounted). Stays open until the user clicks the toggle again
  // — it does not auto-collapse just because the field is empty.
  const [filterRowOpen, setFilterRowOpen] = useState(textFilter.trim() !== "");
  // Cụm tuỳ chọn (Show Top, Top-M, Rerank, Language, Translate, Search Type)
  // trước đây gấp sau nút "Tuỳ chọn", đóng sẵn. Bỏ nút, để hiện thường trực:
  // Search Type nằm trong cụm đó, mà chuyển sang TRAKE hay OCR là việc làm
  // nhiều lần một vòng — "đóng sẵn" nghĩa là mỗi lần đổi tuyến tìm mất thêm
  // một cú bấm mở ra và một cú bấm đóng lại.
  //
  // Hồi cụm này còn là thanh ngang ở đáy màn hình thì mở ra là nó che mất
  // hàng kết quả cuối, nên đóng sẵn có lý. Từ 4.2.0 nó là cột trái, không đè
  // lên gì nữa, nên lý do đó hết hiệu lực.

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

  // Expand: giống Translate ở chỗ ghi thẳng vào ô nhập, khác ở chỗ đi qua
  // backend (Gemini/Ollama) thay vì gtx trong trình duyệt. Kết quả kèm
  // check_units — hiện một dòng mờ dưới cụm nút, biến mất ngay khi người dùng
  // sửa câu, theo cùng triết lý "không để UI cố định chỉ để đọc một lần".
  const [expanding, setExpanding] = useState(false);
  const [expandError, setExpandError] = useState<string | null>(null);
  const [expansion, setExpansion] = useState<ExpansionResult | null>(null);

  const handleExpand = async () => {
    if (!queryText || expanding) return;
    setExpanding(true);
    setExpandError(null);
    try {
      const result = await expandQuery(queryText, "KIS");
      setQueryText(result.eng_query);
      setExpansion(result);
    } catch (err) {
      setExpandError(
        err instanceof Error ? err.message : "Không mở rộng được câu truy vấn"
      );
      console.error("Không mở rộng được:", err);
    } finally {
      setExpanding(false);
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

  const textFilterModeOptions: DropdownOption[] = [
    {
      id: 0,
      label: "Substring",
      value: "substring" as TextFilterMode,
      description: "exact text match, diacritics ignored",
    },
    {
      id: 1,
      label: "Regex",
      value: "regex" as TextFilterMode,
      description: "pattern match, e.g. (ngò|ngo) or đường\\s+\\w+",
    },
    {
      id: 2,
      label: "BM25",
      value: "bm25" as TextFilterMode,
      description: "lexical relevance score across transcript",
    },
  ];

  const textFilterPlaceholder = {
    substring: "e.g. ngò, quán trọ, 2018",
    regex: "e.g. (ngò|ngo), đường\\s+\\w+",
    bm25: "e.g. khu vườn trái cây miền Tây",
  }[textFilterMode];

  return (
    // Không còn `border rounded-xl`: khung bao ngoài giờ là cột trái cố định
    // trong App.tsx, nó đã có viền phải và nền trắng của riêng nó.
    <div className="p-4 flex flex-col gap-y-4 font-baloo">
      {/* Khối "Dịch" (tiêu đề + nút X + ô chỉ-đọc) đã bỏ — xem handleTranslate. */}

      {/* Xếp DỌC, không phải `flex-row justify-between` như hồi còn là thanh
          ngang rộng 900px ở đáy màn hình. Trong cột 360px, `justify-between`
          đẩy hai cụm ra hai mép rồi bỏ lại một khoảng trống ở giữa, còn từng
          ô thì bị bóp cho tới lúc rớt dòng lung tung. */}
      <div className="w-full flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-x-3 gap-y-2 font-baloo">
          <div className="items-center">
            <p className="font-bold">Show Top:</p>
            <Dropdown
              options={resultLimitOptions}
              value={resultLimit}
              onChange={(opt) => setResultLimit(opt.value)}
              dropDownWidth={100}
              dropDirection="down"
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
                  dropDirection="down"
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
                dropDirection="down"
              />
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-2">
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
                  dropDirection="down"
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
              <div>
                <Button
                  className="h-full bg-gray-500 hover:bg-gray-700"
                  onClick={handleExpand}
                  disabled={expanding || disabled}
                  title="Dịch + mở rộng qua backend (Gemini, fallback Ollama local)"
                >
                  {expanding ? "Đang mở rộng..." : "Expand"}
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
              dropDirection="down"
            />
          </div>
        </div>
      </div>

      {/* Text-signal filter — additive ASR/OCR annotation, /ensemble-search
          only (backend never applies it to single/temporal/trake/ocr), so the
          toggle only shows for that search type to avoid a control that
          silently does nothing. Hidden by default: most searches don't need
          it, and showing it always would push the textarea down for everyone. */}
      {searchType === "ensemble" && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              className="flex items-center gap-1 text-[12.5px] font-semibold text-proto-primary-active w-fit"
              onClick={() => setFilterRowOpen((open) => !open)}
            >
              <Filter size={13} />
              Text filter
            </button>
            <TextIndexStatus />
          </div>

          {filterRowOpen && (
            <div
              className={`flex items-center gap-2 rounded-[8px] p-1.5 transition-colors ${
                textFilter.trim() !== "" ? "bg-proto-primary/10" : ""
              }`}
            >
              <Dropdown
                options={textFilterModeOptions}
                value={textFilterMode}
                onChange={(opt) => setTextFilterMode(opt.value as TextFilterMode)}
                dropDownWidth={130}
                dropDirection="down"
                size="sm"
              />
              <input
                type="text"
                value={textFilter}
                maxLength={TEXT_FILTER_MAX_CHARS}
                onChange={(e) => setTextFilter(e.target.value)}
                placeholder={textFilterPlaceholder}
                className="flex-1 min-w-0 rounded-[6px] border border-proto-line bg-white px-2 py-1.5 text-[12.5px] text-proto-ink"
              />
              {textFilter !== "" && (
                <button
                  type="button"
                  onClick={() => setTextFilter("")}
                  title="Xoá bộ lọc"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] border border-proto-line bg-white text-proto-muted"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Hai dòng gợi ý cú pháp cho Temporal/TRAKE đã bỏ ("Nhập đúng 2 đoạn,
          cách nhau bằng dấu ." và bản N đoạn của TRAKE). Cùng lý do với đoạn
          hướng dẫn OCR bên dưới: đọc một lần là thuộc, từ lần thứ hai trở đi
          nó chỉ đẩy ô nhập xuống thấp.

          Luật tách đoạn vẫn còn nói ở chỗ gõ vào được: `placeholder` của ô
          nhập đổi theo searchType và nêu thẳng ví dụ có dấu chấm phân đoạn
          ("vd: cắt nấm. cắt đậu hũ. bật bếp"). Tách đoạn thật sự làm ở
          backend — preprocess.py:_split_query_text. */}

      {/* Đoạn hướng dẫn dài cho tuyến OCR đã bỏ. Nó chiếm bốn dòng ngay trên ô
          nhập, mà cả nhóm đọc đúng một lần rồi thôi — từ lần thứ hai trở đi nó
          chỉ đẩy ô nhập xuống. Phần đáng nhớ nhất vẫn còn ở chỗ gõ vào được:
          placeholder của ô nhập nêu sẵn ví dụ có thật. */}

      {/* Ô chữ NHIỀU DÒNG, không phải `<input>` một dòng.
          Cột nhập rộng 360px, mà một truy vấn TRAKE là bốn câu tả nối nhau —
          trên một dòng thì thấy được chừng năm chữ đầu, phần còn lại phải rê
          con trỏ sang mới đọc được. Đúng lúc cần đọc lại nó nhất: trước khi
          bấm Search. `resize-y` để ai cần thì kéo cao thêm.

          Enter vẫn là Search như cũ, nên `preventDefault` — nếu không nó chèn
          một dòng trống rồi mới tìm. Shift+Enter mới xuống dòng. */}
      {/* Kết quả Expand: chỉ hiện ngay sau khi bấm và biến mất khi câu trong
          ô nhập được sửa. Hai dòng trở xuống là đã chiếm chỗ vĩnh viễn —
          đúng thứ mà hồi 4.2.0 đã dọn cho khối Dịch. */}
      {expandError && (
        <p className="text-[12.5px] text-red-600 leading-snug">{expandError}</p>
      )}
      {!expandError && expansion && (
        <p
          className="text-[12.5px] text-proto-muted leading-snug"
          title={expansion.check_units.join(", ")}
        >
          {`Check units (${expansion.provider}, ${
            expansion.elapsed_ms
          }ms): ${expansion.check_units.join(", ")}`}
        </p>
      )}

      <div className="w-full flex flex-col gap-2">
        <textarea
          value={queryText}
          onChange={(e) => {
            setQueryText(e.target.value);
            setExpansion(null);
          }}
          rows={6}
          // Dòng chú thích "Enter để tìm · Shift+Enter xuống dòng" đã bỏ khỏi
          // màn hình — nó chiếm một dòng vĩnh viễn cho một câu đọc một lần.
          // Chuyển vào tooltip: vẫn tra được, không nằm choán chỗ.
          title="Enter để tìm · Shift+Enter xuống dòng"
          className="p-3 w-full rounded-[8px] bg-proto-soft border border-proto-line resize-y min-h-[120px] leading-snug"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!disabled) doSearch();
            }
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
        {/* Nút "Tuỳ chọn / Ẩn tuỳ chọn" đứng cạnh Search ở đây đã bỏ — cụm
            tuỳ chọn giờ hiện thường trực, xem chú thích chỗ khai báo. Search
            còn một mình nên bỏ luôn thẻ bọc `flex` và `flex-1`: một nút duy
            nhất không cần chia phần ngang với ai. */}
        <Button onClick={doSearch} disabled={disabled} className="w-full">
          Search
        </Button>
      </div>
    </div>
  );
}
