"use client";

import { FormEvent, useState, useTransition } from "react";
import { normalizeTicker } from "@/lib/validation/ticker";

interface UseTickerSearchOptions {
  onSuccess?: (symbol: string) => void;
}

export function useTickerSearch(options?: UseTickerSearchOptions) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [isPending, startTransition] = useTransition();

  const loading = isSearching || isPending;

  const clearError = () => setError("");

  const handleInputChange = (raw: string) => {
    setQuery(raw);
    if (error) setError("");
  };

  const executeSearch = async (inputQuery?: string): Promise<string | null> => {
    if (loading) return null;

    const target = (inputQuery ?? query).trim();
    if (!target) {
      setError("Enter a ticker symbol or company name.");
      return null;
    }
    if (!/^[a-zA-Z0-9.\-\s]+$/.test(target)) {
      setError("Use letters, numbers, spaces, periods, or hyphens only.");
      return null;
    }

    setError("");
    setIsSearching(true);

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(target)}`);

      if (!res.ok) {
        let errorMessage = `No matching US ticker found for '${target}'`;
        try {
          const errorData = await res.json();
          if (errorData?.error) {
            errorMessage = errorData.error;
          } else if (errorData?.detail?.message) {
            errorMessage = errorData.detail.message;
          }
        } catch {
          // Keep default message
        }
        setIsSearching(false);
        setError(errorMessage);
        return null;
      }

      const data = await res.json();
      const symbol = typeof data?.symbol === "string" ? normalizeTicker(data.symbol) : null;

      if (!symbol) {
        setIsSearching(false);
        setError(`No matching US ticker found for '${target}'`);
        return null;
      }

      // Transition smoothly to the destination route without dropping the loading animation early
      startTransition(() => {
        options?.onSuccess?.(symbol);
        setIsSearching(false);
      });

      return symbol;
    } catch {
      setIsSearching(false);
      setError(`Failed to search for '${target}'. Please try again.`);
      return null;
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await executeSearch();
  };

  return {
    query,
    setQuery,
    handleInputChange,
    error,
    setError,
    clearError,
    loading,
    executeSearch,
    handleSubmit,
  };
}
