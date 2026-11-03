const $ = s => document.querySelector(s);
const token = $('meta[name="csrf-token"]').content;
let scenario = 'sun', state = {jobs: [], avatars: []}, busy = false, uploadBusy = false;
let selectedAvatar = '', candidateId = '', referenceLoaded = false;
const prices = {low: .013, medium: .05, high: .2};
const methods = {selfie: 'Direct selfie', avatar: 'Approved avatar', protected: 'Protected head', base: 'Reference candidate', clothes: 'Fixed-base clothing edit'};
const labels = {sun: 'Warm & sunny', rain: 'Rainy commute', cold: 'Cold morning'};
const scores = {likeness: 'Looks like me', body: 'Body consistency', framing: 'Stable framing', garment: 'Clothing matches brief', outfit: 'Outfit quality', boundary: 'Natural head / neck join'};
const drafts = new Map();
const cardSignatures = new Map();
const checked = name => [...document.querySelectorAll(`[name=${name}]:checked`)].map(x => x.value);
const message = text => { $('#message').textContent = text; };
function element(tag, text, className) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (className) e.className = className;
  return e;
}
async function api(path, options = {}) {
  const response = await fetch('/api/pilot' + path, {...options, headers: {'X-CSRF-Token': token, ...options.headers}});
  const data = await response.json().catch(() => ({error: 'Request failed. Refresh the page and try again.'}));
  if (!response.ok) throw Error(data.error || 'Request failed.');
  return data;
}
const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
function controls() {
  for (const input of document.querySelectorAll('[name=method]')) {
    const locked = input.value !== 'selfie' && !selectedAvatar;
    input.disabled = locked;
    input.title = locked ? 'Create and approve a reference to unlock this method.' : '';
    if (locked) input.checked = false;
  }
  const qs = checked('quality'), ms = checked('method'), count = qs.length * ms.length;
  const needsAvatar = ms.some(m => m !== 'selfie') && !selectedAvatar;
  $('#setup-reference').hidden = !!selectedAvatar;
  $('#comparison-help').textContent = !selectedAvatar ? 'Direct selfie is available now. To unlock the other two methods, create a reference in step 1 and approve it.' : 'All methods are unlocked. Choose up to 3 method × quality combinations.';
  $('#generate').textContent = `Show / generate ${count} portrait${count === 1 ? '' : 's'} ↗`;
  $('#generate').disabled = busy || uploadBusy || !state.photo || !$('#consent').checked || !count || count > 3 || needsAvatar;
  $('#create-avatar').disabled = busy || uploadBusy || !state.ready || !state.photo || !$('#consent').checked;
  $('#reference-help').textContent = busy ? 'A generation is running. Wait for it to finish.' : uploadBusy ? 'Uploading your photo…' : !state.photo ? 'Upload your photo to begin.' : !state.ready ? 'The OpenAI credential is not configured.' : !$('#consent').checked ? 'Confirm photo use above to enable reference creation.' : 'Ready to create your reference. Comparison quality selections do not affect this step.';
  $('#photo').disabled = busy || uploadBusy || state.jobs.length > 0;
  $('#clear').disabled = busy || uploadBusy;
  $('#approve-avatar').disabled = busy || !$('#approve-check').checked;
  $('#estimate').textContent = `${needsAvatar ? 'Approve a reference first. ' : ''}${count > 3 ? 'Select at most 3 combinations. ' : ''}If all are new: $${(ms.length * qs.reduce((a, q) => a + prices[q], 0)).toFixed(3)} output + input charges. Saved matches cost $0 to view. ${state.remaining ?? 24} new images remain in the local allowance (including references). Not a dollar cap.`;
}
function box() { return ['x', 'y', 'w', 'h'].map(k => +$('#head-' + k).value / 100); }
function drawRegion() {
  const [x, y, w, h] = box(), ellipse = $('#head-ellipse');
  ellipse.setAttribute('cx', (x + w / 2) * 100);
  ellipse.setAttribute('cy', (y + h / 2) * 150);
  ellipse.setAttribute('rx', w * 50);
  ellipse.setAttribute('ry', h * 75);
}
function review(job) {
  candidateId = job.id;
  $('#candidate-image').src = '/api/pilot/images/' + job.id;
  $('#review').hidden = false;
  $('#approved-reference').hidden = true;
  $('#approve-check').checked = false;
  drawRegion(); controls();
}
function renderIdentity() {
  const select = $('#avatar-version');
  const signature = state.avatars.map(a => a.id).join();
  if (select.dataset.signature !== signature) {
    select.dataset.signature = signature;
    select.replaceChildren(new Option('Original selfie only', ''));
    for (const avatar of state.avatars) select.append(new Option(`Avatar v${avatar.version} · approved`, avatar.id));
    selectedAvatar = state.active_avatar || '';
    select.value = selectedAvatar;
  }
  const avatar = state.avatars.find(a => a.id === selectedAvatar);
  $('#approved-reference').hidden = !avatar || !!candidateId;
  if (avatar && !candidateId) $('#approved-reference').src = '/api/pilot/images/' + avatar.source_job;
  $('#identity-title').textContent = avatar ? `Avatar v${avatar.version}. Your approved starting point.` : 'Create your reference first.';
  $('#identity-description').textContent = avatar ? 'This version is immutable. New candidates do not replace it until you approve them. Select any approved version for a comparison.' : 'Your approved face, body proportions and framing become the starting point for outfit edits. Choose reference quality and confirm photo use, then create a reference candidate.';
  const pending = [...state.jobs].reverse().find(j => j.kind === 'avatar' && j.status === 'done' && !state.avatars.some(a => a.source_job === j.id));
  if (!candidateId && pending) review(pending);
}
function recommendation() {
  $('#recommendation').replaceChildren(element('span', `${labels[scenario]} · generic outfit brief`));
  for (const item of state.outfits?.[scenario]?.items || []) $('#recommendation').append(element('span', item.id.replaceAll('-', ' ')));
}
function ratings(job, body) {
  const form = element('form', null, 'ratings');
  const values = drafts.get(job.id) || job.rating;
  for (const [key, title] of Object.entries(scores)) {
    const label = element('label', title), select = element('select');
    select.name = key; select.required = true;
    select.setAttribute('aria-label', `${title} for ${methods[job.mode]} ${job.quality}`);
    select.append(new Option('Rate 1–5', ''));
    for (let n = 1; n <= 5; n++) select.append(new Option(`${n}${n === 5 ? ' · excellent' : n === 1 ? ' · poor' : ''}`, n));
    select.value = values[key] || '';
    label.append(select); form.append(label);
  }
  const keep = element('label', 'I would use this portrait'), check = element('input');
  check.type = 'checkbox'; check.name = 'accepted'; check.checked = values.accepted || false;
  keep.append(check); form.append(keep);
  const read = () => Object.fromEntries([...Object.keys(scores).map(k => [k, +form.elements[k].value]), ['accepted', check.checked]]);
  form.onchange = () => drafts.set(job.id, read());
  const save = element('button', Object.keys(job.rating).length ? 'Update rating' : 'Save rating');
  form.append(save);
  form.onsubmit = async e => {
    e.preventDefault(); save.disabled = true;
    try { await post('/ratings/' + job.id, read()); drafts.delete(job.id); message('Rating saved. Unchecking “I would use this portrait” excludes it from reuse, allowing another attempt.'); await refresh(); }
    catch (err) { message(err.message); }
    finally { save.disabled = false; }
  };
  body.append(form);
}
function card(job) {
  const article = element('article', null, 'card'); article.id = 'job-' + job.id;
  if (job.status === 'done') {
    const image = element('img'); image.src = '/api/pilot/images/' + job.id;
    image.alt = `${methods[job.mode]}: ${job.kind === 'avatar' ? 'full-body reference' : labels[job.scenario]}`;
    article.append(image);
  } else article.append(element('div', job.error || (job.status === 'generating' ? 'Creating your portrait… This can take several minutes.' : 'Queued · waiting for the previous portrait'), 'pending'));
  const body = element('div', null, 'card-body');
  body.append(element('div', methods[job.mode], 'method-label'));
  body.append(element('h3', `${job.kind === 'avatar' ? 'Full-body reference' : labels[job.scenario]} / ${job.quality}`));
  const avatar = state.avatars.find(a => a.id === job.avatar_id);
  if (avatar) body.append(element('p', `Avatar v${avatar.version} · ${job.pose}`));
  const metrics = element('div', null, 'metrics');
  metrics.append(element('span', job.seconds != null ? `${job.seconds}s` : 'Waiting'), element('span', job.estimated_usd != null ? `≈ $${job.estimated_usd.toFixed(4)}` : 'Cost unknown'));
  body.append(metrics);
  if (job.status === 'done') {
    const a = element('a', 'Save portrait ↗'); a.href = '/api/pilot/images/' + job.id;
    a.download = `weatheravatar-${job.mode}-${job.scenario}-${job.quality}.png`; body.append(a);
    if (job.kind === 'avatar') {
      const approved = state.avatars.find(a => a.source_job === job.id);
      if (approved) body.append(element('p', `Approved as Avatar v${approved.version}.`));
      else {
        const button = element('button', 'Review & approve reference', 'review-button');
        button.onclick = () => { review(job); $('#identity-panel').scrollIntoView({behavior: 'smooth'}); }; body.append(button);
      }
    } else {
      body.append(element('p', job.checks?.protected_core_unchanged ? 'Protected core pixels unchanged ✓ · dimensions match ✓. Review body alignment and the neck join below.' : 'Dimensions match ✓. Identity, body and framing still require your review.', 'checks'));
      body.append(element('p', 'Garment score checks the generic outfit brief. Exact product fidelity is not tested without product images.'));
      ratings(job, body);
    }
  }
  article.append(body); return article;
}
function renderCards() {
  const cards = $('#cards'), ids = new Set(state.jobs.map(j => j.id));
  for (const child of [...cards.children]) if (!ids.has(child.id.replace('job-', ''))) child.remove();
  for (const job of state.jobs) {
    const signature = JSON.stringify([job, state.avatars.map(a => a.id)]);
    if (cardSignatures.get(job.id) === signature) continue;
    cardSignatures.set(job.id, signature);
    const existing = document.getElementById('job-' + job.id), replacement = card(job);
    if (existing) existing.replaceWith(replacement); else cards.append(replacement);
  }
  $('#empty').hidden = !!state.jobs.length; $('#export').hidden = !state.jobs.length;
}
function summary() {
  const container = $('#summary'); container.replaceChildren(); container.hidden = !state.jobs.length;
  const known = state.jobs.filter(j => j.estimated_usd != null), total = known.reduce((s, j) => s + j.estimated_usd, 0);
  container.append(element('strong', `$${total.toFixed(4)} known estimated spend · ${state.jobs.length} attempts, including onboarding`));
  container.append(element('div', 'Standard undiscounted token estimates, not invoices. Unknown or failed-request charges may be missing. Reused images add no generation attempts.'));
  const table = element('table', null, 'metric-table'), header = element('tr');
  for (const title of ['Method', 'Accepted / rated', '1st try accepted / looks', 'Cost / keeper']) header.append(element('th', title)); table.append(header);
  for (const mode of ['selfie', 'avatar', 'protected']) {
    const jobs = state.jobs.filter(j => j.mode === mode), rated = jobs.filter(j => typeof j.rating.accepted === 'boolean'), keepers = rated.filter(j => j.rating.accepted);
    const first = [...new Map([...jobs].reverse().map(j => [j.cache_key, j])).values()];
    const firstKeepers = first.filter(j => j.rating.accepted).length;
    const cost = jobs.reduce((s, j) => s + (j.estimated_usd ?? 0), 0), row = element('tr');
    const completeCost = jobs.every(j => j.estimated_usd != null);
    for (const text of [methods[mode], `${keepers.length} / ${rated.length}`, `${firstKeepers} / ${first.length}`, keepers.length ? `${completeCost ? '≈' : '≥ known'} $${(cost / keepers.length).toFixed(4)}` : 'Not rated']) row.append(element('td', text));
    table.append(row);
  }
  container.append(table, element('p', 'Release target: ≥90% accepted on the first attempt, with stable framing and body consistency across multiple adults. This pilot has not validated that target. Method costs exclude shared onboarding, shown above.'));
}
async function refresh() {
  try {
    state = await api(''); busy = state.jobs.some(j => ['queued', 'generating'].includes(j.status));
    $('#connection').textContent = state.ready ? '● OpenAI configured' : '○ Credential needed';
    if (state.photo && !referenceLoaded) { $('#reference').src = '/api/pilot/photo'; referenceLoaded = true; }
    $('#reference').hidden = !state.photo; $('#upload-label').hidden = !!state.photo;
    renderIdentity(); renderCards(); recommendation(); summary(); controls();
  } catch (e) { message(e.message); }
}
$('#photo').onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  uploadBusy = true; controls();
  try { const data = new FormData(); data.append('photo', file); await api('/photo', {method: 'POST', body: data}); referenceLoaded = false; message('Photo saved locally. Choose reference quality, confirm photo use, then create your reference.'); await refresh(); }
  catch (err) { message(err.message); } finally { uploadBusy = false; controls(); }
};
for (const button of document.querySelectorAll('.scenario')) button.onclick = () => {
  scenario = button.dataset.scenario;
  for (const b of document.querySelectorAll('.scenario')) { b.classList.toggle('selected', b === button); b.setAttribute('aria-pressed', String(b === button)); }
  recommendation();
};
for (const input of document.querySelectorAll('[name=quality],[name=method]')) input.onchange = () => {
  if (checked('quality').length * checked('method').length > 3) {
    input.checked = false;
    message('That would exceed 3 portraits. Use one quality for all three methods, or one method for multiple qualities.');
  }
  controls();
};
for (const input of document.querySelectorAll('#consent,#approve-check')) input.onchange = controls;
$('#setup-reference').onclick = () => {
  const target = candidateId ? $('#approve-check') : $('#create-avatar');
  target.scrollIntoView({behavior: 'smooth', block: 'center'});
  target.focus({preventScroll: true});
};
for (const input of document.querySelectorAll('[id^=head-]')) input.oninput = drawRegion;
$('#avatar-version').onchange = () => { selectedAvatar = $('#avatar-version').value; renderIdentity(); controls(); };
async function submit(path, body) {
  busy = true; controls();
  try {
    const result = await post(path, {...body, consent: $('#consent').checked, request_id: crypto.randomUUID()});
    message(result.reused ? `Reused ${result.reused === true ? 'existing' : result.reused} saved or queued result(s). ${result.generated || 0} new images requested.` : 'Generation started. The approved identity stays unchanged until you approve a new candidate.');
    await refresh();
  } catch (e) { message(e.message); busy = false; controls(); }
}
$('#create-avatar').onclick = () => submit('/avatar', {preferences: $('#preferences').value, quality: $('#reference-quality').value});
$('#generate').onclick = () => submit('/runs', {scenario, qualities: checked('quality'), modes: checked('method'), avatar_id: selectedAvatar || null});
$('#approve-avatar').onclick = async () => {
  try { const result = await post('/approve', {job_id: candidateId, head_box: box(), approved: $('#approve-check').checked}); candidateId = ''; $('#review').hidden = true; message(`Avatar v${result.avatar.version} approved. Ready to compare all three methods.`); await refresh(); }
  catch (e) { message(e.message); }
};
$('#clear').onclick = () => {
  const dialog = element('dialog'); dialog.append(element('h3', 'Delete this local library?'), element('p', 'This removes the uploaded photo, approved versions, generated portraits and ratings from this app. Export or download anything you want to keep first. It does not reset the generation allowance or delete provider records.'));
  const cancel = element('button', 'Keep library'), confirm = element('button', 'Delete local data');
  cancel.onclick = () => { dialog.close(); dialog.remove(); };
  confirm.onclick = async () => {
    try { await api('', {method: 'DELETE'}); candidateId = ''; selectedAvatar = ''; referenceLoaded = false; cardSignatures.clear(); drafts.clear(); $('#review').hidden = true; $('#reference').removeAttribute('src'); $('#photo').value = ''; $('#consent').checked = false; message('Local library deleted.'); dialog.close(); dialog.remove(); await refresh(); }
    catch (e) { message(e.message); }
  };
  dialog.append(cancel, confirm); document.body.append(dialog); dialog.showModal();
};
await refresh(); setInterval(() => { if (busy) refresh(); }, 2500);
