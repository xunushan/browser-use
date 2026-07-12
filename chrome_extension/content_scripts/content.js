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

  /**
   * Check if element is visible
   */
  function isVisible(element) {
    if (!element) return false;

    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return false;
    }

    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  /**
   * Check if element is in viewport
   */
  function isInViewport(element) {
    if (!element) return false;

    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= window.innerHeight &&
      rect.right <= window.innerWidth
    );
  }

  /**
   * Check if element is interactive
   */
  function isInteractive(element) {
    if (!element) return false;

    const interactiveTags = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA', 'DETAILS', 'SUMMARY'];
    const interactiveRoles = [
      'button', 'link', 'checkbox', 'radio', 'switch', 'textbox',
      'combobox', 'listbox', 'option', 'menuitem', 'slider',
      'spinbutton', 'searchbox', 'tab'
    ];

    if (interactiveTags.includes(element.tagName)) {
      return true;
    }

    const role = element.getAttribute('role');
    if (role && interactiveRoles.includes(role)) {
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

    const rect = element.getBoundingClientRect();
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
        focusable: element.tabIndex >= 0 || interactiveTags.includes(element.tagName),
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
   * Perform click on element
   */
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
  function performScroll(dx = 0, dy = 0) {
    window.scrollBy(dx, dy);
    return {
      success: true,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
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
        const scrollResult = performScroll(params?.dx, params?.dy);
        sendResponse(scrollResult);
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

      default:
        sendResponse({ error: `Unknown action: ${action}` });
    }

    // Return true to indicate async response
    return true;
  });

  console.log("Chrome Agent content script injected, documentId:", DOCUMENT_ID);
})();
