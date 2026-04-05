// Telegram Web Dashboard - Main Script

document.addEventListener('DOMContentLoaded', function () {
    checkHealth();
});

// ─── Health check ─────────────────────────────────────────────────────────────

async function checkHealth() {
    try {
        const res = await fetch('/health');
        const data = await res.json();
        const el = document.getElementById('health-indicator');
        if (el) {
            if (data.status === 'healthy') {
                el.textContent = 'Online';
                el.classList.add('status-active');
            } else {
                el.textContent = 'Offline';
                el.classList.add('status-inactive');
            }
        }
    } catch {
        const el = document.getElementById('health-indicator');
        if (el) { el.textContent = 'Unreachable'; el.classList.add('status-inactive'); }
    }
}

// ─── Alert bar (top of page) ──────────────────────────────────────────────────

function showAlert(message, type = 'info') {
    const container = document.getElementById('alert-container');
    if (!container) return;
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show`;
    div.innerHTML = `${escHtml(message)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    container.appendChild(div);
    setTimeout(() => { if (div.parentNode) div.remove(); }, 6000);
}

// ─── Toast (bottom-right) ─────────────────────────────────────────────────────

function showToast(message, type = 'secondary') {
    const container = document.getElementById('toast-container');
    if (!container) { showAlert(message, type); return; }

    const iconMap = {
        success: 'fa-check-circle text-success',
        danger:  'fa-exclamation-circle text-danger',
        warning: 'fa-exclamation-triangle text-warning',
        info:    'fa-info-circle text-info',
        secondary: 'fa-circle-dot text-secondary',
    };
    const icon = iconMap[type] || iconMap.secondary;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
        <div class="toast align-items-center border-0 shadow" role="alert" aria-live="assertive">
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center gap-2">
                    <i class="fas ${icon}"></i>
                    <span>${escHtml(message)}</span>
                </div>
                <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>`;
    const toastEl = wrapper.firstElementChild;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 4500 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

// ─── Loading overlay ──────────────────────────────────────────────────────────

function showOverlay() {
    const el = document.getElementById('loading-overlay');
    if (el) el.classList.remove('d-none');
}

function hideOverlay() {
    const el = document.getElementById('loading-overlay');
    if (el) el.classList.add('d-none');
}

// ─── Button spinner helpers ───────────────────────────────────────────────────

function setLoading(btnEl, loading) {
    if (!btnEl) return;
    if (loading) {
        btnEl.dataset.origHtml = btnEl.innerHTML;
        btnEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Loading…';
        btnEl.disabled = true;
    } else {
        btnEl.innerHTML = btnEl.dataset.origHtml || btnEl.innerHTML;
        btnEl.disabled = false;
    }
}

// ─── Copy helpers ─────────────────────────────────────────────────────────────

function copyToClipboard(text, msg = 'Copied to clipboard!') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showToast(msg, 'success'))
            .catch(() => _fallbackCopy(text, msg));
    } else {
        _fallbackCopy(text, msg);
    }
}

function _fallbackCopy(text, msg) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); showToast(msg, 'success'); }
    catch { showToast('Could not copy — please copy manually.', 'warning'); }
    document.body.removeChild(ta);
}

function copyInputValue(inputId, msg) {
    const el = document.getElementById(inputId);
    if (el) copyToClipboard(el.value, msg || 'Link copied!');
}

// ─── Channel AJAX context ─────────────────────────────────────────────────────

function getChannelCtx() {
    return {
        uniqueLink: document.body.dataset.uniqueLink || '',
        channelId:  document.body.dataset.channelId  || '',
    };
}

function channelApiBase() {
    const { uniqueLink, channelId } = getChannelCtx();
    return `/channel/${uniqueLink}/${channelId}`;
}

// ─── Generate invite link ─────────────────────────────────────────────────────

async function generateInviteLink(btnEl) {
    setLoading(btnEl, true);
    try {
        const res = await fetch(`${channelApiBase()}/invite`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            _showInviteResult(data.invite_link);
            showToast('New invite link generated!', 'success');
        } else {
            showToast('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'danger');
    } finally {
        setLoading(btnEl, false);
    }
}

function _showInviteResult(link) {
    // Show in both the Info tab and the Actions tab invite areas
    ['inviteActionsArea', 'inviteActionsAreaActions'].forEach(id => {
        let box = document.getElementById('generatedInviteBox_' + id);
        if (!box) {
            box = document.createElement('div');
            box.id = 'generatedInviteBox_' + id;
            box.className = 'mt-3';
            const target = document.getElementById(id);
            if (target) target.appendChild(box);
        }
        box.innerHTML = `
            <label class="form-label fw-semibold small text-muted">Generated Link</label>
            <div class="invite-link-box d-flex align-items-center gap-2 flex-wrap">
                <input id="genInviteInput_${id}" type="text" class="form-control form-control-sm"
                       value="${escHtml(link)}" readonly style="min-width:0;flex:1;">
                <button class="btn btn-sm btn-outline-secondary"
                        onclick="copyInputValue('genInviteInput_${id}')">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger"
                        onclick="revokeInviteLink('${escHtml(link)}', this)">
                    <i class="fas fa-ban"></i> Revoke
                </button>
            </div>`;
    });
}

// ─── Revoke invite link ───────────────────────────────────────────────────────

async function revokeInviteLink(inviteLink, btnEl) {
    if (!confirm('Revoke this invite link? It will stop working immediately.')) return;
    setLoading(btnEl, true);
    try {
        const res = await fetch(`${channelApiBase()}/revoke_invite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ invite_link: inviteLink }),
        });
        const data = await res.json();
        if (data.success) {
            showToast('Invite link revoked.', 'warning');
            document.querySelectorAll('[id^="generatedInviteBox_"]').forEach(el => el.remove());
        } else {
            showToast('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'danger');
    } finally {
        setLoading(btnEl, false);
    }
}

// ─── Transfer ownership ───────────────────────────────────────────────────────

function openTransferModal() {
    // Reset fields
    const uid = document.getElementById('transferUserId');
    const pwd = document.getElementById('transferPassword');
    const err = document.getElementById('transferError');
    if (uid) uid.value = '';
    if (pwd) pwd.value = '';
    if (err) { err.classList.add('d-none'); err.textContent = ''; }
    const modal = new bootstrap.Modal(document.getElementById('transferModal'));
    modal.show();
}

function togglePasswordVisibility(inputId, btnEl) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    const icon = btnEl.querySelector('i');
    if (icon) {
        icon.classList.toggle('fa-eye', !isHidden);
        icon.classList.toggle('fa-eye-slash', isHidden);
    }
}

async function submitTransfer(btnEl) {
    const uidInput = document.getElementById('transferUserId');
    const pwdInput = document.getElementById('transferPassword');
    const errBox   = document.getElementById('transferError');

    const targetUserId = (uidInput ? uidInput.value : '').trim();
    const password     = (pwdInput ? pwdInput.value : '').trim();

    function showInlineError(msg) {
        if (errBox) {
            errBox.textContent = msg;
            errBox.classList.remove('d-none');
        } else {
            showToast(msg, 'danger');
        }
    }

    if (errBox) errBox.classList.add('d-none');
    if (!targetUserId) { showInlineError('Please enter the target User ID.'); return; }
    if (!password)     { showInlineError('Please enter your 2FA password.'); return; }

    if (!confirm('Are you sure? This will permanently transfer ownership. This action cannot be undone.')) return;

    setLoading(btnEl, true);
    try {
        const res = await fetch(`${channelApiBase()}/transfer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_user_id: targetUserId, password }),
        });
        const data = await res.json();
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('transferModal'))?.hide();
            showToast('Ownership transferred successfully!', 'success');
        } else {
            showInlineError(data.error || 'Transfer failed.');
        }
    } catch (e) {
        showInlineError('Network error: ' + e.message);
    } finally {
        setLoading(btnEl, false);
    }
}

// ─── Delete message ───────────────────────────────────────────────────────────

async function deleteMessage(messageId, rowEl) {
    if (!confirm('Delete this message? This action cannot be undone.')) return;
    try {
        const res = await fetch(`${channelApiBase()}/delete_message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId }),
        });
        const data = await res.json();
        if (data.success) {
            if (rowEl) {
                rowEl.style.transition = 'opacity .3s';
                rowEl.style.opacity = '0';
                setTimeout(() => rowEl.remove(), 300);
            }
            showToast('Message deleted.', 'success');
        } else {
            showToast('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'danger');
    }
}

// ─── Members pagination ───────────────────────────────────────────────────────

let membersPage = 1;
const membersLimit = 50;

async function loadMembers(page, btnEl) {
    if (btnEl) setLoading(btnEl, true);
    const tbody  = document.getElementById('membersTableBody');
    const status = document.getElementById('membersStatus');
    if (!tbody) return;

    try {
        const res = await fetch(`${channelApiBase()}/members?page=${page}&limit=${membersLimit}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) { showToast('Error: ' + data.error, 'danger'); return; }

        tbody.innerHTML = data.members.length
            ? data.members.map(m => `
                <tr>
                    <td>
                        <div class="d-flex align-items-center gap-2">
                            <div class="member-avatar" style="background:${escHtml(m.avatar_color || '#0088cc')}">
                                ${escHtml(m.avatar_letter || '?')}
                            </div>
                            <span>${escHtml(m.name)}</span>
                            ${m.is_bot ? '<span class="badge bg-info ms-1" style="font-size:.7rem">Bot</span>' : ''}
                        </div>
                    </td>
                    <td>${m.username
                        ? `<a href="https://t.me/${escHtml(m.username)}" target="_blank">@${escHtml(m.username)}</a>`
                        : '<span class="text-muted">—</span>'}</td>
                    <td><span class="badge bg-light text-dark">${escHtml(m.status)}</span></td>
                </tr>`).join('')
            : '<tr><td colspan="3" class="text-center text-muted py-4">No members found.</td></tr>';

        membersPage = page;
        if (status) status.textContent = `Page ${page} · Showing ${data.members.length} members`;

        const prevBtn = document.getElementById('membersPrevBtn');
        const nextBtn = document.getElementById('membersNextBtn');
        if (prevBtn) prevBtn.disabled = page <= 1;
        if (nextBtn) nextBtn.disabled = data.members.length < membersLimit;
    } catch (e) {
        showToast('Failed to load members: ' + e.message, 'danger');
    } finally {
        if (btnEl) setLoading(btnEl, false);
    }
}

function membersPrev() { if (membersPage > 1) loadMembers(membersPage - 1); }
function membersNext() { loadMembers(membersPage + 1); }

// ─── Messages pagination ──────────────────────────────────────────────────────

let messagesPage = 1;
const messagesLimit = 30;

async function loadMessages(page, btnEl) {
    if (btnEl) setLoading(btnEl, true);
    const container = document.getElementById('messagesContainer');
    const status    = document.getElementById('messagesStatus');
    if (!container) return;

    try {
        const res = await fetch(`${channelApiBase()}/messages?page=${page}&limit=${messagesLimit}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) { showToast('Error: ' + data.error, 'danger'); return; }

        container.innerHTML = data.messages.length
            ? data.messages.map(msg => `
                <div class="msg-card card mb-2" id="msg-${msg.id}">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-start flex-wrap gap-1 mb-1">
                            <small class="fw-semibold text-primary">${escHtml(msg.sender || 'Channel')}</small>
                            <div class="d-flex align-items-center gap-2 flex-wrap">
                                ${msg.views ? `<small class="text-muted"><i class="fas fa-eye me-1"></i>${fmtNum(msg.views)}</small>` : ''}
                                ${msg.is_pinned ? '<span class="badge bg-warning text-dark">📌 Pinned</span>' : ''}
                                <small class="text-muted">${escHtml(msg.date)}</small>
                                <button class="btn btn-xs btn-outline-danger delete-msg-btn"
                                        onclick="deleteMessage(${msg.id}, document.getElementById('msg-${msg.id}'))">
                                    <i class="fas fa-trash-alt"></i>
                                </button>
                            </div>
                        </div>
                        <p class="mb-0 small">
                            ${msg.short_text
                                ? escHtml(msg.short_text)
                                : (msg.media_label
                                    ? `<span class="text-muted">${escHtml(msg.media_label)}</span>`
                                    : '<span class="text-muted">Empty message</span>')}
                        </p>
                    </div>
                </div>`).join('')
            : '<div class="text-center text-muted py-4"><i class="fas fa-comment fa-2x mb-2"></i><p>No messages found.</p></div>';

        messagesPage = page;
        if (status) status.textContent = `Page ${page} · Showing ${data.messages.length} messages`;

        const prevBtn = document.getElementById('messagesPrevBtn');
        const nextBtn = document.getElementById('messagesNextBtn');
        if (prevBtn) prevBtn.disabled = page <= 1;
        if (nextBtn) nextBtn.disabled = data.messages.length < messagesLimit;
    } catch (e) {
        showToast('Failed to load messages: ' + e.message, 'danger');
    } finally {
        if (btnEl) setLoading(btnEl, false);
    }
}

function messagesPrev() { if (messagesPage > 1) loadMessages(messagesPage - 1); }
function messagesNext() { loadMessages(messagesPage + 1); }

// ─── Member search filter ─────────────────────────────────────────────────────

function filterMembers(q) {
    q = q.toLowerCase();
    document.querySelectorAll('#membersTableBody tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function escHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
}

function fmtNum(n) {
    if (n == null) return '';
    return Number(n).toLocaleString();
}
