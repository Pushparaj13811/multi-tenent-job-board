/**
 * HireFlow API Client
 *
 * Handles JWT token management (store, refresh, auto-retry on 401)
 * and provides typed methods for every API endpoint.
 *
 * Auth strategy:
 *  - Frontend Django views use session auth (server-side login/logout)
 *  - JS API client uses JWT for async operations (AJAX calls from Alpine.js)
 *  - On login page, we POST to /api/auth/login/ to get JWT tokens and store them
 */

const HireFlowAPI = {
  // Token storage
  _accessToken: null,
  _refreshToken: null,

  init() {
    this._accessToken = localStorage.getItem('hf_access');
    this._refreshToken = localStorage.getItem('hf_refresh');
  },

  setTokens(access, refresh) {
    this._accessToken = access;
    this._refreshToken = refresh;
    if (access) localStorage.setItem('hf_access', access);
    if (refresh) localStorage.setItem('hf_refresh', refresh);
  },

  clearTokens() {
    this._accessToken = null;
    this._refreshToken = null;
    localStorage.removeItem('hf_access');
    localStorage.removeItem('hf_refresh');
  },

  isAuthenticated() {
    return !!this._accessToken;
  },

  // ── CSRF token ──

  _getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  },

  // ── Core fetch wrapper ──

  async _fetch(url, options = {}) {
    const headers = options.headers || {};

    if (this._accessToken && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${this._accessToken}`;
    }

    // Send CSRF token on all non-GET requests
    const method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && !headers['X-CSRFToken']) {
      headers['X-CSRFToken'] = this._getCsrfToken();
    }

    // Don't set Content-Type for FormData (let browser set boundary)
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, { ...options, headers });

    // Auto-refresh on 401
    if (response.status === 401 && this._refreshToken && !options._retried) {
      const refreshed = await this._refreshAccessToken();
      if (refreshed) {
        return this._fetch(url, { ...options, _retried: true });
      }
      // Refresh failed — clear tokens
      this.clearTokens();
    }

    return response;
  },

  async _refreshAccessToken() {
    try {
      const resp = await fetch('/api/auth/token/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: this._refreshToken }),
      });
      if (resp.ok) {
        const data = await resp.json();
        this.setTokens(data.access, data.refresh || this._refreshToken);
        return true;
      }
    } catch (e) {
      console.error('Token refresh failed:', e);
    }
    return false;
  },

  async _get(url) {
    const resp = await this._fetch(url);
    if (!resp.ok) throw await this._parseError(resp);
    return resp.json();
  },

  async _post(url, data) {
    const isFormData = data instanceof FormData;
    const resp = await this._fetch(url, {
      method: 'POST',
      body: isFormData ? data : JSON.stringify(data),
    });
    if (!resp.ok) throw await this._parseError(resp);
    return resp.json();
  },

  async _patch(url, data) {
    const resp = await this._fetch(url, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    if (!resp.ok) throw await this._parseError(resp);
    return resp.json();
  },

  async _delete(url) {
    const resp = await this._fetch(url, { method: 'DELETE' });
    if (!resp.ok) throw await this._parseError(resp);
    // DELETE may return 200 with body or 204 with no body
    const text = await resp.text();
    return text ? JSON.parse(text) : {};
  },

  async _parseError(resp) {
    try {
      const data = await resp.json();
      return {
        status: resp.status,
        message: data.error || data.detail || JSON.stringify(data),
        data,
      };
    } catch {
      return { status: resp.status, message: resp.statusText, data: {} };
    }
  },

  // ── Auth ──

  async login(email, password) {
    const data = await this._post('/api/auth/login/', { email, password });
    this.setTokens(data.access, data.refresh);
    return data;
  },

  async register(payload) {
    return this._post('/api/auth/register/', payload);
  },

  // ── Jobs ──

  async listJobs(params = '') {
    return this._get(`/api/jobs/${params ? '?' + params : ''}`);
  },

  async getJob(slug) {
    return this._get(`/api/jobs/${slug}/`);
  },

  async createJob(data) {
    return this._post('/api/jobs/', data);
  },

  async updateJob(slug, data) {
    return this._patch(`/api/jobs/${slug}/`, data);
  },

  async publishJob(slug) {
    return this._post(`/api/jobs/${slug}/publish/`, {});
  },

  async closeJob(slug) {
    return this._post(`/api/jobs/${slug}/close/`, {});
  },

  async searchJobs(query) {
    return this._get(`/api/jobs/search/?q=${encodeURIComponent(query)}`);
  },

  // ── Companies ──

  async listCompanies(params = '') {
    return this._get(`/api/companies/${params ? '?' + params : ''}`);
  },

  async getCompany(slug) {
    return this._get(`/api/companies/${slug}/`);
  },

  async createCompany(data) {
    return this._post('/api/companies/', data);
  },

  async inviteMember(companySlug, email) {
    return this._post(`/api/companies/${companySlug}/members/`, { email });
  },

  // ── Applications ──

  async listApplications(params = '') {
    return this._get(`/api/applications/${params ? '?' + params : ''}`);
  },

  async createApplication(formData) {
    return this._post('/api/applications/', formData);
  },

  async withdrawApplication(id) {
    return this._delete(`/api/applications/${id}/`);
  },

  async updateApplicationStatus(id, status, recruiterNotes = '') {
    const data = { status };
    if (recruiterNotes) data.recruiter_notes = recruiterNotes;
    return this._patch(`/api/applications/${id}/status/`, data);
  },

  // ── Notifications ──

  async listNotifications(params = '') {
    return this._get(`/api/notifications/${params ? '?' + params : ''}`);
  },

  async markNotificationRead(id) {
    return this._patch(`/api/notifications/${id}/read/`, {});
  },

  async markAllNotificationsRead() {
    return this._post('/api/notifications/mark-all-read/', {});
  },

  // ── Dashboard ──

  async getRecruiterDashboard() {
    return this._get('/api/dashboard/recruiter/');
  },

  async getCandidateDashboard() {
    return this._get('/api/dashboard/candidate/');
  },
};
