'use client'

import type { ChangeEvent, FocusEvent, FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";

import type { AuthFieldErrors, AuthFieldName, AuthFieldValues } from "@/lib/auth/validation";

type Validator = (values: AuthFieldValues) => AuthFieldErrors;

function readValues(form: HTMLFormElement): AuthFieldValues {
  const data = new FormData(form);
  return {
    email: String(data.get("email") ?? ""),
    password: String(data.get("password") ?? ""),
    passwordConfirmation: String(data.get("passwordConfirmation") ?? ""),
  };
}

export function useAuthFormValidation(
  serverErrors: AuthFieldErrors | undefined,
  validate: Validator,
) {
  const [touched, setTouched] = useState<Partial<Record<AuthFieldName, boolean>>>({});
  const serverVersion = JSON.stringify(serverErrors ?? {});
  const [edits, setEdits] = useState<{
    version: string;
    fields: Partial<Record<AuthFieldName, boolean>>;
  }>({ version: serverVersion, fields: {} });
  const [clientErrors, setClientErrors] = useState<AuthFieldErrors>({});
  const editedSinceServer = edits.version === serverVersion ? edits.fields : {};

  useEffect(() => {
    const first = (["email", "password", "passwordConfirmation"] as const).find((name) => serverErrors?.[name]);
    if (first) requestAnimationFrame(() => document.querySelector<HTMLInputElement>(`[name="${first}"]`)?.focus());
  }, [serverErrors]);

  const validateTouched = useCallback((form: HTMLFormElement, nextTouched = touched) => {
    const nextErrors = validate(readValues(form));
    const visibleErrors: AuthFieldErrors = {};
    for (const name of ["email", "password", "passwordConfirmation"] as const) {
      if (nextTouched[name] && nextErrors[name]) visibleErrors[name] = nextErrors[name];
    }
    setClientErrors(visibleErrors);
    return nextErrors;
  }, [touched, validate]);

  const fieldProps = (name: AuthFieldName) => ({
    onBlur: (event: FocusEvent<HTMLInputElement>) => {
      const nextTouched = { ...touched, [name]: true };
      setTouched(nextTouched);
      if (event.currentTarget.form) validateTouched(event.currentTarget.form, nextTouched);
    },
    onChange: (event: ChangeEvent<HTMLInputElement>) => {
      setEdits((current) => ({
        version: serverVersion,
        fields: { ...(current.version === serverVersion ? current.fields : {}), [name]: true },
      }));
      if (event.currentTarget.form && touched[name]) validateTouched(event.currentTarget.form);
    },
  });

  const errorFor = (name: AuthFieldName): string | undefined =>
    clientErrors[name] ?? (editedSinceServer[name] ? undefined : serverErrors?.[name]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    const values = readValues(event.currentTarget);
    const nextErrors = validate(values);
    if (!Object.keys(nextErrors).length) return;

    event.preventDefault();
    const nextTouched: Partial<Record<AuthFieldName, boolean>> = {};
    for (const name of Object.keys(values) as AuthFieldName[]) {
      if (event.currentTarget.elements.namedItem(name)) nextTouched[name] = true;
    }
    setTouched(nextTouched);
    setClientErrors(nextErrors);
    const first = (["email", "password", "passwordConfirmation"] as const).find((name) => nextErrors[name]);
    const form = event.currentTarget;
    if (first) requestAnimationFrame(() => (form.elements.namedItem(first) as HTMLInputElement | null)?.focus());
  };

  return { errorFor, fieldProps, onSubmit };
}
