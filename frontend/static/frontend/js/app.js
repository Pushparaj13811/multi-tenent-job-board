/**
 * HireFlow App — Alpine.js root component + utilities
 */

// ── Theme Manager ──
const ThemeManager = {
  STORAGE_KEY: 'hf_theme',
  DARK: 'dark',
  LIGHT: 'light',

  /** Get the current theme from localStorage or system preference. */
  getPreferred() {
    const stored = localStorage.getItem(this.STORAGE_KEY);
    if (stored === this.DARK || stored === this.LIGHT) return stored;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      return this.LIGHT;
    }
    return this.DARK;
  },

  /** Apply theme to the document. */
  apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(this.STORAGE_KEY, theme);
    // Update meta theme-color
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === this.LIGHT ? '#FFFFFF' : '#0A0F1E');
    }
    // Update body classes for Tailwind
    if (theme === this.LIGHT) {
      document.body.classList.remove('bg-dark-base', 'text-white');
      document.body.classList.add('bg-white', 'text-slate-900');
    } else {
      document.body.classList.remove('bg-white', 'text-slate-900');
      document.body.classList.add('bg-dark-base', 'text-white');
    }
  },

  /** Toggle between light and dark. Returns the new theme. */
  toggle() {
    const current = document.documentElement.getAttribute('data-theme') || this.DARK;
    const next = current === this.DARK ? this.LIGHT : this.DARK;
    this.apply(next);
    return next;
  },

  /** Initialize on page load. Call this early. */
  init() {
    const theme = this.getPreferred();
    this.apply(theme);
    // Listen for system preference changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
        // Only auto-switch if user hasn't manually set a preference
        if (!localStorage.getItem(this.STORAGE_KEY)) {
          this.apply(e.matches ? this.LIGHT : this.DARK);
        }
      });
    }
  },

  /** Get current theme. */
  current() {
    return document.documentElement.getAttribute('data-theme') || this.DARK;
  },

  isDark() { return this.current() === this.DARK; },
  isLight() { return this.current() === this.LIGHT; },
};

// Toast counter for unique IDs
let _toastId = 0;
const MAX_TOASTS = 5;

// Standalone error extractor — usable inside inline x-data blocks
function extractErrors(err) {
  const errors = {};
  const data = err.data || {};
  const source = data.details || data;
  for (const [key, val] of Object.entries(source)) {
    if (key === 'error' || key === 'code') continue;
    if (Array.isArray(val)) {
      errors[key] = val.join(' ');
    } else if (typeof val === 'string') {
      errors[key] = val;
    } else if (typeof val === 'object' && val !== null) {
      errors[key] = JSON.stringify(val);
    }
  }
  return errors;
}

function app() {
  return {
    toasts: [],
    unreadCount: 0,
    darkMode: true,

    init() {
      HireFlowAPI.init();
      this.darkMode = ThemeManager.isDark();
      if (HireFlowAPI.isAuthenticated()) {
        this.fetchUnreadCount();
        // Poll for new notifications every 60 seconds
        setInterval(() => this.fetchUnreadCount(), 60000);
      }
    },

    toggleTheme() {
      ThemeManager.toggle();
      this.darkMode = ThemeManager.isDark();
    },

    // ── Toast notifications ──

    showToast(message, type = 'info', duration = 4000) {
      const id = ++_toastId;
      const toast = {
        id,
        message,
        type,
        visible: true,
        paused: false,
        progress: 100,
        duration,
        _startTime: Date.now(),
        _remaining: duration,
      };

      // Stack limit: remove oldest if at max
      if (this.toasts.length >= MAX_TOASTS) {
        this.toasts.shift();
      }

      this.toasts.push(toast);
      this._startToastTimer(toast);
    },

    _startToastTimer(toast) {
      const tick = () => {
        if (!toast.visible) return;
        if (toast.paused) {
          toast._rafId = requestAnimationFrame(tick);
          return;
        }
        const elapsed = Date.now() - toast._startTime;
        const remaining = toast._remaining - elapsed + (toast._pauseAdjust || 0);
        toast.progress = Math.max(0, (remaining / toast.duration) * 100);

        if (remaining <= 0) {
          this.dismissToast(toast.id);
        } else {
          toast._rafId = requestAnimationFrame(tick);
        }
      };
      toast._rafId = requestAnimationFrame(tick);
    },

    pauseToast(id) {
      const toast = this.toasts.find(t => t.id === id);
      if (toast && !toast.paused) {
        toast.paused = true;
        toast._pauseStart = Date.now();
      }
    },

    resumeToast(id) {
      const toast = this.toasts.find(t => t.id === id);
      if (toast && toast.paused) {
        toast.paused = false;
        // Adjust timing so remaining time is preserved
        const pauseDuration = Date.now() - toast._pauseStart;
        toast._startTime += pauseDuration;
      }
    },

    dismissToast(id) {
      const toast = this.toasts.find(t => t.id === id);
      if (toast) {
        toast.visible = false;
        if (toast._rafId) cancelAnimationFrame(toast._rafId);
        setTimeout(() => {
          this.toasts = this.toasts.filter(t => t.id !== id);
        }, 200);
      }
    },

    success(message) { this.showToast(message, 'success'); },
    error(message) { this.showToast(message, 'error', 6000); },
    info(message) { this.showToast(message, 'info'); },
    warning(message) { this.showToast(message, 'warning', 5000); },

    // ── Notification badge ──

    async fetchUnreadCount() {
      try {
        const data = await HireFlowAPI.listNotifications('is_read=false');
        this.unreadCount = data.unread_count || 0;
      } catch {
        // silently fail
      }
    },

    // ── Utility helpers ──

    formatDate(isoString) {
      if (!isoString) return '';
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },

    timeAgo(isoString) {
      if (!isoString) return '';
      const now = new Date();
      const date = new Date(isoString);
      const seconds = Math.floor((now - date) / 1000);
      if (seconds < 60) return 'just now';
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return `${minutes}m ago`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      if (days < 30) return `${days}d ago`;
      return this.formatDate(isoString);
    },

    formatSalary(min, max, currency = 'USD') {
      const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 });
      if (min && max) return `${fmt.format(min)} - ${fmt.format(max)}`;
      if (min) return `From ${fmt.format(min)}`;
      if (max) return `Up to ${fmt.format(max)}`;
      return 'Not specified';
    },

    statusColor(status) {
      const colors = {
        applied: 'status-applied',
        reviewing: 'status-reviewing',
        shortlisted: 'status-shortlisted',
        interview: 'status-interview',
        offered: 'status-offered',
        rejected: 'status-rejected',
        withdrawn: 'status-withdrawn',
        draft: 'status-draft',
        published: 'status-published',
        closed: 'status-closed',
      };
      return colors[status] || 'status-draft';
    },

    jobTypeLabel(type) {
      const labels = {
        full_time: 'Full Time', part_time: 'Part Time',
        contract: 'Contract', internship: 'Internship', remote: 'Remote',
      };
      return labels[type] || type;
    },

    experienceLabel(level) {
      const labels = { junior: 'Junior', mid: 'Mid-Level', senior: 'Senior', lead: 'Lead' };
      return labels[level] || level;
    },

    // Delegate to standalone extractErrors (avoids duplication)
    extractErrors,

    // Animate number counting up
    countUp(el, target, duration = 600) {
      if (!target || target <= 0) { el.textContent = '0'; return; }
      const start = 0;
      const startTime = performance.now();
      const step = (now) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease-out quad
        const eased = 1 - (1 - progress) * (1 - progress);
        el.textContent = Math.round(start + (target - start) * eased);
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    },

    // Extract cursor from URL
    extractCursor(url) {
      if (!url) return null;
      try {
        const u = new URL(url, window.location.origin);
        return u.searchParams.get('cursor');
      } catch {
        return null;
      }
    },
  };
}
