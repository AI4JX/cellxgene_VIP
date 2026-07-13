(function () {
  'use strict';

  const gridEl = document.getElementById('datasetGrid');
  const searchInput = document.getElementById('searchInput');
  const sortSelect = document.getElementById('sortSelect');
  const refreshBtn = document.getElementById('refreshBtn');
  const countEl = document.getElementById('datasetCount');
  const themeToggle = document.getElementById('themeToggle');
  const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
  const confirmBody = document.getElementById('confirmBody');
  const confirmBtn = document.getElementById('confirmBtn');

  const newFolderModal = document.getElementById('newFolderModal')
    ? new bootstrap.Modal(document.getElementById('newFolderModal')) : null;
  const moveModal = document.getElementById('moveModal')
    ? new bootstrap.Modal(document.getElementById('moveModal')) : null;

  const username = document.querySelector('meta[name="gateway-username"]')?.content || '';
  const isAdmin = document.querySelector('meta[name="gateway-is-admin"]')?.content === 'true';

  let allDatasets = [];
  let allFolders = [];
  let pollTimer = null;
  let pendingLaunches = new Set();

  const PIN_KEY = 'gatewayPinnedFolders';
  const FOLD_KEY = 'gatewayFoldedFolders';

  function getPinned() {
    try { return JSON.parse(localStorage.getItem(PIN_KEY)) || []; } catch { return []; }
  }
  function setPinned(v) { localStorage.setItem(PIN_KEY, JSON.stringify(v)); }
  function getFolded() {
    try { return JSON.parse(localStorage.getItem(FOLD_KEY)) || []; } catch { return []; }
  }
  function setFolded(v) { localStorage.setItem(FOLD_KEY, JSON.stringify(v)); }

  function isPinned(key) { return getPinned().includes(key); }
  function isFolded(key) { return getFolded().includes(key); }

  document.getElementById('adminLink')?.classList.toggle('d-none', !isAdmin);
  document.getElementById('newFolderBtn')?.classList.toggle('d-none', !isAdmin);

  document.getElementById('logoutBtn')?.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/login';
  });

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem('gatewayTheme', theme);
    if (themeToggle) {
      themeToggle.innerHTML = theme === 'dark'
        ? '<i class="bi bi-sun"></i>'
        : '<i class="bi bi-moon"></i>';
    }
  }

  const savedTheme = localStorage.getItem('gatewayTheme') || 'dark';
  applyTheme(savedTheme);

  themeToggle?.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-bs-theme');
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });

  function formatSize(bytes) {
    if (bytes === 0) return '\u2014';
    const units = ['B','KB','MB','GB','TB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
  }

  function formatTime(iso) {
    if (!iso) return '\u2014';
    return new Date(iso).toLocaleString();
  }

  function statusBadge(ds) {
    const status = ds.status.toLowerCase();
    const labels = { stopped: 'Stopped', loading: 'Loading', loaded: 'Loaded', error: 'Error' };
    const label = labels[status] || status;
    return `<span class="card-status status-${status}">
      <span class="status-dot ${status}"></span> ${label}${status === 'loaded' && ds.port ? ' :' + ds.port : ''}
    </span>`;
  }

  function qs(ds) {
    return ds.source ? '?source_name=' + encodeURIComponent(ds.source) : '';
  }

  function annotationsHtml(ds) {
    const sn = qs(ds);
    const annSubpath = ds.annotation_subpath || '';
    function annLink(a) {
      const url = '/view/' + encodeURIComponent(annSubpath + '/' + a) + '/';
      const display = a.endsWith('.csv') ? a.slice(0, -4) : a;
      return '<a href="' + url + '" class="small" target="_blank">' + display + '</a>' +
        ' <button class="btn btn-outline-warning btn-sm py-0 px-1 bake-btn" data-descriptor="' + ds.descriptor + '" data-source="' + sn + '" data-annotation-name="' + a + '" title="Write to h5ad"><i class="bi bi-fire"></i></button>';
    }
    const newLink = '<a href="#" class="new-annotation small" data-descriptor="' + ds.descriptor + '" data-source="' + sn + '" data-annotation-subpath="' + annSubpath + '">+ New</a>';
    if (!ds.annotations || ds.annotations.length === 0) {
      return '<div class="annotation-list"><span class="text-muted small">No annotations</span> \u00b7 ' + newLink + '</div>';
    }
    const items = ds.annotations.map(annLink).join(' \u00b7 ');
    return '<div class="annotation-list"><i class="bi bi-journal-text me-1"></i>' + items + ' \u00b7 ' + newLink + '</div>';
  }

  function actionButtons(ds) {
    const s = ds.status.toLowerCase();
    const isLoaded = s === 'loaded';
    const isLoading = s === 'loading';
    const isError = s === 'error';
    const isLaunching = pendingLaunches.has(ds.descriptor);
    const sn = qs(ds);
    const viewUrl = '/view/' + encodeURIComponent(ds.descriptor) + sn;

    let launchHtml;
    if (isLoaded) {
      launchHtml = `<a class="btn btn-outline-success btn-sm" href="${viewUrl}" target="_blank" title="Open dataset"><i class="bi bi-box-arrow-up-right"></i></a>`;
    } else if (isLaunching) {
      launchHtml = `<button class="btn btn-outline-secondary btn-sm" disabled><span class="spinner-border spinner-border-sm" role="status"></span></button>`;
    } else {
      launchHtml = `<button class="btn btn-outline-success btn-sm launch-btn" data-descriptor="${ds.descriptor}" data-source="${sn}" data-view-url="${viewUrl}"><i class="bi bi-play-fill"></i></button>`;
    }

    return `<div class="btn-group-action mt-2 d-flex gap-1 flex-wrap">
      ${launchHtml}
      <button class="btn btn-outline-warning btn-sm restart-btn" data-descriptor="${ds.descriptor}" data-source="${sn}" ${!isLoaded && !isError ? 'disabled' : ''}><i class="bi bi-arrow-repeat"></i></button>
      <button class="btn btn-outline-danger btn-sm stop-btn" data-descriptor="${ds.descriptor}" data-source="${sn}" ${!isLoaded && !isLoading && !isLaunching ? 'disabled' : ''}><i class="bi bi-stop-fill"></i></button>
      ${isAdmin ? '<button class="btn btn-outline-info btn-sm move-btn" data-descriptor="' + ds.descriptor + '" data-source="' + ds.source + '" title="Move to folder"><i class="bi bi-folder-symlink"></i></button>' : ''}
      <button class="btn btn-outline-danger btn-sm delete-btn" data-descriptor="${ds.descriptor}" data-source="${sn}"><i class="bi bi-trash"></i></button>
      <button class="btn btn-outline-secondary btn-sm settings-btn" data-descriptor="${ds.descriptor}" data-source="${sn}" title="Default embedding"><i class="bi bi-gear"></i></button>
    </div>`;
  }

  function render() {
    const query = (searchInput?.value || '').toLowerCase().trim();
    const sortBy = sortSelect?.value || 'name';

    let filtered = allDatasets;
    if (query) {
      filtered = allDatasets.filter(ds =>
        ds.name.toLowerCase().includes(query) ||
        ds.descriptor.toLowerCase().includes(query)
      );
    }

    const cmp = (a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'size') return (b.size || 0) - (a.size || 0);
      if (sortBy === 'mtime') return (b.mtime || '').localeCompare(a.mtime || '');
      if (sortBy === 'status') {
        const order = { loaded: 0, loading: 1, error: 2, stopped: 3 };
        return (order[a.status.toLowerCase()] ?? 9) - (order[b.status.toLowerCase()] ?? 9);
      }
      return 0;
    };
    filtered.sort(cmp);

    const groups = {};
    filtered.forEach(ds => {
      const key = ds.subfolder || '__root__';
      if (!groups[key]) groups[key] = [];
      groups[key].push(ds);
    });
    allFolders.forEach(f => {
      if (!groups[f]) groups[f] = [];
    });

    const pinned = getPinned();
    const sortedKeys = Object.keys(groups).sort((a, b) => {
      const aPinned = pinned.includes(a);
      const bPinned = pinned.includes(b);
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;
      if (a === '__root__') return -1;
      if (b === '__root__') return 1;
      return a.localeCompare(b);
    });

    countEl.textContent = filtered.length + ' / ' + allDatasets.length + ' datasets';

    if (filtered.length === 0) {
      gridEl.innerHTML = '<div class="text-center py-5 text-muted"><i class="bi bi-inbox" style="font-size:2rem"></i><p class="mt-2">No datasets found.</p></div>';
      return;
    }

    const folded = getFolded();
    let html = '';
    for (const key of sortedKeys) {
      const datasets = groups[key];
      const label = key === '__root__' ? 'Root' : key;
      const isPinnedFolder = pinned.includes(key);
      const isFoldedFolder = folded.includes(key);
      const safeId = 'folder-' + key.replace(/[^a-zA-Z0-9_-]/g, '_');

      html += `<div class="folder-section">
        <div class="folder-header ${isFoldedFolder ? 'collapsed' : ''}" data-target="${safeId}">
          <span class="collapse-icon"><i class="bi ${isFoldedFolder ? 'bi-chevron-right' : 'bi-chevron-down'}"></i></span>
          <span class="folder-label">${label}</span>
          <span class="text-muted ms-1 small">(${datasets.length})</span>
          <button class="btn btn-sm btn-link pin-btn ms-auto p-0 ${isPinnedFolder ? 'text-warning' : 'text-secondary'}" data-folder="${key}" title="${isPinnedFolder ? 'Unpin' : 'Pin'}">
            <i class="bi ${isPinnedFolder ? 'bi-pin-fill' : 'bi-pin'}"></i>
          </button>
        </div>
        <div class="folder-content" id="${safeId}" style="display: ${isFoldedFolder ? 'none' : 'grid'}">
          <div class="dataset-grid">
            ${datasets.map(ds => {
              return `<div class="dataset-card" data-descriptor="${ds.descriptor}">
                <div class="card-title">
                  <a href="/view/${encodeURIComponent(ds.descriptor)}/" class="text-decoration-none" target="_blank">${ds.name}</a>
                </div>
                <div class="card-meta">${formatSize(ds.size)} \u00b7 ${formatTime(ds.mtime)}</div>
                ${statusBadge(ds)}
                ${annotationsHtml(ds)}
                ${actionButtons(ds)}
                <div class="settings-panel mt-2" id="settings-${ds.descriptor.replace(/[^a-zA-Z0-9_-]/g, '_')}" style="display:none">
                  <div class="input-group input-group-sm">
                    <label class="input-group-text">Default embedding</label>
                    <select class="form-select form-select-sm emb-select" data-descriptor="${ds.descriptor}" data-source="${qs(ds)}"></select>
                    <button class="btn btn-outline-primary btn-sm emb-save-btn" data-descriptor="${ds.descriptor}" data-source="${qs(ds)}">Save</button>
                  </div>
                  <div class="form-text emb-status small"></div>
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>`;
    }
    gridEl.innerHTML = html;

    document.querySelectorAll('.folder-header').forEach(h => {
      h.addEventListener('click', function (e) {
        if (e.target.closest('.pin-btn')) return;
        const target = document.getElementById(this.dataset.target);
        if (!target) return;
        const isVisible = target.style.display !== 'none';
        target.style.display = isVisible ? 'none' : 'grid';
        this.classList.toggle('collapsed', isVisible);
        const key = this.querySelector('.pin-btn')?.dataset.folder;
        if (key) {
          const foldedSet = getFolded();
          if (isVisible) { if (!foldedSet.includes(key)) foldedSet.push(key); }
          else { const idx = foldedSet.indexOf(key); if (idx > -1) foldedSet.splice(idx, 1); }
          setFolded(foldedSet);
          this.querySelector('.collapse-icon i').className = isVisible ? 'bi bi-chevron-right' : 'bi bi-chevron-down';
        }
      });
    });

    document.querySelectorAll('.pin-btn').forEach(btn => {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        const folder = this.dataset.folder;
        const pinnedSet = getPinned();
        const idx = pinnedSet.indexOf(folder);
        if (idx > -1) { pinnedSet.splice(idx, 1); }
        else { pinnedSet.push(folder); }
        setPinned(pinnedSet);
        render();
      });
    });

    document.querySelectorAll('.launch-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        const viewUrl = this.dataset.viewUrl || '/view/' + encodeURIComponent(desc) + '/' + sn;
        pendingLaunches.add(desc);
        render();
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/launch' + sn, { method: 'POST' })
          .then(r => r.json())
          .then(data => {
            if (data.redirect) window.open(data.redirect, '_blank');
            else window.open(viewUrl, '_blank');
          })
          .catch(() => {
            pendingLaunches.delete(desc);
            render();
            window.open(viewUrl, '_blank');
          });
      });
    });

    document.querySelectorAll('.stop-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/terminate' + sn, { method: 'POST' })
          .then(r => r.json())
          .then(() => fetchDatasets())
          .catch(() => {});
      });
    });

    document.querySelectorAll('.restart-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/relaunch' + sn, { method: 'POST' })
          .then(r => r.json())
          .then(data => { if (data.redirect) window.location.href = data.redirect; })
          .catch(() => {});
      });
    });

    document.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        confirmBody.textContent = 'Delete "' + desc + '"? This will remove the h5ad file and all annotations. This cannot be undone.';
        confirmBtn.dataset.descriptor = desc;
        confirmBtn.dataset.source = sn;
        confirmModal.show();
      });
    });

    document.querySelectorAll('.move-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const source = this.dataset.source || '';
        document.getElementById('moveDatasetLabel').textContent = 'Move: ' + desc;
        document.getElementById('moveConfirmBtn').dataset.descriptor = desc;
        document.getElementById('moveConfirmBtn').dataset.source = source;
        populateMoveFolders(desc);
        if (moveModal) moveModal.show();
      });
    });

    document.querySelectorAll('.new-annotation').forEach(a => {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        const annSubpath = this.dataset.annotationSubpath || '';
        const name = prompt('Enter annotation name:');
        if (!name || !name.trim()) return;
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/annotations/new?name=' + encodeURIComponent(name.trim()) + sn, { method: 'POST' })
          .then(r => r.json())
          .then(data => {
            if (data.ok) {
              fetchDatasets();
              const annUrl = '/view/' + encodeURIComponent(annSubpath + '/' + name.trim() + '.csv') + '/';
              window.open(annUrl, '_blank');
            } else {
              alert('Error: ' + (data.error || 'unknown'));
            }
          })
          .catch(() => alert('Failed to create annotation'));
      });
    });

    document.querySelectorAll('.bake-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        const annName = this.dataset.annotationName;
        if (!confirm('Write "' + annName + '" into h5ad and delete the CSV?')) return;
        const self = this;
        self.disabled = true;
        self.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/annotations/' + encodeURIComponent(annName) + '/bake' + sn, { method: 'POST' })
          .then(r => r.json())
          .then(data => {
            if (data.ok) {
              self.innerHTML = '<i class="bi bi-check-lg text-success"></i>';
              setTimeout(fetchDatasets, 500);
            } else {
              alert('Bake failed: ' + (data.error || 'unknown'));
              self.disabled = false;
              self.innerHTML = '<i class="bi bi-fire"></i>';
            }
          })
          .catch(() => { alert('Bake failed'); self.disabled = false; self.innerHTML = '<i class="bi bi-fire"></i>'; });
      });
    });

    document.querySelectorAll('.settings-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        const panelId = 'settings-' + desc.replace(/[^a-zA-Z0-9_-]/g, '_');
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const isVisible = panel.style.display !== 'none';
        document.querySelectorAll('.settings-panel').forEach(p => p.style.display = 'none');
        if (isVisible) return;
        panel.style.display = '';
        const sel = panel.querySelector('.emb-select');
        const status = panel.querySelector('.emb-status');
        status.textContent = 'Loading...';
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/embeddings' + sn)
          .then(r => r.json())
          .then(data => {
            if (!data.ok) { status.textContent = data.error || 'Failed'; return; }
            sel.innerHTML = '<option value="">None</option>';
            data.embeddings.forEach(e => {
              const opt = document.createElement('option');
              opt.value = e; opt.textContent = e;
              sel.appendChild(opt);
            });
            return fetch('/api/dataset/' + encodeURIComponent(desc) + '/config' + sn);
          })
          .then(r => r ? r.json() : null)
          .then(data => {
            if (data && data.ok && data.default_embedding) {
              sel.value = data.default_embedding;
              status.textContent = 'Current: ' + data.default_embedding;
            } else {
              status.textContent = 'Current: none';
            }
          })
          .catch(() => { status.textContent = 'Failed to load'; });
      });
    });

    document.querySelectorAll('.emb-save-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const desc = this.dataset.descriptor;
        const sn = this.dataset.source || '';
        const panel = this.closest('.settings-panel');
        const sel = panel.querySelector('.emb-select');
        const status = panel.querySelector('.emb-status');
        const val = sel.value || null;
        status.textContent = 'Saving...';
        fetch('/api/dataset/' + encodeURIComponent(desc) + '/config' + sn, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ default_embedding: val })
        })
          .then(r => r.json())
          .then(data => {
            if (data.ok) status.textContent = val ? 'Saved: ' + val : 'Saved: none (default)';
            else status.textContent = 'Failed: ' + (data.error || 'unknown');
          })
          .catch(() => { status.textContent = 'Save failed'; });
      });
    });
  }

  function populateMoveFolders(currentDescriptor) {
    const select = document.getElementById('moveTargetFolder');
    select.innerHTML = '<option value="">Root (no subfolder)</option>';
    const folders = new Set();
    allDatasets.forEach(ds => {
      if (ds.descriptor !== currentDescriptor && ds.subfolder) {
        folders.add(ds.subfolder);
      }
    });
    allFolders.forEach(f => folders.add(f));
    [...folders].sort().forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f;
      select.appendChild(opt);
    });
  }

  confirmBtn?.addEventListener('click', function () {
    const desc = this.dataset.descriptor;
    const sn = this.dataset.source || '';
    if (!desc) return;
    fetch('/api/dataset/' + encodeURIComponent(desc) + '/delete' + sn, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        confirmModal.hide();
        if (data.ok) fetchDatasets();
        else alert('Delete failed: ' + (data.error || 'unknown'));
      })
      .catch(() => { alert('Delete failed'); confirmModal.hide(); });
  });

  document.getElementById('createFolderBtn')?.addEventListener('click', async function () {
    const name = document.getElementById('newFolderName').value.trim();
    const alert = document.getElementById('newFolderAlert');
    if (!name) {
      alert.textContent = 'Folder name required';
      alert.classList.remove('d-none');
      return;
    }
    alert.classList.add('d-none');
    const res = await fetch('/api/folders/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById('newFolderName').value = '';
      if (newFolderModal) newFolderModal.hide();
      fetchDatasets();
    } else {
      alert.textContent = data.error || 'Failed to create folder';
      alert.classList.remove('d-none');
    }
  });

  document.getElementById('newFolderBtn')?.addEventListener('click', () => {
    document.getElementById('newFolderAlert')?.classList.add('d-none');
    document.getElementById('newFolderName').value = '';
    if (newFolderModal) newFolderModal.show();
  });

  document.getElementById('moveConfirmBtn')?.addEventListener('click', async function () {
    const descriptor = this.dataset.descriptor;
    const source = this.dataset.source || '';
    const target = document.getElementById('moveTargetFolder').value;
    const alert = document.getElementById('moveAlert');
    alert.classList.add('d-none');
    const res = await fetch('/api/datasets/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ descriptor, source, target_folder: target })
    });
    const data = await res.json();
    if (data.ok) {
      if (moveModal) moveModal.hide();
      fetchDatasets();
    } else {
      alert.textContent = data.error || 'Failed to move dataset';
      alert.classList.remove('d-none');
    }
  });

  function fetchDatasets() {
    fetch('/api/datasets')
      .then(r => { if (r.status === 401) { window.location.href = '/login'; return null; } return r.json(); })
      .then(data => {
        if (!data) return;
        allDatasets = data;
        const activeStatus = {};
        data.forEach(ds => { activeStatus[ds.descriptor] = ds.status.toLowerCase(); });
        pendingLaunches.forEach(desc => {
          if (activeStatus[desc] && activeStatus[desc] !== 'stopped') {
            pendingLaunches.delete(desc);
          }
        });
        fetchFolders();
      })
      .catch(() => {
        gridEl.innerHTML = '<div class="text-center py-5 text-danger">Failed to load datasets. Is the gateway running?</div>';
      });
  }

  function fetchFolders() {
    fetch('/api/folders')
      .then(r => r.json())
      .then(data => {
        allFolders = data || [];
        render();
      })
      .catch(() => {});
  }

  searchInput?.addEventListener('input', render);
  sortSelect?.addEventListener('change', render);
  refreshBtn?.addEventListener('click', fetchDatasets);

  function startPoll() {
    fetch('/api/me').then(r => { if (r.status === 401) { window.location.href = '/login'; return null; } return r.json(); })
      .then(data => {
        if (!data || !data.authenticated) { window.location.href = '/login'; return; }
        fetchDatasets();
        pollTimer = setInterval(fetchDatasets, 10000);
      })
      .catch(() => { window.location.href = '/login'; });
  }

  startPoll();
})();
