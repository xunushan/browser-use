/**
 * Chrome Agent Extension - Background Service Worker (Enhanced)
 *
 * Manages connection to Native Messaging Host and handles
 * communication with the Chrome Agent Daemon.
 * Supports on-demand content script injection and dynamic registration.
 */

// Connection state
let nativePort = null;
let reconnectAttempt = 0;
let reconnectTimer = null;
let isConnected = false;
let sessionId = null;

// Reconnect configuration
const RECONNECT_DELAYS = [0, 1000, 2000, 4000, 8000, 15000, 30000];
const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS.length;

// Content script injection state
const injectedTabs = new Map();
const registeredScripts = new Map();

/**
 * Connect to the Native Messaging Host
 */
function connectDaemon() {
  if (nativePort) {
    console.log("Already connected to daemon");
    return;
  }

  console.log("Connecting to Chrome Agent Daemon...");

  try {
    nativePort = chrome.runtime.connectNative("com.browseruse.chrome_agent");

    nativePort.onMessage.addListener(handleNativeMessage);
    nativePort.onDisconnect.addListener(handleDisconnect);

    reconnectAttempt = 0;
    isConnected = true;
    console.log("Connected to Chrome Agent Daemon");

    // Send registration message
    sendToDaemon({
      jsonrpc: "2.0",
      method: "session.register",
      params: {
        extensionId: chrome.runtime.id,
        protocolVersion: "1.0",
        browserVersion: navigator.userAgent,
      },
      id: `register-${Date.now()}`,
    });

  } catch (error) {
    console.error("Failed to connect to daemon:", error);
    scheduleReconnect();
  }
}

/**
 * Send message to daemon
 */
function sendToDaemon(message) {
  if (nativePort) {
    nativePort.postMessage(message);
  }
}

/**
 * Handle messages from Native Host
 */
function handleNativeMessage(message) {
  console.log("Received from daemon:", message);

  if (message.method) {
    handleDaemonCommand(message);
  } else if (message.result) {
    handleDaemonResponse(message);
  } else if (message.error) {
    handleDaemonError(message);
  }
}

/**
 * Handle commands from daemon
 */
async function handleDaemonCommand(message) {
  const { method, params, id } = message;

  try {
    let result;

    switch (method) {
      case "tabs.list":
        result = await listTabs(params);
        break;
      case "tabs.open":
        result = await openTab(params);
        break;
      case "tabs.claim":
        result = await claimTab(params);
        break;
      case "page.snapshot":
        result = await pageSnapshot(params);
        break;
      case "page.click":
        result = await pageClick(params);
        break;
      case "page.fill":
        result = await pageFill(params);
        break;
      case "page.scroll":
        result = await pageScroll(params);
        break;
      case "page.keypress":
        result = await pageKeypress(params);
        break;
      case "page.wait":
        result = await pageWait(params);
        break;
      case "page.validate":
        result = await pageValidate(params);
        break;
      case "page.inject":
        result = await injectContentScript(params);
        break;
      case "page.register":
        result = await registerContentScript(params);
        break;
      case "page.unregister":
        result = await unregisterContentScript(params);
        break;
      default:
        sendError(id, -32601, `Method not found: ${method}`);
        return;
    }

    sendResponse(id, result);
  } catch (error) {
    console.error("Error handling command:", error);
    sendError(id, -32603, `Internal error: ${error.message}`);
  }
}

/**
 * Handle responses from daemon
 */
function handleDaemonResponse(message) {
  console.log("Daemon response:", message);
}

/**
 * Handle errors from daemon
 */
function handleDaemonError(message) {
  console.error("Daemon error:", message.error);
}

/**
 * Handle disconnect from Native Host
 */
function handleDisconnect() {
  console.log("Disconnected from daemon");
  isConnected = false;
  nativePort = null;
  scheduleReconnect();
}

/**
 * Schedule reconnect with exponential backoff
 */
function scheduleReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
  }

  if (reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
    console.error("Max reconnect attempts reached");
    return;
  }

  const delay = RECONNECT_DELAYS[reconnectAttempt];
  console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempt + 1})`);

  reconnectTimer = setTimeout(() => {
    reconnectAttempt++;
    connectDaemon();
  }, delay);
}

/**
 * Send response to daemon
 */
function sendResponse(id, result) {
  if (nativePort) {
    nativePort.postMessage({
      jsonrpc: "2.0",
      id: id,
      result: result,
    });
  }
}

/**
 * Send error to daemon
 */
function sendError(id, code, message) {
  if (nativePort) {
    nativePort.postMessage({
      jsonrpc: "2.0",
      id: id,
      error: {
        code: code,
        message: message,
      },
    });
  }
}

// Tab management functions
async function listTabs(params) {
  const tabs = await chrome.tabs.query({});
  return tabs.map(tab => ({
    id: tab.id,
    url: tab.url,
    title: tab.title,
    active: tab.active,
    windowId: tab.windowId,
  }));
}

async function openTab(params) {
  const { url } = params;
  const tab = await chrome.tabs.create({ url });
  return { tabId: tab.id, url: tab.url };
}

async function claimTab(params) {
  const { tabId } = params;
  const tab = await chrome.tabs.get(tabId);
  return { tabId: tab.id, url: tab.url, title: tab.title };
}

// Content Script injection functions
async function injectContentScript(params) {
  const { tabId } = params;

  try {
    // Check if already injected
    if (injectedTabs.has(tabId)) {
      return { success: true, injected: true, cached: true };
    }

    // Inject content script
    await chrome.scripting.executeScript({
      target: { tabId: tabId, allFrames: false },
      files: ["content_scripts/content.js"],
      world: "ISOLATED",
    });

    // Mark as injected
    injectedTabs.set(tabId, {
      injectedAt: Date.now(),
      documentId: null, // Will be updated after first snapshot
    });

    return { success: true, injected: true };
  } catch (error) {
    console.error("Error injecting content script:", error);
    return { success: false, error: error.message };
  }
}

async function registerContentScript(params) {
  const { tabId, urlPattern } = params;
  const scriptId = `agent-session-${tabId}-${Date.now()}`;

  try {
    await chrome.scripting.registerContentScripts([
      {
        id: scriptId,
        matches: [urlPattern || "<all_urls>"],
        js: ["content_scripts/content.js"],
        runAt: "document_start",
        world: "ISOLATED",
        persistAcrossSessions: false,
      },
    ]);

    registeredScripts.set(scriptId, {
      tabId,
      urlPattern,
      registeredAt: Date.now(),
    });

    return { success: true, scriptId };
  } catch (error) {
    console.error("Error registering content script:", error);
    return { success: false, error: error.message };
  }
}

async function unregisterContentScript(params) {
  const { scriptId } = params;

  try {
    await chrome.scripting.unregisterContentScripts({
      ids: [scriptId],
    });

    registeredScripts.delete(scriptId);

    return { success: true };
  } catch (error) {
    console.error("Error unregistering content script:", error);
    return { success: false, error: error.message };
  }
}

// Page interaction functions
async function pageSnapshot(params) {
  const { tabId, scope } = params;

  // Ensure content script is injected
  const injectResult = await injectContentScript({ tabId });
  if (!injectResult.success) {
    return injectResult;
  }

  // Send message to content script
  const response = await chrome.tabs.sendMessage(tabId, {
    action: "snapshot",
    params: { scope: scope || "viewport" },
  });

  // Update document ID tracking
  if (response.documentId) {
    const tabInfo = injectedTabs.get(tabId);
    if (tabInfo) {
      tabInfo.documentId = response.documentId;
    }
  }

  return response;
}

async function pageClick(params) {
  const { tabId, ref } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "click",
    params: { ref },
  });

  return response;
}

async function pageFill(params) {
  const { tabId, ref, value } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "fill",
    params: { ref, value },
  });

  return response;
}

async function pageScroll(params) {
  const { tabId } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "scroll",
    params: params,
  });

  return response;
}

async function pageScreenshot(params) {
  const { tabId, scope } = params;

  // Capture screenshot using chrome.tabs.captureVisibleTab
  const tab = await chrome.tabs.get(tabId);
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "png",
  });

  return {
    screenshot: dataUrl,
    scope: scope || "viewport",
  };
}

async function pageKeypress(params) {
  const { tabId, ref, keys } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "keypress",
    params: { ref, keys },
  });

  return response;
}

async function pageWait(params) {
  const { tabId } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "wait",
    params: params,
  });

  return response;
}

async function pageValidate(params) {
  const { tabId, ref } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "validate",
    params: { ref },
  });

  return response;
}

// Listen for tab updates to track navigation
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    // Tab has finished loading, update injection status
    if (injectedTabs.has(tabId)) {
      injectedTabs.delete(tabId);
    }
  }
});

// Listen for tab removal
chrome.tabs.onRemoved.addListener((tabId) => {
  if (injectedTabs.has(tabId)) {
    injectedTabs.delete(tabId);
  }
});

// Initialize connection on startup
chrome.runtime.onStartup.addListener(connectDaemon);
chrome.runtime.onInstalled.addListener(connectDaemon);

// Also try to connect immediately
connectDaemon();
