/**
 * HireFlow Landing Page — Interactions
 * Loaded only on the landing page with defer.
 */

(function () {
  'use strict';

  // ── 1. Scroll Reveal (IntersectionObserver) ──
  var revealObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });

  document.querySelectorAll('[data-reveal]').forEach(function (el) {
    revealObserver.observe(el);
  });

  // ── 2. Navbar Scroll Effect ──
  var navbar = document.getElementById('lp-navbar');
  if (navbar) {
    window.addEventListener('scroll', function () {
      navbar.classList.toggle('scrolled', window.scrollY > 80);
    }, { passive: true });
  }

  // ── 3. Count-Up Animation on Stats ──
  var countObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        var el = entry.target;
        var target = parseInt(el.getAttribute('data-count'), 10);
        if (isNaN(target)) return;
        animateCount(el, target, 1200);
        countObserver.unobserve(el);
      }
    });
  }, { threshold: 0.3 });

  document.querySelectorAll('[data-count]').forEach(function (el) {
    countObserver.observe(el);
  });

  function animateCount(el, target, duration) {
    // Respect reduced motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      el.textContent = formatStatNumber(target);
      return;
    }
    var startTime = performance.now();
    function step(now) {
      var elapsed = now - startTime;
      var progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.round(target * eased);
      el.textContent = formatStatNumber(current);
      if (progress < 1) {
        requestAnimationFrame(step);
      }
    }
    requestAnimationFrame(step);
  }

  function formatStatNumber(n) {
    if (n >= 1000) {
      return n.toLocaleString('en-US');
    }
    return String(n);
  }

  // ── 4. Hero Search Form ──
  var searchForm = document.getElementById('hero-search');
  if (searchForm) {
    searchForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = searchForm.querySelector('[name="q"]').value.trim();
      var loc = searchForm.querySelector('[name="location"]').value.trim();
      if (!q && !loc) {
        searchForm.querySelector('[name="q"]').focus();
        return;
      }
      var params = new URLSearchParams();
      if (q) params.set('q', q);
      if (loc) params.set('location', loc);
      window.location.href = '/jobs/?' + params.toString();
    });
  }

  // ── 5. Mobile Menu Body Scroll Lock ──
  // Alpine.js handles the toggle; we just watch for changes
  var overlay = document.querySelector('.lp-mobile-overlay');
  if (overlay) {
    var observer = new MutationObserver(function () {
      var isOpen = overlay.classList.contains('open');
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });
    observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });
  }
})();
