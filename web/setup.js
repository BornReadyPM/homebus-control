const editor = document.querySelector('#device-list');
const setupMessage = document.querySelector('#setup-message');
const setupBadge = document.querySelector('#setup-connection');
let devices = [];

function safe(text) { return String(text).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function renderEditor() {
  editor.innerHTML = devices.map((device, index) => `<div class="editor-row" data-row="${index}">
    <input aria-label="Room" data-field="room" value="${safe(device.room)}" placeholder="Room">
    <input aria-label="Device name" data-field="name" value="${safe(device.name)}" placeholder="Name">
    <select aria-label="Device type" data-field="kind"><option value="light" ${device.kind==='light'?'selected':''}>Light</option><option value="dimmer" ${device.kind==='dimmer'?'selected':''}>Dimmer</option><option value="shade" ${device.kind==='shade'?'selected':''}>Shade</option></select>
    <input aria-label="OpenWebNet address" data-field="where" value="${safe(device.where)}" placeholder="Address" inputmode="numeric">
    <select aria-label="OpenWebNet subsystem" data-field="who"><option value="1" ${Number(device.who)===1?'selected':''}>WHO 1</option><option value="2" ${Number(device.who)===2?'selected':''}>WHO 2</option></select>
    <button class="remove" type="button" aria-label="Remove device" data-remove="${index}">×</button>
  </div>`).join('');
  editor.querySelectorAll('[data-field]').forEach((input) => input.addEventListener('input', () => {
    const row = input.closest('.editor-row');
    const index = Number(row.dataset.row);
    devices[index][input.dataset.field] = input.dataset.field === 'who' ? Number(input.value) : input.value;
    if (input.dataset.field === 'kind') devices[index].who = input.value === 'shade' ? 2 : 1;
    if (input.dataset.field === 'who') devices[index].kind = input.value === '2' ? 'shade' : (devices[index].kind === 'shade' ? 'light' : devices[index].kind);
    if (input.dataset.field === 'who' || input.dataset.field === 'kind') renderEditor();
  }));
  editor.querySelectorAll('[data-remove]').forEach((button) => button.addEventListener('click', () => {
    devices.splice(Number(button.dataset.remove), 1);
    renderEditor();
  }));
}

async function loadDevices() {
  const response = await fetch('/api/admin/devices', {cache:'no-store'});
  if (!response.ok) throw new Error('Could not load setup');
  devices = (await response.json()).devices;
  renderEditor();
}

async function loadDiagnostics() {
  try {
    const response = await fetch('/api/admin/events', {cache:'no-store'});
    const data = await response.json();
    setupBadge.className = `connection ${data.connected ? 'online' : 'offline'}`;
    setupBadge.querySelector('span').textContent = data.connected ? 'Gateway online' : 'Gateway offline';
    const events = data.events || [];
    document.querySelector('#events').innerHTML = events.length ? events.map((event) => `<div class="event"><time>${safe(new Date(event.received_at).toLocaleTimeString())}</time><code>${safe(event.raw_frame)}</code><small>${safe(event.interpreted_as)}</small></div>`).join('') : '<p class="muted">No bus reports received yet.</p>';
  } catch (_) { /* Refresh on the next poll. */ }
}

document.querySelector('#add-device').addEventListener('click', () => {
  devices.push({room:'New room',name:'New device',kind:'light',who:1,where:''});
  renderEditor();
  editor.lastElementChild?.scrollIntoView({behavior:'smooth',block:'center'});
});

document.querySelector('#save').addEventListener('click', async () => {
  setupMessage.textContent = 'Saving…';
  setupMessage.className = '';
  try {
    const response = await fetch('/api/admin/devices', {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({devices})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not save setup');
    setupMessage.textContent = 'Setup saved';
    await loadDevices();
  } catch (error) {
    setupMessage.textContent = error.message;
    setupMessage.className = 'setup-error';
  }
});

document.querySelector('#resync').addEventListener('click', async () => {
  setupMessage.textContent = 'Requesting fresh status…';
  try {
    const response = await fetch('/api/admin/resynchronize', {method:'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Status refresh failed');
    setupMessage.textContent = 'Status refresh requested';
  } catch (error) { setupMessage.textContent = error.message; setupMessage.className = 'setup-error'; }
});

loadDevices().catch((error) => { setupMessage.textContent = error.message; setupMessage.className = 'setup-error'; });
loadDiagnostics();
setInterval(loadDiagnostics, 2500);

