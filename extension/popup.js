const site = document.querySelector('#site');
const button = document.querySelector('#grant');
const status = document.querySelector('#status');

async function currentOriginPattern() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return null;
  const url = new URL(tab.url);
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  site.textContent = url.hostname;
  return `${url.protocol}//${url.hostname}/*`;
}

currentOriginPattern().then(async pattern => {
  if (!pattern) {
    site.textContent = '此页面不支持授权';
    return;
  }
  if (await chrome.permissions.contains({ origins: [pattern] })) {
    status.textContent = '当前网站已授权';
    return;
  }
  button.disabled = false;
  button.addEventListener('click', async () => {
    const granted = await chrome.permissions.request({ origins: [pattern] });
    status.textContent = granted ? '授权成功，可以交给智能体操作' : '未授权';
    button.disabled = granted;
  });
});
