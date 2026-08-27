import Dropdown, { type DropdownOption } from "../DropDown";

export type SortType = "video_id" | "accuracy";

type ResultInfoAndSortProps = {
  numberOfResults: number;
  sortBy: SortType;
  totalTime: number;
  onSortChange: (sort: SortType) => void;
  // Auto-discovery đếm VIDEO ứng viên, không phải frame, và thứ tự do backend
  // quyết (discovery_score) nên không có gì để người dùng sắp lại.
  unit?: "frames" | "videos";
  queryParts?: number;
  /** Set while a focus filter is on, so the count cannot pass for a bad search. */
  filtered?: { shown: number; total: number };
};

const sortOptions: DropdownOption[] = [
  { id: 1, label: "Video ID", value: "video_id" },
  { id: 2, label: "Accuracy", value: "accuracy" },
];

export default function ResultInfoAndSort({
  numberOfResults,
  sortBy,
  totalTime,
  onSortChange,
  unit = "frames",
  queryParts,
  filtered,
}: ResultInfoAndSortProps) {
  const isVideos = unit === "videos";
  return (
    <div className="flex flex-row font-baloo gap-x-10 items-center px-4 py-2 bg-proto-card border border-proto-line rounded-md shadow-sm">
      <div className="text-sm font-medium text-proto-body">
        {isVideos ? (
          <>
            Tìm thấy{" "}
            <span className="font-bold">{numberOfResults} video ứng viên</span>{" "}
            trong {totalTime.toFixed(1)}s
          </>
        ) : (
          <>
            {filtered ? (
              <>
                <span className="font-bold">
                  {filtered.shown}/{filtered.total} kết quả
                </span>{" "}
                <span className="text-proto-primary-active font-bold">
                  (đang lọc)
                </span>{" "}
                in {totalTime.toFixed(1)}s
              </>
            ) : (
              <>
                Searched Results{" "}
                <span className="font-bold">
                  ({numberOfResults} Frames Matched)
                </span>{" "}
                in {totalTime.toFixed(1)}s
              </>
            )}
          </>
        )}
      </div>
      {isVideos ? (
        <div className="text-sm text-proto-muted">
          query tách <span className="font-bold">{queryParts ?? 0} đoạn</span> ·
          sắp theo số đoạn khớp
        </div>
      ) : (
        <div className="flex flex-row items-center gap-x-2">
          <p className="">Sorted By:</p>
          <Dropdown
            options={sortOptions}
            value={sortBy}
            onChange={(opt) => onSortChange(opt.value as SortType)}
            dropDownWidth={100}
            size="sm"
          />
        </div>
      )}
    </div>
  );
}
