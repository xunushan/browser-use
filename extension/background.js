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

// Reconnect configuration - keep retrying indefinitely with capped delay
const RECONNECT_DELAYS = [0, 1000, 2000, 4000, 8000, 15000, 30000];
const MAX_RECONNECT_DELAY = 30000;

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
      case "tabs.navigate":
        result = await navigateTab(params);
        break;
      case "tabs.claim":
        result = await claimTab(params);
        break;
      case "tabs.activate":
        result = await activateTab(params);
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
      case "page.screenshot":
        result = await pageScreenshot(params);
        break;
      case "page.extract":
        result = await pageExtract(params);
        break;
      case "page.text":
        result = await pageText(params);
        break;
      case "page.images":
        result = await pageImages(params);
        break;
      case "page.downloadImages":
        result = await pageDownloadImages(params);
        break;
      case "page.media":
        result = await pageMedia(params);
        break;
      case "page.downloadMedia":
        result = await pageDownloadMedia(params);
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
  if (message.result?.status === "registered") {
    reconnectAttempt = 0;
    sessionId = message.result.sessionId || null;
  }
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
 * Schedule reconnect with exponential backoff, retry forever
 */
function scheduleReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
  }

  const delay = reconnectAttempt < RECONNECT_DELAYS.length
    ? RECONNECT_DELAYS[reconnectAttempt]
    : MAX_RECONNECT_DELAY;
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
  const domain = params?.domain?.toLowerCase();
  const selected = domain
    ? tabs.filter(tab => {
        try { return new URL(tab.url).hostname.toLowerCase().endsWith(domain); }
        catch { return false; }
      })
    : tabs;
  return {
    tabs: selected.map(tab => ({
      id: tab.id,
      url: tab.url,
      title: tab.title,
      active: tab.active,
      windowId: tab.windowId,
    })),
  };
}

async function openTab(params) {
  const { url } = params;
  assertWebUrl(url);
  const tab = await chrome.tabs.create({ url });
  return { tabId: tab.id, url: tab.url };
}

async function navigateTab(params) {
  const { tabId, url } = params;
  assertWebUrl(url);
  const tab = await chrome.tabs.update(tabId, { url });
  return { tabId: tab.id, url };
}

function assertWebUrl(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('Only HTTP(S) navigation is allowed');
  }
}

async function claimTab(params) {
  const { tabId } = params;
  const tab = await chrome.tabs.get(tabId);
  return { tabId: tab.id, url: tab.url, title: tab.title };
}

async function activateTab(params) {
  const { tabId } = params;
  const tab = await chrome.tabs.get(tabId);
  await chrome.windows.update(tab.windowId, { focused: true });
  const activated = await chrome.tabs.update(tabId, { active: true });
  return {
    tabId: activated.id,
    windowId: activated.windowId,
    active: activated.active,
    url: activated.url,
    title: activated.title,
  };
}

// Content Script injection functions
async function injectContentScript(params) {
  const { tabId } = params;

  try {
    // Check if already injected
    if (injectedTabs.has(tabId)) {
      return { success: true, injected: true, cached: true };
    }

    // Host permissions can only be granted from a user gesture. The extension
    // popup owns that flow; command handling only verifies and uses access.
    const tab = await chrome.tabs.get(tabId);
    const tabUrl = new URL(tab.url);
    const hostPattern = `${tabUrl.protocol}//${tabUrl.hostname}/*`;
    const hasAccess = await chrome.permissions.contains({ origins: [hostPattern] });
    if (!hasAccess) {
      return {
        success: false,
        error: `Site access not granted for ${tabUrl.hostname}. Open the Chrome Agent popup on this tab and grant access.`,
      };
    }

    // Inject content script
    await chrome.scripting.executeScript({
      target: { tabId: tabId, allFrames: false },
      files: ["content.js"],
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

async function pageImages(params) {
  const { tabId } = params;
  await injectContentScript({ tabId });
  return chrome.tabs.sendMessage(tabId, {
    action: "images",
    params,
  });
}

async function pageText(params) {
  const { tabId } = params;
  await injectContentScript({ tabId });
  return chrome.tabs.sendMessage(tabId, {
    action: "text",
    params,
  });
}

function safeDownloadName(prefix, index, url, defaultExtension = ".jpg") {
  let extension = defaultExtension;
  try {
    const pathname = new URL(url).pathname;
    const match = pathname.match(/\.(avif|gif|jpe?g|png|webp|m4a|m4v|mov|mp3|mp4|ogg|wav|webm)$/i);
    if (match) extension = `.${match[1].toLowerCase()}`;
  } catch (_) {
    // Keep the generic image extension for opaque CDN URLs.
  }
  const safePrefix = (prefix || "image").replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 80);
  return `chrome-agent/${safePrefix}-${String(index + 1).padStart(3, "0")}${extension}`;
}

async function waitForDownload(downloadId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const matches = await chrome.downloads.search({ id: downloadId });
    const item = matches[0];
    if (item?.state === "complete") return { id: downloadId, state: item.state, filename: item.filename };
    if (item?.state === "interrupted") {
      return { id: downloadId, state: item.state, error: item.error || "interrupted" };
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  return { id: downloadId, state: "in_progress", timedOut: true };
}

async function pageDownloadImages(params) {
  const discovered = await pageImages(params);
  const limit = Math.min(Math.max(Number(params.limit) || 20, 1), 100);
  const discoveredUrls = discovered.images
    .map(image => image.src)
    .filter(url => /^https?:\/\//i.test(url));
  const requestedUrls = Array.isArray(params.urls) && params.urls.length > 0
    ? params.urls
    : discoveredUrls;
  const allowed = new Set(discoveredUrls);
  const urls = [...new Set(requestedUrls)]
    .filter(url => allowed.has(url))
    .slice(0, limit);
  const started = [];

  for (let index = 0; index < urls.length; index += 1) {
    try {
      const id = await chrome.downloads.download({
        url: urls[index],
        filename: safeDownloadName(params.prefix, index, urls[index]),
        conflictAction: "uniquify",
        saveAs: false,
      });
      started.push({ id, url: urls[index] });
    } catch (error) {
      started.push({ url: urls[index], state: "failed", error: error.message });
    }
  }

  const timeoutMs = Math.min(Math.max(Number(params.timeoutMs) || 30000, 1000), 120000);
  const completed = await Promise.all(started.map(item => item.id
    ? waitForDownload(item.id, timeoutMs).then(status => ({ ...item, ...status }))
    : item));
  return {
    success: completed.some(item => item.state === "complete"),
    discovered: discovered.count,
    selected: Array.isArray(params.urls) ? params.urls.length : discoveredUrls.length,
    requested: urls.length,
    downloads: completed,
  };
}

async function pageMedia(params) {
  const { tabId } = params;
  await injectContentScript({ tabId });
  return chrome.tabs.sendMessage(tabId, { action: "media", params });
}

async function pageDownloadMedia(params) {
  const discovered = await pageMedia(params);
  const limit = Math.min(Math.max(Number(params.limit) || 10, 1), 50);
  const candidates = discovered.media
    .filter(item => item.downloadable && /^https?:\/\//i.test(item.url))
    .slice(0, limit);
  const started = [];

  for (let index = 0; index < candidates.length; index += 1) {
    const item = candidates[index];
    try {
      const id = await chrome.downloads.download({
        url: item.url,
        filename: safeDownloadName(
          params.prefix || item.type || "media",
          index,
          item.url,
          item.type === "audio" ? ".mp3" : ".mp4",
        ),
        conflictAction: "uniquify",
        saveAs: false,
      });
      started.push({ id, url: item.url, type: item.type });
    } catch (error) {
      started.push({ url: item.url, type: item.type, state: "failed", error: error.message });
    }
  }

  const timeoutMs = Math.min(Math.max(Number(params.timeoutMs) || 120000, 1000), 600000);
  const completed = await Promise.all(started.map(item => item.id
    ? waitForDownload(item.id, timeoutMs).then(status => ({ ...item, ...status }))
    : item));
  return {
    success: completed.some(item => item.state === "complete"),
    discovered: discovered.count,
    downloadable: candidates.length,
    downloads: completed,
    unsupported: discovered.media.filter(item => !item.downloadable),
  };
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

async function pageExtract(params) {
  const { tabId } = params;

  await injectContentScript({ tabId });

  const response = await chrome.tabs.sendMessage(tabId, {
    action: "extract",
    params: {},
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

// Keep service worker alive in MV3
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm.name === "keep-alive") {
    console.log("Keep-alive alarm");
    if (!nativePort) {
      connectDaemon();
    }
  }
});

// Initialize connection on startup
chrome.runtime.onStartup.addListener(connectDaemon);
chrome.runtime.onInstalled.addListener(connectDaemon);
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms?.create("keep-alive", { periodInMinutes: 0.5 });
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms?.create("keep-alive", { periodInMinutes: 0.5 });
});

// Also try to connect immediately
connectDaemon();
chrome.alarms?.create("keep-alive", { periodInMinutes: 0.5 });
