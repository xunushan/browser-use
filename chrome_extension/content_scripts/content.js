/**
 * Chrome Agent Content Script
 *
 * Injected into web pages to provide DOM interaction capabilities.
 */

(function() {
  'use strict';

  // Prevent duplicate injection
  if (window.__CHROME_AGENT_INJECTED__) {
    return;
  }
  window.__CHROME_AGENT_INJECTED__ = true;

  // Element reference management
  let elementCounter = 1;
  const elementToRef = new WeakMap();
  const refToElement = new Map();

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
   * Check if element is interactive
   */
  function isInteractive(element) {
    if (!element) return false;

    const interactiveTags = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'];
    const interactiveRoles = ['button', 'link', 'checkbox', 'radio', 'textbox', 'combobox'];

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

    return false;
  }

  /**
   * Get element information
   */
  function getElementInfo(element) {
    if (!element) return null;

    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);

    return {
      ref: getElementRef(element),
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute('role') || null,
      name: element.getAttribute('name') || null,
      id: element.id || null,
      className: element.className || null,
      text: element.textContent?.substring(0, 200) || null,
      placeholder: element.getAttribute('placeholder') || null,
      type: element.type || null,
      visible: isVisible(element),
      enabled: !element.disabled,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      interactive: isInteractive(element),
    };
  }

  /**
   * Build DOM snapshot
   */
  function buildSnapshot(scope = 'viewport') {
    const elements = [];
    const allElements = document.querySelectorAll('*');

    allElements.forEach(element => {
      // Skip invisible elements in viewport mode
      if (scope === 'viewport' && !isVisible(element)) {
        return;
      }

      // Skip non-interactive elements unless they have text content
      if (!isInteractive(element) && !element.textContent?.trim()) {
        return;
      }

      const info = getElementInfo(element);
      if (info) {
        elements.push(info);
      }
    });

    return {
      documentId: `doc-${Date.now()}`,
      url: window.location.href,
      title: document.title,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      },
      elements: elements.slice(0, 500), // Limit to 500 elements
      timestamp: new Date().toISOString(),
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

  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log("Content script received:", request);

    const { action, params } = request;

    switch (action) {
      case 'ping':
        sendResponse({ pong: true });
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

      default:
        sendResponse({ error: `Unknown action: ${action}` });
    }

    // Return true to indicate async response
    return true;
  });

  console.log("Chrome Agent content script injected");
})();
