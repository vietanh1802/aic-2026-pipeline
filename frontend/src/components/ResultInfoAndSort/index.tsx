import Dropdown, { type DropdownOption } from "../DropDown";

export type SortType = "video_id" | "accuracy";

type ResultInfoAndSortProps = {
  numberOfResults: number;
  sortBy: SortType;
  totalTime: number;
  onSortChange: (sort: SortType) => void;
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
}: ResultInfoAndSortProps) {
  return (
    <div className="flex flex-row font-baloo gap-x-10 items-center px-4 py-2 bg-gray-100 rounded-md shadow-sm">
      <div className="text-sm font-medium text-gray-700">
        Searched Results{" "}
        <span className="font-bold">({numberOfResults} Frames Matched)</span> in{" "}
        {totalTime.toFixed(1)}s
      </div>
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
    </div>
  );
}
