"use client";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import {
  useQueryStore,
  // type QueryType,
  type SearchType,
  type TranslateLanguage,
} from "../../store/queryStore";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../ui/dialog";
import { useState } from "react";

interface QueryInputProps {
  doTextSearch: () => void;
  doFaissSearch: () => void;
  doCombinedSearch: () => void;
  doOCRsearch: () => void;
  doFilter: () => void;
  doTextSearchNoAgent: () => void;
}

export default function QueryInput({
  doTextSearch,
  doFaissSearch,
  doCombinedSearch,
  doOCRsearch,
  doFilter,
  doTextSearchNoAgent,
}: QueryInputProps) {
  // const queryType = useQueryStore((state) => state.queryType);
  // const setQueryType = useQueryStore((state) => state.setQueryType);
  const resultLimit = useQueryStore((state) => state.resultLimit);
  const setResultLimit = useQueryStore((state) => state.setResultLimit);
  const queryText = useQueryStore((state) => state.queryText);
  const setQueryText = useQueryStore((state) => state.setQueryText);
  const searchType = useQueryStore((state) => state.searchType);
  const setSearchType = useQueryStore((state) => state.setSearchType);

  const rank = useQueryStore((state) => state.rank);
  const setRank = useQueryStore((state) => state.setRank);

  const filter = useQueryStore((state) => state.filter);
  const setFilter = useQueryStore((state) => state.setFilter);

  const translateLang = useQueryStore((state) => state.translateLang);
  const setTranslateLang = useQueryStore((state) => state.setTranslateLang);
  const queryTranslated = useQueryStore((state) => state.queryTranslated);
  const setQueryTranslated = useQueryStore((state) => state.setQueryTranslated);

  const uniqueKeyword = useQueryStore((state) => state.uniqueKeyword);
  const setUniqueKeyword = useQueryStore((state) => state.setUniqueKeyword);
  const [isTranslated, setisTranslated] = useState<boolean>(false);

  // const queryTypeOptions: DropdownOption[] = [
  //   {
  //     id: 1,
  //     label: "Text",
  //     value: "text",
  //     leadingIcon: <img src="/text.svg" />,
  //   },
  //   {
  //     id: 2,
  //     label: "Frame",
  //     value: "frame",
  //     leadingIcon: <img src="/video.svg" />,
  //   },
  //   {
  //     id: 3,
  //     label: "Audio",
  //     value: "audio",
  //     leadingIcon: <img src="/audio.svg" />,
  //   },
  // ];

  const searchFunction = async () => {
    if (searchType == "text-search") {
      doTextSearch();
    } else if (searchType == "faiss-search") {
      doFaissSearch();
    } else if (searchType == "combined-search") {
      doCombinedSearch();
    } else if (searchType == "ocr-search") {
      doOCRsearch();
    } else {
      doTextSearchNoAgent();
    }
  };

  const handleTranslate = async () => {
    if (!queryText) return;

    // Determine target language based on your translateLang state
    const targetLang = translateLang === "vi-en" ? "en" : "vi";

    const res = await fetch(
      `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=${encodeURIComponent(
        queryText
      )}`
    );

    const data = await res.json();
    const translated = data[0];

    // Extract text from the nested array structure
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
    { id: 4, label: "1000", value: "1000" },
    { id: 5, label: "5000", value: "5000" },
    { id: 6, label: "10000", value: "10000" },
  ];
  const rankOptions: DropdownOption[] = [
    { id: 0, label: "1", value: "1" },
    { id: 1, label: "2", value: "2" },
    { id: 2, label: "3", value: "3" },
    { id: 3, label: "4", value: "4" },
    { id: 4, label: "5", value: "5" },
    { id: 5, label: "6", value: "6" },
    { id: 6, label: "7", value: "7" },
    { id: 7, label: "10", value: "10" },
    { id: 8, label: "15", value: "15" },
    { id: 9, label: "20", value: "20" },
    { id: 10, label: "25", value: "25" },
    { id: 11, label: "30", value: "30" },
  ];
  const transLangOptions: DropdownOption[] = [
    { id: 0, label: "vi-en", value: "vi-en" as TranslateLanguage },
    { id: 1, label: "en-vi", value: "en-vi" as TranslateLanguage },
  ];

  const searchOptions: DropdownOption[] = [
    { id: 0, label: "Text Search", value: "text-search" as SearchType },
    { id: 1, label: "No Agent Search", value: "no-agent" as SearchType },
    { id: 2, label: "Faiss Search", value: "faiss-search" as SearchType },
    { id: 3, label: "Combined Search", value: "combined-search" as SearchType },
    { id: 4, label: "OCR Search", value: "ocr-search" as SearchType },
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

      <div className="w-full flex flex-row justify-between">
        <div className="flex flex-row gap-x-4 items-center font-baloo">
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
            <p className="font-bold">Rank</p>
            <Dropdown
              options={rankOptions}
              value={String(rank)}
              onChange={(opt) => setRank(opt.value)}
              dropDownWidth={80}
              dropDirection="up"
            />
          </div>

          <div className="">
            <p className="font-bold">Unique Keywords</p>
            <input
              type="text"
              value={uniqueKeyword} // bind state value
              onChange={(e) => setUniqueKeyword(e.target.value)} // update state
              className="border p-2 rounded"
            />
          </div>
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

      <div className="w-full flex flex-row gap-x-3">
        <input
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          className="p-3 w-full rounded-[4px] bg-[#F8F8F8] border-2 border-[#E3E3E3]"
          placeholder="Enter your query"
        />
        <Dialog>
          <DialogTrigger asChild>
            <Button
              leadingIcon={<img src="/filter.svg" />}
              className="bg-red-400 hover:bg-red-600 p-2 transition-all duration-300"
            >
              Filter
            </Button>
          </DialogTrigger>
          <DialogContent className="font-baloo text-2xl bg-white">
            <DialogHeader>
              <DialogTitle className="text-2xl">Filter Search</DialogTitle>
              <DialogDescription>
                Refine your search by specifying objects, actions, and colors.
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-4 mt-4 text-xl">
              {/* Objects */}
              <div>
                <label className="block font-medium text-gray-700">
                  Objects
                </label>
                <input
                  type="text"
                  value={filter.object}
                  onChange={(e) => setFilter({ object: e.target.value })}
                  placeholder="e.g., car, tree, person"
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2"
                />
              </div>

              {/* Actions */}
              <div>
                <label className="block font-medium text-gray-700">
                  Actions
                </label>
                <input
                  type="text"
                  value={filter.action}
                  onChange={(e) => setFilter({ action: e.target.value })}
                  placeholder="e.g., running, eating"
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2"
                />
              </div>

              {/* Colors */}
              <div>
                <label className="block font-medium text-gray-700">Color</label>
                <input
                  type="text"
                  value={filter.color}
                  onChange={(e) => setFilter({ color: e.target.value })}
                  placeholder="e.g., red, blue"
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2"
                />
              </div>

              {/* OCR */}
              <div>
                <label className="block font-medium text-gray-700">OCR</label>
                <input
                  type="text"
                  value={filter.ocr}
                  onChange={(e) => setFilter({ ocr: e.target.value })}
                  placeholder="e.g., "
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <Button
                onClick={async () => {
                  doFilter();
                }}
                className="bg-blue-500 hover:bg-blue-600"
              >
                Filters Search
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <Button onClick={searchFunction}>Search</Button>
      </div>
    </div>
  );
}
