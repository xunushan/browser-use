/**
 * Chrome Agent Extension - Background Service Worker
 *
 * Manages connection to Native Messaging Host and handles
 * communication with the Chrome Agent Daemon.
 */

// Connection state
let nativePort = null;
let reconnectAttempt = 0;
let reconnectTimer = null;
let isConnected = false;

// Reconnect configuration
const RECONNECT_DELAYS = [0, 1000, 2000, 4000, 8000, 15000, 30000];
const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS.length;

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
    nativePort.postMessage({
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
 * Handle messages from Native Host
 */
function handleNativeMessage(message) {
  console.log("Received from daemon:", message);

  // Handle different message types
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
      case "page.screenshot":
        result = await pageScreenshot(params);
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
  // Responses are typically handled by the requester
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

  // Schedule reconnect
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

// Page interaction functions
async function pageSnapshot(params) {
  const { tabId } = params;

  // Inject content script if needed
  await ensureContentScript(tabId);

  // Send message to content script
  const response = await chrome.tabs.sendMessage(tabId, {
    action: "snapshot",
    params: params,
  });

  return response;
}

async function pageClick(params) {
  const { tabId, ref } = params;

  await ensureContentScript(tabId);

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "click",
    params: params,
  });

  return response;
}

async function pageFill(params) {
  const { tabId, ref, value } = params;

  await ensureContentScript(tabId);

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "fill",
    params: params,
  });

  return response;
}

async function pageScroll(params) {
  const { tabId } = params;

  await ensureContentScript(tabId);

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "scroll",
    params: params,
  });

  return response;
}

async function pageScreenshot(params) {
  const { tabId, scope } = params;

  // Capture screenshot using chrome.tabs.captureVisibleTab
  const dataUrl = await chrome.tabs.captureVisibleTab(tabId.windowId, {
    format: "png",
  });

  return {
    screenshot: dataUrl,
    scope: scope || "viewport",
  };
}

/**
 * Ensure content script is injected in tab
 */
async function ensureContentScript(tabId) {
  try {
    // Try to send a ping message
    await chrome.tabs.sendMessage(tabId, { action: "ping" });
  } catch (error) {
    // Content script not injected, inject it
    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ["content_scripts/content.js"],
    });
  }
}

// Initialize connection on startup
chrome.runtime.onStartup.addListener(connectDaemon);
chrome.runtime.onInstalled.addListener(connectDaemon);

// Also try to connect immediately
connectDaemon();
