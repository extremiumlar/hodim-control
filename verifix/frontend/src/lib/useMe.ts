"use client";
import useSWR from "swr";
import { api } from "./api";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export function useMe() {
  const { data, error, isLoading, mutate } = useSWR("/accounts/users/me/", fetcher);
  return {
    me: data,
    isLoading,
    isError: error,
    refresh: mutate,
    isHR: data && (data.role === "admin" || data.role === "hr"),
  };
}
