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
  return (
    <Range
      label="Select your value"
      step={0.1}
      min={min}
      max={max}
      values={values}
      onChange={(values) => {
        setValues(values);
        if (activeIndex == 1) {
          setStartAt(values[1] * 1000);
        }
      }}
      renderTrack={({ props, children }) => (
        <div
          {...props}
          style={{
            ...props.style,
            height: "6px",
            width: "100%",
            backgroundColor: "#ccc",
          }}
        >
          {children}
        </div>
      )}
      renderThumb={({ props, index, isDragged }) => {
        const isActive = activeIndex === index; // check if THIS thumb is active
        return (
          <div
            {...props}
            onFocus={() => setActiveIndex(index)}
            onBlur={() => setActiveIndex(null)}
            onMouseDown={() => setActiveIndex(index)}
            onMouseUp={() => setActiveIndex(null)}
            onTouchStart={() => setActiveIndex(index)}
            onTouchEnd={() => setActiveIndex(null)}
            style={{
              ...props.style,
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
                {values[index].toFixed(2)}
              </div>
            )}
          </div>
        );
      }}
    />
  );
};
