const roomsRoot = document.querySelector('#rooms');
const gatewayBadge = document.querySelector('#gateway');
const updatedLabel = document.querySelector('#updated');
const toast = document.querySelector('#message');
const allLightsOffButton = document.querySelector('#all-lights-off');
const allLightsOnButton = document.querySelector('#all-lights-on');
let refreshTimer;
let toastTimer;
let statusRequest = null;
let allLightsOffInFlight = false;
let allLightsOnInFlight = false;
let lastBulkOperationId = '';
let lastBulkSentCount = -1;
let lastFinishedBulkOperationId = '';
let lastRendered = '';
let hasInitialRoomExpansion = false;
const expandedRooms = new Set();

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function stateDescription(device) {
  if (device.pending) return 'waiting for confirmation';
  if (!device.state || device.state === 'unknown') return 'status unknown';
  if (device.stale) return 'status stale';
  return ({on:'on', off:'off', moving_open:'opening', moving_closed:'closing', stopped:'stopped', unknown:'status unknown'})[device.state] || 'status unknown';
}

function deviceIcon(device, statusClass) {
  const name = `${device.name}, ${stateDescription(device)}`;
  const icon = device.kind === 'shade'
    ? '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 3.5h16v17H4zM4 8h16M4 12.5h16M4 17h16M12 3.5v17"/></svg>'
    : '<svg viewBox="0 0 24 24" focusable="false"><path d="M9 18h6m-5 3h4m-6-6.4a7 7 0 1 1 8 0c-.8.6-1 1.4-1 2.4h-6c0-1-.2-1.8-1-2.4Z"/></svg>';
  return `<span class="device-symbol ${device.kind === 'shade' ? 'shade-symbol' : 'light-symbol'} ${statusClass}" role="img" aria-label="${escapeHtml(name)}">${icon}</span>`;
}

function deviceCard(device) {
  const state = device.state || 'unknown';
  const isOn = state === 'on';
  let statusClass = 'status-unknown';
  if (device.pending) statusClass = 'status-pending';
  else if (state === 'unknown') statusClass = 'status-unknown';
  else if (device.stale) statusClass = 'status-stale';
  else if (isOn) statusClass = 'status-on';
  else if (state === 'off') statusClass = 'status-off';
  else if (state === 'moving_open') statusClass = 'status-moving-open';
  else if (state === 'moving_closed') statusClass = 'status-moving-closed';
  else if (state === 'stopped') statusClass = 'status-stopped';

  let controls;
  if (device.kind === 'shade') {
    controls = `<button class="control-button shade" aria-label="Open ${escapeHtml(device.name)}" data-action="open" data-id="${device.id}">↑</button>
      <button class="control-button shade" aria-label="Stop ${escapeHtml(device.name)}" data-action="stop" data-id="${device.id}">■</button>
      <button class="control-button shade" aria-label="Close ${escapeHtml(device.name)}" data-action="close" data-id="${device.id}">↓</button>`;
  } else {
    const nextAction = isOn ? 'off' : 'on';
    const stateKnown = (state === 'on' || state === 'off') && !device.stale;
    const toggleLabel = device.pending
      ? `Waiting for confirmation for ${device.name}`
      : `Turn ${nextAction} ${device.name}${stateKnown ? '' : `; ${device.stale ? 'last status is stale' : 'current state unknown'}`}`;
    const toggleStateClass = state === 'unknown' ? 'status-unknown' : device.stale ? 'status-stale' : '';
    const toggle = `<button class="light-toggle ${isOn && !device.stale ? 'is-on' : ''} ${toggleStateClass}" aria-label="${escapeHtml(toggleLabel)}" ${stateKnown ? `aria-pressed="${isOn}"` : ''} data-action="toggle" data-next-action="${nextAction}" data-id="${device.id}" ${device.pending ? 'disabled' : ''}><span class="toggle-track"><span class="toggle-thumb"></span></span></button>`;
    if (device.kind === 'dimmer') {
      const value = device.brightness ?? 50;
      controls = `${toggle}<input class="brightness-range" type="range" min="0" max="100" step="10" value="${value}" aria-label="${escapeHtml(device.name)} brightness" data-action="brightness" data-id="${device.id}">`;
    } else {
      controls = toggle;
    }
  }

  return `<article class="device-row ${device.pending ? 'pending' : ''}" data-device="${device.id}">
    ${deviceIcon(device, statusClass)}
    <div class="device-info"><div class="device-name">${escapeHtml(device.name)}</div>${device.pending ? '<div class="device-feedback">Waiting for confirmation</div>' : ''}</div>
    <div class="device-actions">${controls}</div>
  </article>`;
}

function render(data) {
  gatewayBadge.className = `connection ${data.connected ? 'online' : 'offline'}`;
  gatewayBadge.querySelector('span').textContent = data.connected ? 'Gateway online' : 'Gateway offline';
  const rooms = data.rooms || [];
  const lightCommandPending = rooms.some((room) => room.devices.some((device) =>
    (device.kind === 'light' || device.kind === 'dimmer') && device.pending));
  const bulkOperation = data.bulk_lights_on;
  const bulkOnActive = bulkOperation && ['dispatching', 'confirming'].includes(bulkOperation.status);
  const lightActionsBusy = allLightsOffInFlight || allLightsOnInFlight || lightCommandPending || bulkOnActive;
  allLightsOffButton.disabled = !data.connected || lightActionsBusy;
  allLightsOnButton.disabled = !data.connected || lightActionsBusy;
  allLightsOffButton.setAttribute('aria-busy', String(lightActionsBusy));
  allLightsOnButton.setAttribute('aria-busy', String(lightActionsBusy));
  updateBulkLightsOnNotice(bulkOperation);
  if (!rooms.length) {
    roomsRoot.innerHTML = '<div class="loading-card">No devices configured yet. Open Setup to add rooms and devices.</div>';
  } else {
    const snapshot = JSON.stringify({connected:data.connected,rooms});
    if (snapshot === lastRendered) return;
    if (document.activeElement?.matches('input[data-action="brightness"]')) return;
    lastRendered = snapshot;
    if (!hasInitialRoomExpansion && rooms.length) {
      expandedRooms.add(rooms[0].name);
      hasInitialRoomExpansion = true;
    }
    roomsRoot.innerHTML = rooms.map((room) => {
      const lights = room.devices.filter((device) => device.kind === 'light' || device.kind === 'dimmer');
      const onCount = lights.filter((device) => device.state === 'on' && !device.stale).length;
      const roomSummary = lights.length
        ? `${onCount} on · ${room.devices.length} devices`
        : `${room.devices.length} devices`;
      return `<section class="room-card ${expandedRooms.has(room.name) ? '' : 'collapsed'}">
      <div class="room-head" role="button" tabindex="0" aria-expanded="${expandedRooms.has(room.name)}"><span class="room-title">${escapeHtml(room.name)}</span>
      <span class="room-meta"><span class="room-summary">${roomSummary}</span><span class="chevron">⌄</span></span></div>
      <div class="device-list">${room.devices.map(deviceCard).join('')}</div></section>`;
    }).join('');
    roomsRoot.querySelectorAll('.room-head').forEach((head) => {
      const toggle = () => { const card = head.closest('.room-card'); card.classList.toggle('collapsed'); const open = !card.classList.contains('collapsed'); head.setAttribute('aria-expanded', String(open)); const roomName = head.querySelector('.room-title').textContent; if (open) expandedRooms.add(roomName); else expandedRooms.delete(roomName); };
      head.addEventListener('click', toggle);
      head.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); } });
    });
    roomsRoot.querySelectorAll('button[data-action]').forEach((button) => {
      button.addEventListener('click', () => sendDevice(button.dataset.id, button.dataset.action === 'toggle' ? button.dataset.nextAction : button.dataset.action));
    });
    roomsRoot.querySelectorAll('input[data-action="brightness"]').forEach((range) => {
      range.addEventListener('change', () => sendDevice(range.dataset.id, `brightness:${range.value}`));
    });
  }
  const reported = data.rooms.flatMap((room) => room.devices).filter((device) => device.updated_at).length;
  const last = data.last_event_at ? new Date(data.last_event_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'none yet';
  updatedLabel.textContent = data.connected ? `${reported} device reports · last bus activity ${last}` : 'Waiting for the gateway connection';
}

function loadStatus() {
  if (statusRequest) return statusRequest;
  statusRequest = (async () => {
    try {
      const response = await fetch('/api/status', {cache:'no-store'});
      if (!response.ok) throw new Error('Status request failed');
      render(await response.json());
    } catch (_) {
      gatewayBadge.className = 'connection offline';
      gatewayBadge.querySelector('span').textContent = 'Page reconnecting';
    }
  })().finally(() => { statusRequest = null; });
  return statusRequest;
}

async function sendDevice(id, action) {
  try {
    const response = await fetch(`/api/devices/${id}/command`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not send command');
    showToast('Command sent · waiting for device feedback');
    setTimeout(loadStatus, 650);
  } catch (error) {
    showToast(error.message);
  }
}

async function sendAllLightsOff() {
  if (allLightsOffInFlight || !gatewayBadge.classList.contains('online')) return;
  if (!window.confirm('Turn off all lights and dimmers in the home?')) return;
  allLightsOffInFlight = true;
  allLightsOffButton.disabled = true;
  allLightsOffButton.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/lights/off', {method:'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not turn off all lights');
    showToast('All Lights Off sent · waiting for device feedback');
    setTimeout(loadStatus, 300);
  } catch (error) {
    showToast(error.message);
  } finally {
    allLightsOffInFlight = false;
    loadStatus();
  }
}

async function sendAllLightsOn() {
  if (allLightsOnInFlight || !gatewayBadge.classList.contains('online')) return;
  if (!window.confirm('Turn on all lights and set dimmers to 50%?')) return;
  allLightsOnInFlight = true;
  allLightsOnButton.disabled = true;
  allLightsOnButton.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/lights/on', {method:'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not turn on all lights');
    showToast('All ON started · waiting for device feedback');
    setTimeout(loadStatus, 300);
  } catch (error) {
    showToast(error.message);
  } finally {
    allLightsOnInFlight = false;
    loadStatus();
  }
}

function updateBulkLightsOnNotice(operation) {
  if (!operation) return;
  if (['dispatching', 'confirming'].includes(operation.status)) {
    if (operation.id !== lastBulkOperationId) {
      lastBulkOperationId = operation.id;
      lastBulkSentCount = -1;
    }
    if (operation.sent !== lastBulkSentCount) {
      lastBulkSentCount = operation.sent;
      showToast(`All ON · ${operation.sent} of ${operation.total} commands sent`);
    }
    return;
  }
  if (operation.id === lastFinishedBulkOperationId || operation.status === 'dispatching' || operation.status === 'confirming') return;
  lastFinishedBulkOperationId = operation.id;
  const confirmed = operation.confirmed || [];
  if (operation.status === 'complete' && confirmed.length === operation.total) {
    showToast(`All ON confirmed for ${confirmed.length} devices`);
    return;
  }
  const issues = [...new Set([...(operation.failed || []), ...(operation.unconfirmed || [])])];
  const names = issues.slice(0, 3).join(', ');
  const more = issues.length > 3 ? ` and ${issues.length - 3} more` : '';
  showToast(`All ON: ${confirmed.length}/${operation.total} confirmed${names ? ` · Check ${names}${more}` : ''}`);
}

function showToast(text) {
  toast.textContent = text;
  toast.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('visible'), 2800);
}

document.querySelector('#refresh').addEventListener('click', loadStatus);
allLightsOffButton.addEventListener('click', sendAllLightsOff);
allLightsOnButton.addEventListener('click', sendAllLightsOn);
function refreshWhenPageResumes() {
  if (!document.hidden) loadStatus();
}
document.addEventListener('visibilitychange', refreshWhenPageResumes);
window.addEventListener('pageshow', refreshWhenPageResumes);
window.addEventListener('focus', refreshWhenPageResumes);
window.addEventListener('online', refreshWhenPageResumes);
loadStatus();
refreshTimer = setInterval(loadStatus, 2000);

