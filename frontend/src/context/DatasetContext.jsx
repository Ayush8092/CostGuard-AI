import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { datasetsApi } from "../api/client";

const DatasetContext = createContext(null);

export function DatasetProvider({ children }) {
  const [activeDataset, setActiveDataset] = useState(null);
  const [datasets, setDatasets]           = useState([]);
  const [loading, setLoading]             = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [listRes, activeRes] = await Promise.all([
        datasetsApi.list(),
        datasetsApi.active(),
      ]);
      setDatasets(listRes.data);
      setActiveDataset(activeRes.data);
    } catch {
      // not authenticated yet - ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("costguard_token");
    if (token) refresh();
    else setLoading(false);
  }, [refresh]);

  const switchDataset = useCallback(async (datasetId) => {
    await datasetsApi.activate(datasetId);
    await refresh();
  }, [refresh]);

  return (
    <DatasetContext.Provider value={{ activeDataset, datasets, loading, refresh, switchDataset }}>
      {children}
    </DatasetContext.Provider>
  );
}

export function useDataset() {
  const ctx = useContext(DatasetContext);
  if (!ctx) throw new Error("useDataset must be used within DatasetProvider");
  return ctx;
}
