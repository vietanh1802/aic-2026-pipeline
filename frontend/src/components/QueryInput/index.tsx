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

  const translateLang = useQueryStore((state) => state.translateLang);
  const setTranslateLang = useQueryStore((state) => state.setTranslateLang);
  const queryTranslated = useQueryStore((state) => state.queryTranslated);
  const setQueryTranslated = useQueryStore(
    (state) => state.setQueryTranslated
  );
  const [isTranslated, setisTranslated] = useState<boolean>(false);

  const handleTranslate = async () => {
    if (!queryText) return;
    const targetLang = translateLang === "vi-en" ? "en" : "vi";
    const res = await fetch(
      `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=${encodeURIComponent(
        queryText
      )}`
    );
    const data = await res.json();
    const translated = data[0];
    const texts = translated.map((item: string[]) => item[0]);
    const queryTranslated = texts.join("");
    setQueryTranslated(queryTranslated);
    setisTranslated(true);
  };

  const resultLimitOptions: DropdownOption[] = [
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
  ];

  const modelOptions: DropdownOption[] = [
    { id: 0, label: "BEiT3", value: "beit3" as ModelName },
    { id: 1, label: "CLIP", value: "clip" as ModelName },
  ];

  return (
    <div className="bg-white border p-5 border-[#E3E3E3] rounded-xl flex flex-col gap-y-5 font-baloo">
      <div
        className={`w-full flex flex-row justify-between ${
          isTranslated ? "" : "hidden"
        }`}
      >
        <h1 className="font-bold">Dịch</h1>
        <div
          className="text-red-500 hover:bg-red-300 hover:rounded-full px-2 font-bold cursor-pointer text-2xl"
          onClick={() => setisTranslated(false)}
        >
          X
        </div>
      </div>
      <div className={`w-full flex ${isTranslated ? "" : "hidden"}`}>
        <input
          value={queryTranslated}
          className="p-3 w-full rounded-[4px] bg-[#F8F8F8] border-2 border-[#E3E3E3]"
          readOnly
        />
      </div>

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
            <p className="font-bold">Button</p>
            <Button
              className="h-full bg-gray-500 hover:bg-gray-700"
              onClick={handleTranslate}
            >
              Translate
            </Button>
          </div>

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

      {/* Gợi ý cú pháp khi chọn Temporal/TRAKE — KHÔNG thêm field nào, chỉ
          text hướng dẫn. Ô nhập bên dưới vẫn là 1 input duy nhất như cũ. */}
      {(searchType === "temporal" || searchType === "trake") && (
        <p className="text-xs text-gray-500 -mt-2">
          {searchType === "temporal"
            ? "Nhập đúng 2 đoạn, cách nhau bằng dấu \".\" — vd: \"người bước lên sân khấu. khán giả vỗ tay\""
            : "Nhập từ 2 đoạn trở lên, theo thứ tự thời gian, cách nhau bằng dấu \".\" — vd: \"cắt nấm. cắt đậu hũ. bật bếp\""}
        </p>
      )}

      <div className="w-full flex flex-row gap-x-3">
        <input
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          className="p-3 w-full rounded-[4px] bg-[#F8F8F8] border-2 border-[#E3E3E3]"
          placeholder={
            searchType === "temporal"
              ? "vd: người bước lên sân khấu. khán giả vỗ tay"
              : searchType === "trake"
              ? "vd: cắt nấm. cắt đậu hũ. bật bếp"
              : "Enter your query"
          }
        />
        <Button onClick={doSearch} disabled={disabled}>
          Search
        </Button>
      </div>
    </div>
  );
}
