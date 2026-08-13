export type AuthFieldName = "email" | "password" | "passwordConfirmation";
export type AuthFieldErrors = Partial<Record<AuthFieldName, string>>;

export type AuthFieldValues = {
  email?: string;
  password?: string;
  passwordConfirmation?: string;
};

export function validateEmail(email: string | undefined): string | undefined {
  const normalized = (email ?? "").trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)
    ? undefined
    : "Enter a valid email address.";
}

export function validatePassword(password: string | undefined): string | undefined {
  return (password ?? "").length >= 8
    ? undefined
    : "Use at least 8 characters.";
}

export function validatePasswordConfirmation(
  password: string | undefined,
  confirmation: string | undefined,
): string | undefined {
  if (!(confirmation ?? "").length) return "Confirm your password.";
  return password === confirmation ? undefined : "Passwords do not match.";
}
