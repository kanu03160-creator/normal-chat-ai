/**
 * Normal Chat — Landing Page Interactive Scripts
 * Handles:
 * 1. Sticky Navbar background transition on scroll
 * 2. Mobile navigation drawer toggle with keyboard & outside-click support
 * 3. Interactive FAQ accordion with animated max-height & ARIA states
 * 4. Feature cards mouse cursor spotlight illumination
 * 5. Smooth scroll active link spy via IntersectionObserver
 * 6. Interactive UI feedback on mockup action buttons
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileMenu();
  initFaqAccordion();
  initPricingToggle();
  initCardSpotlights();
  initScrollSpy();
  initMockupActions();
});

/**
 * 1. Navbar Scroll Transition
 * Adds a blurred dark backdrop & border once scrolled down
 */
function initNavbarScroll() {
  const navbar = document.getElementById('navbar');
  if (!navbar) return;

  const handleScroll = () => {
    if (window.scrollY > 24) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll(); // Initial check
}

/**
 * 2. Mobile Navigation Drawer
 */
function initMobileMenu() {
  const toggleBtn = document.getElementById('mobile-toggle');
  const menu = document.getElementById('mobile-nav-menu');
  const mobileLinks = document.querySelectorAll('.mobile-link');

  if (!toggleBtn || !menu) return;

  function toggleMenu(forceClose = false) {
    const isOpen = forceClose ? false : !menu.classList.contains('open');
    menu.classList.toggle('open', isOpen);
    toggleBtn.setAttribute('aria-expanded', String(isOpen));
    menu.setAttribute('aria-hidden', String(!isOpen));

    // Update hamburger icon appearance
    if (isOpen) {
      toggleBtn.innerHTML = `
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      `;
    } else {
      toggleBtn.innerHTML = `
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      `;
    }
  }

  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleMenu();
  });

  // Close when clicking any mobile link
  mobileLinks.forEach((link) => {
    link.addEventListener('click', () => {
      toggleMenu(true);
    });
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menu.classList.contains('open')) {
      toggleMenu(true);
    }
  });

  // Close on click outside
  document.addEventListener('click', (e) => {
    if (menu.classList.contains('open') && !menu.contains(e.target) && !toggleBtn.contains(e.target)) {
      toggleMenu(true);
    }
  });
}

/**
 * 3. FAQ Accordion
 * Accessible, animated accordion
 */
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');

  faqItems.forEach((item) => {
    const btn = item.querySelector('.faq-question-btn');
    const panel = item.querySelector('.faq-answer-panel');
    if (!btn || !panel) return;

    btn.addEventListener('click', () => {
      const isExpanded = btn.getAttribute('aria-expanded') === 'true';

      // Close other accordion items for clean focus
      faqItems.forEach((otherItem) => {
        if (otherItem !== item && otherItem.classList.contains('active')) {
          otherItem.classList.remove('active');
          const otherBtn = otherItem.querySelector('.faq-question-btn');
          const otherPanel = otherItem.querySelector('.faq-answer-panel');
          if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
          if (otherPanel) otherPanel.style.maxHeight = '0px';
        }
      });

      // Toggle current item
      if (isExpanded) {
        item.classList.remove('active');
        btn.setAttribute('aria-expanded', 'false');
        panel.style.maxHeight = '0px';
      } else {
        item.classList.add('active');
        btn.setAttribute('aria-expanded', 'true');
        panel.style.maxHeight = panel.scrollHeight + 'px';
      }
    });
  });
}

/**
 * 4. Card Spotlight Hover Effect
 * Tracks mouse position over feature cards to produce subtle radial illumination
 */
function initCardSpotlights() {
  const cards = document.querySelectorAll('.feature-card, .step-card, .benefit-card, .pricing-card');

  cards.forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      card.style.setProperty('--mouse-x', `${x}px`);
      card.style.setProperty('--mouse-y', `${y}px`);
    });
  });
}

/**
 * 5. Scroll Spy & Active Nav Link Highlighting
 */
function initScrollSpy() {
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-links .nav-link');

  if (!sections.length || !navLinks.length) return;

  const observerOptions = {
    root: null,
    rootMargin: '-30% 0px -60% 0px',
    threshold: 0
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const currentId = entry.target.getAttribute('id');
        navLinks.forEach((link) => {
          const href = link.getAttribute('href');
          if (href === `#${currentId}`) {
            link.classList.add('active');
          } else {
            link.classList.remove('active');
          }
        });
      }
    });
  }, observerOptions);

  sections.forEach((sec) => observer.observe(sec));
}

/**
 * 6. Interactive Mockup Buttons
 * Provides realistic feedback when interacting with buttons in mockups
 */
function initMockupActions() {
  const copyButtons = document.querySelectorAll('.control-btn');
  copyButtons.forEach((btn) => {
    if (btn.innerText.includes('Copy')) {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const originalText = btn.innerHTML;
        btn.innerHTML = `
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          <span style="color: #34D399;">Copied!</span>
        `;
        setTimeout(() => {
          btn.innerHTML = originalText;
        }, 1800);
      });
    }
  });

  // Handle local protocol file fallback alert for /chat and /login if tested directly via file://
  const placeholderLinks = document.querySelectorAll('a[href="/chat"], a[href="/login"]');
  placeholderLinks.forEach((link) => {
    link.addEventListener('click', (e) => {
      if (window.location.protocol === 'file:') {
        e.preventDefault();
        const target = link.getAttribute('href');
        alert(`Normal Chat Landing Demo: Route '${target}' is configured and will connect directly to your Flask application backend when hosted.`);
      }
    });
  });
}

/**
 * 7. Pricing Toggle (Monthly vs Annual)
 */
function initPricingToggle() {
  const toggleBtn = document.getElementById('pricing-toggle');
  const monthlyLabel = document.getElementById('billing-monthly-label');
  const annualLabel = document.getElementById('billing-annual-label');
  const priceValues = document.querySelectorAll('.price-value');
  const pricePeriods = document.querySelectorAll('.price-period[data-monthly-sub]');

  if (!toggleBtn) return;

  let isAnnual = false;

  function updatePricing(annual) {
    isAnnual = annual;
    toggleBtn.classList.toggle('annual', isAnnual);
    toggleBtn.setAttribute('aria-checked', String(isAnnual));

    if (monthlyLabel && annualLabel) {
      monthlyLabel.classList.toggle('active', !isAnnual);
      annualLabel.classList.toggle('active', isAnnual);
    }

    priceValues.forEach((valEl) => {
      const targetVal = isAnnual ? valEl.getAttribute('data-annual') : valEl.getAttribute('data-monthly');
      if (targetVal !== null) {
        valEl.textContent = targetVal;
      }
    });

    pricePeriods.forEach((periodEl) => {
      const targetSub = isAnnual ? periodEl.getAttribute('data-annual-sub') : periodEl.getAttribute('data-monthly-sub');
      if (targetSub !== null) {
        periodEl.textContent = targetSub;
      }
    });
  }

  toggleBtn.addEventListener('click', () => {
    updatePricing(!isAnnual);
  });

  if (monthlyLabel) {
    monthlyLabel.addEventListener('click', () => updatePricing(false));
  }
  if (annualLabel) {
    annualLabel.addEventListener('click', () => updatePricing(true));
  }
}
