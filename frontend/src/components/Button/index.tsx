import React, { forwardRef, type ButtonHTMLAttributes } from "react";
type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type ButtonSize = "xs" | "sm" | "md" | "lg" | "xl";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
  fullWidth?: boolean;
  children: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "lg",
      loading = false,
      leadingIcon,
      trailingIcon,
      fullWidth = false,
      disabled,
      className = "",
      children,
      ...props
    },
    ref
  ) => {
    const baseClasses =
      "inline-flex items-center justify-center font-medium rounded-[8px] transition-all duration-200 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed font-baloo font-bold";

    const variantClasses = {
      primary:
        "bg-proto-primary hover:bg-proto-primary-active hover:cursor-pointer text-white",
      secondary: "bg-proto-muted hover:bg-proto-ink text-white",
      outline:
        "border border-proto-line hover:border-proto-primary text-proto-body bg-white hover:bg-proto-soft",
      ghost: "hover:bg-proto-soft text-proto-body",
      danger: "bg-[#c64545] hover:bg-[#a33636] text-white",
    };

    const sizeClasses = {
      xs: "px-2 py-1 text-xs gap-1",
      sm: "px-3 py-1.5 text-sm gap-1.5",
      md: "px-4 py-2 text-sm gap-2",
      lg: "px-5 py-2.5 text-base gap-2",
      xl: "px-6 py-3 text-lg gap-2.5",
    };

    const widthClass = fullWidth ? "w-full" : "";

    const classes =
      `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${widthClass} ${className}`.trim();

    const LoadingSpinner = () => (
      <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    );

    return (
      <button
        ref={ref}
        className={classes}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? <LoadingSpinner /> : leadingIcon}
        {children}
        {!loading && trailingIcon}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;
