import axios from "axios";

const api = axios.create({ baseURL: "/api/v1" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("costguard_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("costguard_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

export const authApi = {
  signup: (payload) => api.post("/auth/signup", payload),
  login: (email, password) => {
    const form = new URLSearchParams();
    form.append("username", email);
    form.append("password", password);
    return api.post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
  },
};

export const dashboardApi       = { get: () => api.get("/dashboard") };
export const forecastApi        = {
  get: (level = "org_total", service = null) =>
    api.get("/forecast", { params: { level, ...(service ? { service } : {}) } }),
};
export const anomaliesApi       = {
  list: (severity = null, limit = 100) =>
    api.get("/anomalies", { params: { ...(severity ? { severity } : {}), limit } }),
};
export const wasteApi           = {
  list: (bucket = null) => api.get("/waste", { params: bucket ? { bucket } : {} }),
};
export const recommendationsApi = {
  list:         (impactTier = null) =>
    api.get("/recommendations", { params: impactTier ? { impact_tier: impactTier } : {} }),
  evaluation:   ()           => api.get("/recommendations/evaluation"),
  updateStatus: (id, status) =>
    api.patch(`/recommendations/${id}/status`, null, { params: { new_status: status } }),
};
export const simulatorApi       = {
  simulate: (actions, windowDays = 30) =>
    api.post("/simulate", { actions, window_days: windowDays }),
};
export const copilotApi         = { ask: (question) => api.post("/copilot", { question }) };
export const reportsApi         = {
  list:   () => api.get("/reports/weekly"),
  latest: () => api.get("/reports/weekly/latest"),
};
export const monitoringApi      = {
  registry:        (modelType = null) =>
    api.get("/models/registry", { params: modelType ? { model_type: modelType } : {} }),
  loadTestSummary: () => api.get("/models/load-test-summary"),
  triggerRetrain:  () => api.post("/models/retrain"),
};
export const uploadApi          = {
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/upload-csv", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  status: (datasetId) => api.get(`/upload-csv/${datasetId}/status`),
};
export const businessMetricsApi = { get: () => api.get("/business-metrics") };

// ── Dataset management (Feature 1 + 2 + 4) ───────────────────────────────
export const datasetsApi = {
  upload: (file, uploadMode = "continuous", datasetName = null) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ upload_mode: uploadMode });
    if (datasetName) params.append("dataset_name", datasetName);
    return api.post(`/datasets/upload?${params}`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  list:     ()    => api.get("/datasets"),
  active:   ()    => api.get("/datasets/active"),
  activate: (id)  => api.post(`/datasets/${id}/activate`),
  status:   (id)  => api.get(`/datasets/${id}/status`),
  reset:    ()    => api.post("/datasets/reset", { confirmation: "RESET" }),
};

// ── Executive insights (Feature 3) ───────────────────────────────────────
export const insightsApi = {
  active:     ()          => api.get("/insights/active"),
  generate:   (datasetId) => api.post("/insights/generate", { dataset_id: datasetId || null }),
  forDataset: (id)        => api.get(`/insights/${id}`),
};
