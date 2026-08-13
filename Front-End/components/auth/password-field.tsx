'use client'

import { useState, ReactNode, type ChangeEventHandler, type FocusEventHandler, type Ref } from "react";
import { Eye, EyeOff } from "lucide-react";

type PasswordFieldProps = {
  id: string;
  name: string;
  label?: string;
  rightElement?: ReactNode;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  error?: string;
  describedBy?: string;
  inputRef?: Ref<HTMLInputElement>;
  onBlur?: FocusEventHandler<HTMLInputElement>;
  onChange?: ChangeEventHandler<HTMLInputElement>;
};

export function PasswordField({
  id,
  name,
  label,
  rightElement,
  required = true,
  minLength = 8,
  autoComplete,
  error,
  describedBy,
  inputRef,
  onBlur,
  onChange,
}: PasswordFieldProps) {
  const [show, setShow] = useState(false);

  const errorId = error ? `${id}-error` : undefined;
  const combinedDescribedBy = [describedBy, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      {(label || rightElement) && (
        <div className="flex items-center justify-between">
          {label && <label htmlFor={id} className="text-[12px] font-semibold text-[#90B09E]">{label}</label>}
          {rightElement}
        </div>
      )}
      <div className="relative">
        <input
          id={id}
          name={name}
          type={show ? "text" : "password"}
          required={required}
          minLength={minLength}
          autoComplete={autoComplete}
          aria-invalid={Boolean(error)}
          aria-describedby={combinedDescribedBy}
          ref={inputRef}
          onBlur={onBlur}
          onChange={onChange}
          className={`h-[44px] w-full rounded-[10px] bg-[#0B0F17] pl-3 pr-11 py-2 text-[13px] text-[#EFFAF4] outline-none ring-1 transition-shadow focus:ring-2 focus:ring-[#B7FF3C] ${error ? 'ring-[#FB7185] focus:ring-[#FB7185]' : 'ring-[#1E293B]'}`}
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-0 top-0 flex h-[44px] w-[44px] items-center justify-center text-[#90B09E] hover:text-[#EFFAF4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] rounded-[10px]"
          aria-pressed={show}
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>
      {error && (
        <p id={errorId} className="text-[13px] leading-5 text-[#FF9C82]">{error}</p>
      )}
    </div>
  )
}
