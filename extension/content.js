/**
 * Chrome Agent Content Script - Enhanced Version
 *
 * Injected into web pages to provide DOM interaction capabilities.
 * Supports viewport/full/element snapshot modes, stable element references,
 * and sensitive data redaction.
 */

(function() {
  'use strict';

  // Prevent duplicate injection
  if (window.__CHROME_AGENT_INJECTED__) {
    return;
  }
  window.__CHROME_AGENT_INJECTED__ = true;

  // Document identity
  const DOCUMENT_ID = `doc-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  // Element reference management
  let elementCounter = 1;
  const elementToRef = new WeakMap();
  const refToElement = new Map();

  // Sensitive field types
  const SENSITIVE_TYPES = ['password', 'tel', 'email', 'credit-card', 'ssn'];
  const SENSITIVE_PATTERNS = [
    /password/i,
    /passcode/i,
    /验证码/i,
    /手机号/i,
    /身份证/i,
    /信用卡/i,
    /cvv/i,
    /token/i,
  ];

  /**
   * Generate or get element reference
   */
  function getElementRef(element) {
    if (!element) return null;

    let ref = elementToRef.get(element);
    if (!ref) {
      ref = `e${elementCounter++}`;
      elementToRef.set(element, ref);
      refToElement.set(ref, new WeakRef(element));
    }
    return ref;
  }

  /**
   * Get element by reference
   */
  function getElementByRef(ref) {
    const weakRef = refToElement.get(ref);
    if (weakRef) {
      return weakRef.deref();
    }
    return null;
  }

  /** Return a clickable overlay anchor's visible ancestor rect when needed. */
  function getEffectiveRect(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) return rect;
    if (element instanceof HTMLAnchorElement && element.href) {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const parentRect = parent.getBoundingClientRect();
        if (parentRect.width > 0 && parentRect.height > 0) return parentRect;
        parent = parent.parentElement;
      }
    }
    return rect;
  }

  /**
   * Check if element is visible
   */
  function isVisible(element) {
    if (!element) return false;

    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return false;
    }

    const rect = getEffectiveRect(element);
    return rect.width > 0 && rect.height > 0;
  }

  /**
   * Check if element is in viewport
   */
  function isInViewport(element) {
    if (!element) return false;

    const rect = getEffectiveRect(element);
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= window.innerHeight &&
      rect.right <= window.innerWidth
    );
  }

  // Interactive tags and roles (shared)
  const INTERACTIVE_TAGS = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA', 'DETAILS', 'SUMMARY'];
  const INTERACTIVE_ROLES = [
    'button', 'link', 'checkbox', 'radio', 'switch', 'textbox',
    'combobox', 'listbox', 'option', 'menuitem', 'slider',
    'spinbutton', 'searchbox', 'tab'
  ];

  /**
   * Check if element is interactive
   */
  function isInteractive(element) {
    if (!element) return false;

    if (INTERACTIVE_TAGS.includes(element.tagName)) {
      return true;
    }

    const role = element.getAttribute('role');
    if (role && INTERACTIVE_ROLES.includes(role)) {
      return true;
    }

    // Check for click handlers (heuristic)
    if (element.onclick || element.getAttribute('onclick')) {
      return true;
    }

    // Check for tabindex
    const tabindex = element.getAttribute('tabindex');
    if (tabindex !== null && parseInt(tabindex) >= 0) {
      return true;
    }

    return false;
  }

  /**
   * Check if field is sensitive
   */
  function isSensitiveField(element) {
    if (!element) return false;

    // Check input type
    const inputType = element.type || element.getAttribute('type');
    if (inputType === 'password') {
      return true;
    }

    // Check name attribute
    const name = element.getAttribute('name') || '';
    const placeholder = element.getAttribute('placeholder') || '';
    const ariaLabel = element.getAttribute('aria-label') || '';

    const textToCheck = `${name} ${placeholder} ${ariaLabel}`.toLowerCase();

    for (const pattern of SENSITIVE_PATTERNS) {
      if (pattern.test(textToCheck)) {
        return true;
      }
    }

    return false;
  }

  /**
   * Get element information
   */
  function getElementInfo(element) {
    if (!element) return null;

    const rect = getEffectiveRect(element);
    const isSensitive = isSensitiveField(element);

    // Build locator hints
    const locator = {};
    if (element.id) {
      locator.id = element.id;
    }
    if (element.className) {
      locator.className = element.className;
    }
    if (element.getAttribute('name')) {
      locator.name = element.getAttribute('name');
    }

    // Get text content (limited)
    let textContent = null;
    if (element.textContent) {
      textContent = element.textContent.trim().substring(0, 200);
    }

    return {
      ref: getElementRef(element),
      tag: element.tagName.toLowerCase(),
      href: element instanceof HTMLAnchorElement ? element.href : null,
      role: element.getAttribute('role') || null,
      name: element.getAttribute('name') || null,
      id: element.id || null,
      className: element.className || null,
      text: textContent,
      placeholder: element.getAttribute('placeholder') || null,
      type: element.type || null,
      states: {
        visible: isVisible(element),
        inViewport: isInViewport(element),
        enabled: !element.disabled,
        focusable: element.tabIndex >= 0 || INTERACTIVE_TAGS.includes(element.tagName),
        focused: document.activeElement === element,
      },
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        coordinateSpace: 'viewport-css-px',
      },
      interactive: isInteractive(element),
      sensitive: isSensitive,
      value: isSensitive ? { present: !!element.value, redacted: true } : element.value || null,
      locator: locator,
    };
  }

  /**
   * Build DOM snapshot
   */
  function buildSnapshot(scope = 'viewport') {
    const elements = [];
    let allElements;

    if (scope === 'element' && arguments[1]) {
      // Element scope - snapshot specific element
      allElements = [arguments[1]];
    } else {
      // Viewport or full scope
      allElements = document.querySelectorAll('*');
    }

    allElements.forEach(element => {
      // Skip invisible elements in viewport mode
      if (scope === 'viewport' && !isVisible(element)) {
        return;
      }

      // For full scope, include all interactive elements and text containers
      if (scope === 'full') {
        if (!isInteractive(element) && !element.textContent?.trim()) {
          return;
        }
      }

      // For viewport scope, include interactive elements and visible text
      if (scope === 'viewport') {
        if (!isInteractive(element) && !element.textContent?.trim()) {
          return;
        }
      }

      const info = getElementInfo(element);
      if (info) {
        elements.push(info);
      }
    });

    // Sort by position (top to bottom, left to right)
    elements.sort((a, b) => {
      if (Math.abs(a.rect.y - b.rect.y) < 50) {
        return a.rect.x - b.rect.x;
      }
      return a.rect.y - b.rect.y;
    });

    return {
      documentId: DOCUMENT_ID,
      url: window.location.href,
      title: document.title,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        devicePixelRatio: window.devicePixelRatio || 1,
        pageZoom: window.visualViewport?.scale || 1,
      },
      elements: elements.slice(0, 500), // Limit to 500 elements
      timestamp: new Date().toISOString(),
      scope: scope,
      truncated: elements.length > 500,
    };
  }

  /**
   * Capture screenshot of element or viewport
   */
  async function captureScreenshot(scope = 'viewport', ref = null, regionRect = null) {
    try {
      let targetElement = null;
      let rect = null;

      if (scope === 'element' && ref) {
        targetElement = getElementByRef(ref);
        if (!targetElement) {
          return { success: false, error: 'Element not found for screenshot' };
        }
        rect = targetElement.getBoundingClientRect();
      } else if (scope === 'region' && regionRect) {
        rect = regionRect;
      } else {
        // Viewport screenshot
        rect = {
          x: 0,
          y: 0,
          width: window.innerWidth,
          height: window.innerHeight,
        };
      }

      // Add padding for context
      const padding = 24;
      const captureRect = {
        x: Math.max(0, rect.x - padding),
        y: Math.max(0, rect.y - padding),
        width: Math.min(window.innerWidth, rect.width + padding * 2),
        height: Math.min(window.innerHeight, rect.height + padding * 2),
      };

      // Use html2canvas-like approach or native screenshot
      // For now, return the rect info for the background script to capture
      return {
        success: true,
        scope: scope,
        rect: captureRect,
        devicePixelRatio: window.devicePixelRatio || 1,
        pageZoom: window.visualViewport?.scale || 1,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        documentId: DOCUMENT_ID,
      };
    } catch (error) {
      return { success: false, error: `Screenshot failed: ${error.message}` };
    }
  }

  /**
   * Check if page is sensitive (login, payment, etc.)
   */
  function checkPageSensitivity() {
    const sensitivePatterns = [
      /login/i,
      /signin/i,
      /auth/i,
      /password/i,
      /payment/i,
      /checkout/i,
      /billing/i,
      /credit/i,
      /bank/i,
    ];

    const url = window.location.href.toLowerCase();
    const title = document.title.toLowerCase();

    for (const pattern of sensitivePatterns) {
      if (pattern.test(url) || pattern.test(title)) {
        return {
          sensitive: true,
          level: 'sensitive',
          reason: `Page matches sensitive pattern: ${pattern.source}`,
        };
      }
    }

    return { sensitive: false, level: 'normal' };
  }

  /**
   * Redact sensitive areas in screenshot data
   */
  function redactSensitiveAreas(dataUrl) {
    // In a real implementation, this would analyze the screenshot
    // and redact sensitive areas like password fields, credit card numbers, etc.
    // For now, return the original data URL
    return {
      redacted: false,
      dataUrl: dataUrl,
      reason: 'Redaction not implemented in V1',
    };
  }
  function performClick(ref) {
    const element = getElementByRef(ref);
    if (!element) {
      return { success: false, error: 'Element not found' };
    }

    if (!isVisible(element)) {
      return { success: false, error: 'Element not visible' };
    }

    // Scroll element into view
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Simulate click
    const clickEvent = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      view: window,
    });
    element.dispatchEvent(clickEvent);

    return { success: true, clicked: true };
  }

  /**
   * Fill input element
   */
  function performFill(ref, value) {
    const element = getElementByRef(ref);
    if (!element) {
      return { success: false, error: 'Element not found' };
    }

    if (!isVisible(element)) {
      return { success: false, error: 'Element not visible' };
    }

    // Scroll element into view
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Focus element
    element.focus();

    // Set value
    element.value = value;

    // Trigger input event
    const inputEvent = new Event('input', { bubbles: true });
    element.dispatchEvent(inputEvent);

    // Trigger change event
    const changeEvent = new Event('change', { bubbles: true });
    element.dispatchEvent(changeEvent);

    return { success: true, filled: true };
  }

  /**
   * Scroll page or element
   */
  function isScrollable(element) {
    if (!element) return false;
    if (element === document.scrollingElement) {
      return element.scrollHeight > element.clientHeight;
    }
    const style = window.getComputedStyle(element);
    return /(auto|scroll|overlay)/.test(style.overflowY) &&
      element.scrollHeight > element.clientHeight + 1;
  }

  function findScrollTarget(ref = null) {
    const referenced = ref ? getElementByRef(ref) : null;
    let candidate = referenced;
    while (candidate && candidate !== document.body) {
      if (isScrollable(candidate)) return candidate;
      candidate = candidate.parentElement;
    }

    const visibleCandidates = Array.from(document.querySelectorAll('*'))
      .filter(isScrollable)
      .filter(isVisible)
      .sort((a, b) => {
        const aRect = a.getBoundingClientRect();
        const bRect = b.getBoundingClientRect();
        return (bRect.width * bRect.height) - (aRect.width * aRect.height);
      });
    return visibleCandidates[0] || document.scrollingElement || document.documentElement;
  }

  function performScroll(dx = 0, dy = 0, ref = null) {
    const target = findScrollTarget(ref);
    const isDocument = target === document.scrollingElement ||
      target === document.documentElement || target === document.body;
    const beforeX = isDocument ? window.scrollX : target.scrollLeft;
    const beforeY = isDocument ? window.scrollY : target.scrollTop;

    if (isDocument) {
      window.scrollBy(dx, dy);
    } else {
      target.scrollBy(dx, dy);
      target.dispatchEvent(new WheelEvent('wheel', {
        deltaX: dx,
        deltaY: dy,
        bubbles: true,
        cancelable: true,
        view: window,
      }));
    }

    const afterX = isDocument ? window.scrollX : target.scrollLeft;
    const afterY = isDocument ? window.scrollY : target.scrollTop;
    return {
      success: afterX !== beforeX || afterY !== beforeY,
      moved: afterX !== beforeX || afterY !== beforeY,
      target: isDocument ? 'document' : getElementRef(target),
      scrollX: afterX,
      scrollY: afterY,
      maxScrollY: Math.max(0, target.scrollHeight - target.clientHeight),
    };
  }

  function collectImages(root = document) {
    const images = new Map();
    const addImage = (url, metadata = {}) => {
      if (!url) return;
      let absoluteUrl;
      try {
        absoluteUrl = new URL(url, window.location.href).href;
      } catch (_) {
        return;
      }
      if (!/^https?:/i.test(absoluteUrl)) return;
      const existing = images.get(absoluteUrl) || {};
      images.set(absoluteUrl, { ...existing, ...metadata, src: absoluteUrl });
    };

    const queryWithin = selector => {
      const matches = Array.from(root.querySelectorAll(selector));
      if (root instanceof Element && root.matches(selector)) matches.unshift(root);
      return matches;
    };

    queryWithin('img').forEach(img => {
      addImage(img.currentSrc || img.src || img.getAttribute('src') || img.dataset.src, {
        alt: img.alt || null,
        width: img.naturalWidth || null,
        height: img.naturalHeight || null,
        source: 'img',
      });
      const srcset = img.getAttribute('srcset') || img.dataset.srcset;
      if (srcset) {
        srcset.split(',').forEach(candidate => addImage(candidate.trim().split(/\s+/)[0], {
          alt: img.alt || null,
          source: 'srcset',
        }));
      }
    });

    queryWithin('source[srcset]').forEach(source => {
      source.srcset.split(',').forEach(candidate => addImage(candidate.trim().split(/\s+/)[0], {
        source: 'source-srcset',
      }));
    });

    queryWithin('*').forEach(element => {
      const backgroundImage = window.getComputedStyle(element).backgroundImage;
      if (!backgroundImage || backgroundImage === 'none') return;
      for (const match of backgroundImage.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
        addImage(match[1], { source: 'background-image' });
      }
    });

    return Array.from(images.values());
  }

  async function loadAndCollectImages(maxScrolls = 12, settleMs = 500, ref = null) {
    const collected = new Map();
    const root = ref ? getElementByRef(ref) : document;
    if (!root) return { success: false, error: 'Image scope element not found' };
    const remember = () => collectImages(root).forEach(image => collected.set(image.src, image));
    const target = findScrollTarget(ref);
    const isDocument = target === document.scrollingElement ||
      target === document.documentElement || target === document.body;

    remember();
    for (let step = 0; step < Math.max(0, maxScrolls); step += 1) {
      const before = isDocument ? window.scrollY : target.scrollTop;
      const amount = Math.max(300, Math.floor((isDocument ? window.innerHeight : target.clientHeight) * 0.8));
      if (isDocument) window.scrollBy(0, amount);
      else target.scrollBy(0, amount);
      await new Promise(resolve => setTimeout(resolve, Math.max(0, settleMs)));
      remember();
      const after = isDocument ? window.scrollY : target.scrollTop;
      if (after === before) break;
    }

    return {
      success: true,
      images: Array.from(collected.values()),
      count: collected.size,
      scrollTarget: isDocument ? 'document' : getElementRef(target),
    };
  }

  /**
   * Perform keyboard event
   */
  function performKeypress(ref, keys) {
    const element = getElementByRef(ref);
    if (!element) {
      return { success: false, error: 'Element not found' };
    }

    if (!isVisible(element)) {
      return { success: false, error: 'Element not visible' };
    }

    // Focus element
    element.focus();

    // Map key names to key codes
    const keyMap = {
      'Enter': { key: 'Enter', code: 'Enter', keyCode: 13 },
      'Tab': { key: 'Tab', code: 'Tab', keyCode: 9 },
      'Escape': { key: 'Escape', code: 'Escape', keyCode: 27 },
      'ArrowUp': { key: 'ArrowUp', code: 'ArrowUp', keyCode: 38 },
      'ArrowDown': { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40 },
      'ArrowLeft': { key: 'ArrowLeft', code: 'ArrowLeft', keyCode: 37 },
      'ArrowRight': { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
      'Backspace': { key: 'Backspace', code: 'Backspace', keyCode: 8 },
      'Delete': { key: 'Delete', code: 'Delete', keyCode: 46 },
      'Space': { key: ' ', code: 'Space', keyCode: 32 },
    };

    const keyInfo = keyMap[keys] || { key: keys, code: keys, keyCode: keys.charCodeAt(0) };

    // Dispatch keydown event
    const keydownEvent = new KeyboardEvent('keydown', {
      key: keyInfo.key,
      code: keyInfo.code,
      keyCode: keyInfo.keyCode,
      bubbles: true,
      cancelable: true,
    });
    element.dispatchEvent(keydownEvent);

    // Dispatch keypress event
    const keypressEvent = new KeyboardEvent('keypress', {
      key: keyInfo.key,
      code: keyInfo.code,
      keyCode: keyInfo.keyCode,
      bubbles: true,
      cancelable: true,
    });
    element.dispatchEvent(keypressEvent);

    // Dispatch keyup event
    const keyupEvent = new KeyboardEvent('keyup', {
      key: keyInfo.key,
      code: keyInfo.code,
      keyCode: keyInfo.keyCode,
      bubbles: true,
      cancelable: true,
    });
    element.dispatchEvent(keyupEvent);

    return { success: true, keypressed: keys };
  }

  /**
   * Wait for DOM element
   */
  async function waitForElement(selector, timeout = 5000) {
    return waitForCondition(() => {
      const element = document.querySelector(selector);
      return element !== null && isVisible(element);
    }, timeout);
  }

  /**
   * Wait for URL change
   */
  async function waitForUrlChange(currentUrl, timeout = 10000) {
    return waitForCondition(() => {
      return window.location.href !== currentUrl;
    }, timeout);
  }

  /**
   * Wait for DOM mutation
   */
  async function waitForMutation(selector, timeout = 5000) {
    return new Promise((resolve) => {
      const startTime = Date.now();
      let resolved = false;

      const observer = new MutationObserver((mutations) => {
        if (resolved) return;

        for (const mutation of mutations) {
          // Check if the mutation affects the target element
          if (selector) {
            const target = document.querySelector(selector);
            if (target) {
              resolved = true;
              observer.disconnect();
              resolve({ success: true, mutation: 'detected' });
              return;
            }
          } else {
            // Any mutation
            resolved = true;
            observer.disconnect();
            resolve({ success: true, mutation: 'detected' });
            return;
          }
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
      });

      // Timeout handler
      setTimeout(() => {
        if (!resolved) {
          observer.disconnect();
          resolve({ success: false, error: 'Timeout waiting for mutation' });
        }
      }, timeout);
    });
  }

  /**
   * Get current page state
   */
  function getPageState() {
    return {
      url: window.location.href,
      title: document.title,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
      readyState: document.readyState,
    };
  }

  /**
   * Validate element before operation
   */
  function validateElement(ref) {
    const element = getElementByRef(ref);
    if (!element) {
      return { valid: false, error: 'Element not found' };
    }

    if (!element.isConnected) {
      return { valid: false, error: 'Element no longer in DOM' };
    }

    if (!isVisible(element)) {
      return { valid: false, error: 'Element not visible' };
    }

    if (element.disabled) {
      return { valid: false, error: 'Element is disabled' };
    }

    return { valid: true, element };
  }

  /**
   * Wait for a condition to be met
   */
  function waitForCondition(condition, timeout = 5000) {
    const startTime = Date.now();

    return new Promise((resolve) => {
      const check = () => {
        if (condition()) {
          resolve({ success: true, condition: 'met' });
          return;
        }

        if (Date.now() - startTime > timeout) {
          resolve({ success: false, error: 'Timeout waiting for condition' });
          return;
        }

        requestAnimationFrame(check);
      };

      check();
    });
  }

  /**
   * Extract structured page data for content scraping.
   */
  function extractPageData() {
    const links = [];
    document.querySelectorAll('a').forEach(a => {
      const href = a.href;
      const text = (a.textContent || '').trim();
      if (href && !href.startsWith('javascript:')) {
        links.push({
          href: href,
          text: text.substring(0, 500),
          title: a.getAttribute('title') || null,
        });
      }
    });

    const images = collectImages();

    const headings = [];
    document.querySelectorAll('h1, h2, h3, h4').forEach(h => {
      headings.push({
        tag: h.tagName.toLowerCase(),
        text: (h.textContent || '').trim().substring(0, 1000),
      });
    });

    const paragraphs = [];
    document.querySelectorAll('p, div[role="article"], article, section').forEach(el => {
      const text = (el.textContent || '').trim();
      if (text.length > 20 && text.length < 5000) {
        paragraphs.push(text.substring(0, 2000));
      }
    });

    return {
      url: window.location.href,
      title: document.title,
      documentId: DOCUMENT_ID,
      links: links,
      images: images,
      headings: headings,
      paragraphs: paragraphs,
    };
  }

  function extractElementText(ref, maxChars = 20000) {
    const element = getElementByRef(ref);
    if (!element) return { success: false, error: 'Text element not found' };
    const limit = Math.min(Math.max(Number(maxChars) || 20000, 1), 200000);
    const fullText = (element.innerText || element.textContent || '').trim();
    return {
      success: true,
      ref,
      documentId: DOCUMENT_ID,
      text: fullText.slice(0, limit),
      length: fullText.length,
      returnedLength: Math.min(fullText.length, limit),
      truncated: fullText.length > limit,
    };
  }

  function classifyMediaUrl(url) {
    if (!url) return { urlType: 'missing', downloadable: false };
    if (url.startsWith('blob:')) return { urlType: 'blob', downloadable: false };
    if (/\.m3u8(?:$|\?)/i.test(url)) return { urlType: 'hls', downloadable: false };
    if (/\.mpd(?:$|\?)/i.test(url)) return { urlType: 'dash', downloadable: false };
    if (/^https?:/i.test(url)) return { urlType: 'direct', downloadable: true };
    return { urlType: 'unsupported', downloadable: false };
  }

  function collectMedia(root = document) {
    const media = new Map();
    const addMedia = (type, url, metadata = {}) => {
      if (!url) return;
      let resolved = url;
      if (!url.startsWith('blob:')) {
        try {
          resolved = new URL(url, window.location.href).href;
        } catch (_) {
          return;
        }
      }
      const key = `${type}:${resolved}`;
      const classification = classifyMediaUrl(resolved);
      media.set(key, {
        ...(media.get(key) || {}),
        type,
        url: resolved,
        ...classification,
        ...metadata,
      });
    };
    const queryWithin = selector => {
      const matches = Array.from(root.querySelectorAll(selector));
      if (root instanceof Element && root.matches(selector)) matches.unshift(root);
      return matches;
    };

    queryWithin('video, audio').forEach(element => {
      const type = element.tagName.toLowerCase();
      const common = {
        source: 'media-element',
        duration: Number.isFinite(element.duration) ? element.duration : null,
        width: element.videoWidth || null,
        height: element.videoHeight || null,
        poster: element.poster || null,
      };
      addMedia(type, element.currentSrc || element.src, common);
      element.querySelectorAll('source[src]').forEach(source => {
        addMedia(type, source.src, { ...common, source: 'source-element', mimeType: source.type || null });
      });
    });

    queryWithin('script[type="application/ld+json"]').forEach(script => {
      try {
        const walk = value => {
          if (Array.isArray(value)) return value.forEach(walk);
          if (!value || typeof value !== 'object') return;
          const schemaType = value['@type'];
          if (schemaType === 'VideoObject' || schemaType === 'AudioObject') {
            const type = schemaType === 'VideoObject' ? 'video' : 'audio';
            addMedia(type, value.contentUrl || value.embedUrl, {
              source: 'json-ld',
              name: value.name || null,
              durationText: value.duration || null,
              thumbnailUrl: value.thumbnailUrl || null,
              uploadDate: value.uploadDate || null,
            });
          }
          Object.values(value).forEach(walk);
        };
        walk(JSON.parse(script.textContent));
      } catch (_) {
        // Ignore malformed third-party structured data.
      }
    });
    return Array.from(media.values());
  }

  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log("Content script received:", request);

    const { action, params } = request;

    switch (action) {
      case 'ping':
        sendResponse({ pong: true, documentId: DOCUMENT_ID });
        break;

      case 'snapshot':
        const snapshot = buildSnapshot(params?.scope || 'viewport');
        sendResponse(snapshot);
        break;

      case 'click':
        const clickResult = performClick(params?.ref);
        sendResponse(clickResult);
        break;

      case 'fill':
        const fillResult = performFill(params?.ref, params?.value);
        sendResponse(fillResult);
        break;

      case 'scroll':
        const scrollResult = performScroll(params?.dx, params?.dy, params?.ref);
        sendResponse(scrollResult);
        break;

      case 'images':
        const imageRoot = params?.ref ? getElementByRef(params.ref) : document;
        if (!imageRoot) {
          sendResponse({ success: false, error: 'Image scope element not found' });
          break;
        }
        if (params?.load) {
          loadAndCollectImages(params?.maxScrolls, params?.settleMs, params?.ref)
            .then(result => sendResponse(result));
        } else {
          const images = collectImages(imageRoot);
          sendResponse({ success: true, images, count: images.length });
        }
        break;

      case 'screenshot':
        captureScreenshot(params?.scope || 'viewport', params?.ref, params?.rect)
          .then(result => sendResponse(result));
        break;

      case 'checkSensitivity':
        sendResponse(checkPageSensitivity());
        break;
      case 'keypress':
        const keyResult = performKeypress(params?.ref, params?.keys);
        sendResponse(keyResult);
        break;

      case 'wait':
        // Wait for element or condition
        if (params?.selector) {
          waitForElement(params.selector, params?.timeout || 5000)
            .then(result => sendResponse(result));
        } else if (params?.url) {
          waitForUrlChange(params.url, params?.timeout || 10000)
            .then(result => sendResponse(result));
        } else if (params?.mutation) {
          waitForMutation(params?.selector, params?.timeout || 5000)
            .then(result => sendResponse(result));
        } else {
          sendResponse({ error: 'No wait condition specified' });
        }
        break;

      case 'pageState':
        sendResponse(getPageState());
        break;

      case 'validate':
        const validationResult = validateElement(params?.ref);
        sendResponse(validationResult);
        break;

      case 'extract':
        sendResponse(extractPageData());
        break;

      case 'text':
        sendResponse(extractElementText(params?.ref, params?.maxChars));
        break;

      case 'media':
        const mediaRoot = params?.ref ? getElementByRef(params.ref) : document;
        if (!mediaRoot) {
          sendResponse({ success: false, error: 'Media scope element not found' });
          break;
        }
        const media = collectMedia(mediaRoot);
        sendResponse({ success: true, media, count: media.length });
        break;

      default:
        sendResponse({ error: `Unknown action: ${action}` });
    }

    // Return true to indicate async response
    return true;
  });

  console.log("Chrome Agent content script injected, documentId:", DOCUMENT_ID);
})();
