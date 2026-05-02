/**
 * Doctor Zebra – front-end helpers
 *
 * Provides:
 *  - Lookup autocomplete for fields that have a `data-lookup` attribute.
 *  - Lookup modal search (openLookupModal / doLookupSearch).
 *  - Auto-fill sibling fields when a lookup item is selected.
 */

/* ======================================================================== */
/* Inline autocomplete                                                        */
/* ======================================================================== */

let _activeInput = null;
let _activeDropdown = null;

function _removeDropdown() {
  if (_activeDropdown) {
    _activeDropdown.remove();
    _activeDropdown = null;
  }
}

function _attachAutocomplete(input) {
  const lookupName = input.dataset.lookup;
  const valueField = input.dataset.valueField || 'value';
  const labelField = input.dataset.labelField || 'label';
  let autofill = [];
  try { autofill = JSON.parse(input.dataset.autofill || '[]'); } catch (_) {}

  input.addEventListener('input', function () {
    const q = this.value.trim();
    if (q.length < 1) { _removeDropdown(); return; }
    fetch(`/api/lookup/${encodeURIComponent(lookupName)}/search?q=${encodeURIComponent(q)}`)
      .then(r => r.json())
      .then(items => _showDropdown(input, items, valueField, labelField, autofill))
      .catch(() => _removeDropdown());
  });

  input.addEventListener('blur', () => setTimeout(_removeDropdown, 200));
  input.addEventListener('keydown', (e) => {
    if (!_activeDropdown) return;
    const items = _activeDropdown.querySelectorAll('.dropdown-item');
    const active = _activeDropdown.querySelector('.dropdown-item.active');
    let idx = active ? [...items].indexOf(active) : -1;
    if (e.key === 'ArrowDown') { e.preventDefault(); _setActive(items, Math.min(idx + 1, items.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); _setActive(items, Math.max(idx - 1, 0)); }
    else if (e.key === 'Enter' && active) { e.preventDefault(); active.click(); }
    else if (e.key === 'Escape') { _removeDropdown(); }
  });
}

function _setActive(items, idx) {
  items.forEach(el => el.classList.remove('active'));
  if (items[idx]) { items[idx].classList.add('active'); items[idx].scrollIntoView({ block: 'nearest' }); }
}

function _showDropdown(input, items, valueField, labelField, autofill) {
  _removeDropdown();
  if (!items.length) return;

  const wrapper = input.closest('.input-group') || input.parentElement;
  wrapper.style.position = 'relative';

  const dropdown = document.createElement('div');
  dropdown.className = 'lookup-dropdown';

  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'dropdown-item';
    const label = item[labelField] || item[valueField] || JSON.stringify(item);
    const value = item[valueField] || label;
    el.textContent = `${value} – ${label}`;
    el.addEventListener('mousedown', () => {
      input.value = value;
      _fillSiblings(input, item, autofill);
      _removeDropdown();
    });
    dropdown.appendChild(el);
  });

  wrapper.appendChild(dropdown);
  _activeDropdown = dropdown;
}

function _fillSiblings(input, item, autofill) {
  autofill.forEach(rule => {
    const val = item[rule.from];
    if (val === undefined) return;
    const sibling = document.getElementById('f_' + rule.to) ||
                    document.querySelector(`[name="${rule.to}"]`);
    if (sibling) sibling.value = val;
  });
}

/* Initialise autocomplete on page load */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.lookup-input').forEach(input => _attachAutocomplete(input));
});


/* ======================================================================== */
/* Lookup modal                                                               */
/* ======================================================================== */

let _modalLookup = null;
let _modalValueField = 'value';
let _modalLabelField = 'label';
let _modalTargetId = null;
let _modalAutofill = [];

function openLookupModal(targetId, lookupName, valueField, labelField, autofill) {
  _modalTargetId = targetId;
  _modalLookup = lookupName;
  _modalValueField = valueField || 'value';
  _modalLabelField = labelField || 'label';
  _modalAutofill = autofill || [];

  document.getElementById('lookupSearchInput').value = '';
  document.getElementById('lookupResults').innerHTML = '';
  const modal = new bootstrap.Modal(document.getElementById('lookupModal'));
  modal.show();
  setTimeout(() => document.getElementById('lookupSearchInput').focus(), 300);
}

function doLookupSearch(query) {
  if (!_modalLookup) return;
  if (query.length < 1) { document.getElementById('lookupResults').innerHTML = ''; return; }

  fetch(`/api/lookup/${encodeURIComponent(_modalLookup)}/search?q=${encodeURIComponent(query)}`)
    .then(r => r.json())
    .then(items => {
      const container = document.getElementById('lookupResults');
      container.innerHTML = '';
      if (!items.length) {
        container.innerHTML = '<p class="text-muted small p-2">Sin resultados.</p>';
        return;
      }
      items.forEach(item => {
        const label = item[_modalLabelField] || item[_modalValueField] || JSON.stringify(item);
        const value = item[_modalValueField] || label;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'list-group-item list-group-item-action';
        btn.innerHTML = `<strong class="font-monospace">${escHtml(String(value))}</strong>
          <span class="text-muted ms-2 small">${escHtml(String(label))}</span>`;
        btn.addEventListener('click', () => {
          const target = document.getElementById('f_' + _modalTargetId) ||
                         document.querySelector(`[name="${_modalTargetId}"]`);
          if (target) {
            target.value = value;
            const input = document.querySelector(`.lookup-input[name="${_modalTargetId}"]`);
            if (input) _fillSiblings(input, item, _modalAutofill);
          }
          bootstrap.Modal.getInstance(document.getElementById('lookupModal')).hide();
        });
        container.appendChild(btn);
      });
    })
    .catch(() => {
      document.getElementById('lookupResults').innerHTML =
        '<p class="text-danger small p-2">Error al buscar.</p>';
    });
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
