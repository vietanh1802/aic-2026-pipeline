"use client";
import React, { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

export interface DropdownOption {
  id: number;
  label: string;
  value: string;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
  disabled?: boolean;
}

interface DropdownProps {
  options: DropdownOption[];
  value?: string;
  placeholder?: string;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
  onChange?: (option: DropdownOption) => void;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
  dropDownWidth?: number;
  dropDirection?: "up" | "down";
}

const Dropdown: React.FC<DropdownProps> = ({
  options,
  value,
  placeholder = "Select an option",
  leadingIcon,
  trailingIcon,
  onChange,
  disabled = false,
  className = "",
  size = "md",
  dropDownWidth = 250,
  dropDirection = "down",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedOption, setSelectedOption] = useState<DropdownOption | null>(
    value ? options.find((opt) => opt.value === value) || null : null
  );
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const sizeConfig = {
    sm: {
      trigger: "px-3 py-2 text-sm",
      option: "px-3 py-2 text-sm",
      icon: "w-4 h-4",
    },
    md: {
      trigger: "px-4 py-3 text-base",
      option: "px-4 py-3 text-base",
      icon: "w-5 h-5",
    },
    lg: {
      trigger: "px-5 py-4 text-lg",
      option: "px-5 py-4 text-lg",
      icon: "w-6 h-6",
    },
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setFocusedIndex(-1);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isOpen) return;

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          setFocusedIndex((prev) => {
            const enabledOptions = options.filter((opt) => !opt.disabled);
            const currentEnabledIndex = enabledOptions.findIndex(
              (opt) => opt.id === options[prev]?.id
            );
            const nextIndex = currentEnabledIndex + 1;
            if (nextIndex < enabledOptions.length) {
              return options.findIndex(
                (opt) => opt.id === enabledOptions[nextIndex].id
              );
            }
            return options.findIndex((opt) => opt.id === enabledOptions[0].id);
          });
          break;
        case "ArrowUp":
          event.preventDefault();
          setFocusedIndex((prev) => {
            const enabledOptions = options.filter((opt) => !opt.disabled);
            const currentEnabledIndex = enabledOptions.findIndex(
              (opt) => opt.id === options[prev]?.id
            );
            const prevIndex = currentEnabledIndex - 1;
            if (prevIndex >= 0) {
              return options.findIndex(
                (opt) => opt.id === enabledOptions[prevIndex].id
              );
            }
            return options.findIndex(
              (opt) => opt.id === enabledOptions[enabledOptions.length - 1].id
            );
          });
          break;
        case "Enter":
        case " ":
          event.preventDefault();
          if (focusedIndex >= 0 && !options[focusedIndex]?.disabled) {
            handleOptionSelect(options[focusedIndex]);
          }
          break;
        case "Escape":
          setIsOpen(false);
          setFocusedIndex(-1);
          triggerRef.current?.focus();
          break;
      }
    };

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, focusedIndex, options]);

  const handleOptionSelect = (option: DropdownOption) => {
    if (option.disabled) return;

    setSelectedOption(option);
    setIsOpen(false);
    setFocusedIndex(-1);
    onChange?.(option);
    triggerRef.current?.focus();
  };

  const toggleDropdown = () => {
    if (disabled) return;
    setIsOpen(!isOpen);
    if (!isOpen) setFocusedIndex(-1);
  };

  return (
    <div
      className={`relative ${className}`}
      ref={dropdownRef}
      style={{ width: dropDownWidth }}
    >
      <button
        ref={triggerRef}
        type="button"
        onClick={toggleDropdown}
        disabled={disabled}
        className={`
          w-full flex items-center justify-between
          ${sizeConfig[size].trigger}
          border border-gray-300 rounded-lg
          bg-white text-gray-900
          hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
          disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
          transition-all duration-200
        `}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-labelledby="dropdown-label"
      >
        <div className="flex items-center gap-1 flex-1 min-w-0">
          {(selectedOption?.leadingIcon || leadingIcon) && (
            <span
              className={`flex-shrink-0 text-gray-400 ${sizeConfig[size].icon} w-6`}
            >
              {selectedOption?.leadingIcon || leadingIcon}
            </span>
          )}
          <span className="truncate text-left">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {trailingIcon && (
            <span className={`text-gray-400 ${sizeConfig[size].icon}`}>
              {trailingIcon}
            </span>
          )}
          <ChevronDown
            className={`
              text-gray-400 transition-transform duration-200
              ${sizeConfig[size].icon}
              ${isOpen ? "transform rotate-180" : ""}
            `}
          />
        </div>
      </button>

      {isOpen && (
        <div
          className={`absolute z-50 ${
            dropDirection === "up" ? "bottom-full mb-1" : "top-full mt-1"
          } bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto`}
          style={{ width: dropDownWidth }}
        >
          <ul role="listbox" className="py-1">
            {options.map((option, index) => (
              <li
                key={option.id}
                role="option"
                aria-selected={selectedOption?.id === option.id}
                className={`
                  ${sizeConfig[size].option}
                  flex items-center gap-3 cursor-pointer
                  transition-colors duration-150
                  ${
                    option.disabled
                      ? "text-gray-400 cursor-not-allowed bg-gray-50"
                      : focusedIndex === index
                      ? "bg-blue-50 text-blue-900"
                      : selectedOption?.id === option.id
                      ? "bg-blue-100 text-blue-900"
                      : "text-gray-900 hover:bg-gray-50"
                  }
                `}
                onClick={() => handleOptionSelect(option)}
                onMouseEnter={() => !option.disabled && setFocusedIndex(index)}
              >
                {option.leadingIcon && (
                  <span
                    className={`flex-shrink-0 ${sizeConfig[size].icon} w-6`}
                  >
                    {option.leadingIcon}
                  </span>
                )}
                <span className="flex-1 truncate">{option.label}</span>
                {option.trailingIcon && (
                  <span
                    className={`flex-shrink-0 ${sizeConfig[size].icon} w-6`}
                  >
                    {option.trailingIcon}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default Dropdown;
