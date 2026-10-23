import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach Bearer token to all outgoing requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('cp_rag_token');
    if (token) {
      config.headers = config.headers || {};
      if (typeof config.headers.set === 'function') {
        config.headers.set('Authorization', `Bearer ${token}`);
      } else {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export const authApi = {
  register: async (email, username, password) => {
    const res = await api.post('/api/auth/register', { email, username, password });
    return res.data;
  },
  login: async (email_or_username, password) => {
    const res = await api.post('/api/auth/login', { email_or_username, password });
    return res.data;
  },
  getMe: async () => {
    const res = await api.get('/api/auth/me');
    return res.data;
  },
};

export const platformApi = {
  connectCodeforces: async (handle, apiKey = null, apiSecret = null) => {
    const payload = { handle };
    if (apiKey) payload.api_key = apiKey;
    if (apiSecret) payload.api_secret = apiSecret;
    const res = await api.post('/api/platforms/codeforces/connect', payload);
    return res.data;
  },
  getCodeforcesStatus: async () => {
    const res = await api.get('/api/platforms/codeforces/status');
    return res.data;
  },
  syncCodeforces: async () => {
    const res = await api.post('/api/platforms/codeforces/sync');
    return res.data;
  },
  connectLeetCode: async (handle) => {
    const res = await api.post('/api/platforms/leetcode/connect', { handle });
    return res.data;
  },
  syncLeetCode: async () => {
    const res = await api.post('/api/platforms/leetcode/sync');
    return res.data;
  },
  connectCodeChef: async (handle) => {
    const res = await api.post('/api/platforms/codechef/connect', { handle });
    return res.data;
  },
  syncCodeChef: async () => {
    const res = await api.post('/api/platforms/codechef/sync');
    return res.data;
  },
  connectGitHub: async (repoUrl, accessToken = null) => {
    const payload = { repo_url: repoUrl };
    if (accessToken) payload.access_token = accessToken;
    const res = await api.post('/api/platforms/github/connect', payload);
    return res.data;
  },
  getGitHubStatus: async () => {
    const res = await api.get('/api/platforms/github/status');
    return res.data;
  },
  disconnectGitHub: async () => {
    const res = await api.delete('/api/platforms/github/disconnect');
    return res.data;
  },
  getAllStatuses: async () => {
    const res = await api.get('/api/platforms/status');
    return res.data;
  },
  getStats: async () => {
    const res = await api.get('/api/stats');
    return res.data;
  },
};


export const publicProfilesApi = {
  search: async (platform, username) => {
    const res = await api.post('/api/public-profiles/search', { platform, username });
    return res.data;
  },
};

export const submissionApi = {
  getSubmissions: async (params = {}) => {
    const res = await api.get('/api/submissions', { params });
    return res.data;
  },
  addSourceCode: async (submissionId, sourceCode, language, filename) => {
    const res = await api.post(`/api/submissions/${submissionId}/source-code`, {
      source_code: sourceCode,
      language,
      filename,
    });
    return res.data;
  },
  uploadSourceCodeFile: async (submissionId, formData) => {
    const res = await api.post(`/api/submissions/${submissionId}/upload-source-code`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },
  getSourceCode: async (submissionId, filePath = null) => {
    const params = filePath ? { file_path: filePath } : {};
    const res = await api.get(`/api/submissions/${submissionId}/source-code`, { params });
    return res.data;
  },
};

export const vectorApi = {
  indexSubmission: async (submissionId) => {
    const res = await api.post(`/api/vector/index/${submissionId}`);
    return res.data;
  },
  indexAllSubmissions: async () => {
    const res = await api.post('/api/vector/index-all');
    return res.data;
  },
  getIndexStatus: async () => {
    const res = await api.get('/api/vector/index-status');
    return res.data;
  },
  searchKnowledge: async (query, top_k = 20) => {
    const res = await api.post('/api/vector/search', { query, top_k });
    return res.data;
  },
};

export const ragApi = {
  queryKnowledge: async (query, top_k = 10) => {
    const res = await api.post('/api/rag/query', { query, top_k });
    return res.data;
  },
};

export default api;
