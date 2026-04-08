import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = "", id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`
            w-full rounded-lg border border-zinc-200 dark:border-zinc-600/50
            bg-white dark:bg-[#1e1e20]
            text-zinc-900 dark:text-zinc-100
            placeholder:text-zinc-400 dark:placeholder:text-zinc-600
            px-3 py-2 text-[13px]
            transition-colors duration-150
            focus:outline-none focus:border-[var(--color-accent)] dark:focus:border-[var(--color-accent-dark)]
            ${error ? "border-rose-300 dark:border-rose-700" : ""}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = "", id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          className={`
            w-full rounded-lg border border-zinc-200 dark:border-zinc-600/50
            bg-white dark:bg-[#1e1e20]
            text-zinc-900 dark:text-zinc-100
            placeholder:text-zinc-400 dark:placeholder:text-zinc-600
            px-3 py-2.5 text-[13px] leading-relaxed
            transition-colors duration-150
            focus:outline-none focus:border-[var(--color-accent)] dark:focus:border-[var(--color-accent-dark)]
            resize-y min-h-[80px]
            ${error ? "border-rose-300 dark:border-rose-700" : ""}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
        )}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
