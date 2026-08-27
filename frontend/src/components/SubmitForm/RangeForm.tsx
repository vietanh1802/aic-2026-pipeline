import * as React from "react";
import { Range } from "react-range";

interface RangeFormData {
  min: number;
  max: number;
  values: number[];
  setValues: React.Dispatch<React.SetStateAction<number[]>>;
  setStartAt: (val: number) => void;
}

export const SuperSimple: React.FC<RangeFormData> = ({
  min,
  max,
  values,
  setValues,
  setStartAt,
}) => {
  // const [values, setValues] = React.useState([0, 100]);
  const [activeIndex, setActiveIndex] = React.useState<number | null>(null);

  // The slider first mounts while the video's `duration` (→ max) is still 0,
  // so min === max === 0 while `values` already holds real seconds from the
  // popup. react-range then warns/throws because `values` conflicts with the
  // current step/min/max — render a plain inert track until there is an
  // actual range to drag over, and clamp values into range afterwards so a
  // stale value beyond the (now real) max never conflicts with it either.
  if (max <= min) {
    return (
      <div
        style={{
          height: "6px",
          width: "100%",
          backgroundColor: "#ccc",
        }}
      />
    );
  }

  const safeValues = values.map((value) => Math.min(Math.max(value, min), max));

  return (
    <Range
      label="Select your value"
      step={0.1}
      min={min}
      max={max}
      values={safeValues}
      onChange={(values) => {
        setValues(values);
        if (activeIndex == 1) {
          setStartAt(values[1] * 1000);
        }
      }}
      renderTrack={({ props, children }) => {
        // ITrackProps doesn't declare `key` (unlike IThumbProps), but the
        // cast keeps this in the same destructure-and-forward shape as
        // renderThumb below, so neither ever spreads a `key` into JSX.
        const { key, ...rest } = props as typeof props & { key?: React.Key };
        return (
          <div
            key={key}
            {...rest}
            style={{
              ...rest.style,
              height: "6px",
              width: "100%",
              backgroundColor: "#ccc",
            }}
          >
            {children}
          </div>
        );
      }}
      renderThumb={({ props, index, isDragged }) => {
        const { key, ...rest } = props;
        const isActive = activeIndex === index; // check if THIS thumb is active
        return (
          <div
            key={key}
            {...rest}
            onFocus={() => setActiveIndex(index)}
            onBlur={() => setActiveIndex(null)}
            onMouseDown={() => setActiveIndex(index)}
            onMouseUp={() => setActiveIndex(null)}
            onTouchStart={() => setActiveIndex(index)}
            onTouchEnd={() => setActiveIndex(null)}
            style={{
              ...rest.style,
              height: "15px",
              width: "7px",
              backgroundColor: isActive && index === 1 ? "#ff0000" : "#ccc", // only index=1 AND active
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              fontSize: "10px",
              color: "#ff0000",
            }}
          >
            {activeIndex === index && isDragged && (
              <div
                style={{
                  position: "absolute",
                  top: "-30px",
                  background: "#888132",
                  color: "#fff",
                  padding: "2px 6px",
                  borderRadius: "4px",
                  fontSize: "12px",
                  whiteSpace: "nowrap",
                }}
              >
                {safeValues[index].toFixed(2)}
              </div>
            )}
          </div>
        );
      }}
    />
  );
};
