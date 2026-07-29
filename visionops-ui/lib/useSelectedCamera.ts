"use client";

import { useCallback, useEffect, useState } from "react";
import type { Camera } from "@/lib/api";
import { visionopsApi } from "@/lib/api";

const STORAGE_KEY = "visionops.selectedCameraId";

export function useSelectedCamera() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      const list = await visionopsApi.listCameras();
      setCameras(list);
      setError(null);

      const stored =
        typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
      const preferred =
        list.find((c) => c.id === stored) ??
        list.find((c) => c.is_active) ??
        list[0] ??
        null;
      setSelectedId(preferred?.id ?? null);
      if (preferred && typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, preferred.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cameras");
      setCameras([]);
      setSelectedId(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const selectCamera = useCallback((id: string) => {
    setSelectedId(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, id);
    }
  }, []);

  const selected = cameras.find((c) => c.id === selectedId) ?? null;

  return {
    cameras,
    selected,
    selectedId,
    selectCamera,
    reload,
    loading,
    error,
  };
}
