// Telegram Web Dashboard - Main Script

document.addEventListener('DOMContentLoaded', function () {
    checkHealth();
});

// ─── Health check ─────────────────────────────────────────────────────────────

async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        const indicator = document.getElementById('health-indicator');
        if (indicator) {
            if (data.status === 'healthy') {
                indicator.textContent = 'Online';
                indicator.classList.add('status-active');
            } else {
                indicator.textContent = 'Offline';
                indicator.classList.add('status-inactive');
            }
        }
    } catch (err) {
        const indicator = document.getElementById('health-indicator');
        if (indicator) {
            indicator.textContent = 'Unreachable';
            indicator.classList.add('status-inactive');
        }
    }
}

// ─── Alert helper ─────────────────────────────────────────────────────────────

function showAlert(message, type = 'info') {
    const container = document.getElementById('alert-container');
    if (!container) return;
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    container.appendChild(alert);
    setTimeout(() => { if (alert.parentNode) alert.remove(); }, 6000);
}

// ─── Spinner helpers ──────────────────────────────────────────────────────────

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

// ─── Copy to clipboard ────────────────────────────────────────────────────────

function copyToClipboard(text, successMsg = 'Copied!') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => showAlert(successMsg, 'success'));
    } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showAlert(successMsg, 'success');
    }
}

function copyInputValue(inputId) {
    const el = document.getElementById(inputId);
    if (el) copyToClipboard(el.value, 'Link copied to clipboard!');
}

// ─── Channel AJAX helpers ─────────────────────────────────────────────────────

// Reads unique_link and channel_id embedded in the page by the template
function getChannelCtx() {
    return {
        uniqueLink: document.body.dataset.uniqueLink || '',
        channelId: document.body.dataset.channelId || '',
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
            showInviteResult(data.invite_link);
            showAlert('New invite link generated!', 'success');
        } else {
            showAlert('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
    } finally {
        setLoading(btnEl, false);
    }
}

function showInviteResult(link) {
    let box = document.getElementById('generatedInviteBox');
    if (!box) {
        box = document.createElement('div');
        box.id = 'generatedInviteBox';
        box.className = 'mt-3';
        const target = document.getElementById('inviteActionsArea');
        if (target) target.appendChild(box);
    }
    box.innerHTML = `
        <label class="form-label fw-semibold small text-muted">Generated Link</label>
        <div class="invite-link-box d-flex align-items-center gap-2">
            <input id="generatedInviteInput" type="text" class="form-control form-control-sm"
                   value="${link}" readonly>
            <button class="btn btn-sm btn-outline-secondary" onclick="copyInputValue('generatedInviteInput')">
                <i class="fas fa-copy"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger"
                    onclick="revokeInviteLink('${link}', this)">
                <i class="fas fa-ban"></i> Revoke
            </button>
        </div>`;
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
            showAlert('Invite link revoked.', 'warning');
            const box = document.getElementById('generatedInviteBox');
            if (box) box.remove();
        } else {
            showAlert('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
    } finally {
        setLoading(btnEl, false);
    }
}

// ─── Transfer ownership ───────────────────────────────────────────────────────

function openTransferModal() {
    const modal = new bootstrap.Modal(document.getElementById('transferModal'));
    modal.show();
}

async function submitTransfer(btnEl) {
    const input = document.getElementById('transferUserId');
    const targetUserId = (input ? input.value : '').trim();
    if (!targetUserId) { showAlert('Please enter a User ID.', 'warning'); return; }

    setLoading(btnEl, true);
    try {
        const res = await fetch(`${channelApiBase()}/transfer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_user_id: targetUserId }),
        });
        const data = await res.json();
        const modalEl = document.getElementById('transferModal');
        if (data.success) {
            bootstrap.Modal.getInstance(modalEl)?.hide();
            showAlert('Ownership transferred successfully!', 'success');
        } else {
            showAlert('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
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
            showAlert('Message deleted.', 'success');
        } else {
            showAlert('Error: ' + data.error, 'danger');
        }
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
    }
}

// ─── Members pagination ───────────────────────────────────────────────────────

let membersPage = 1;
const membersLimit = 50;

async function loadMembers(page, btnEl) {
    if (btnEl) setLoading(btnEl, true);
    const container = document.getElementById('membersTableBody');
    const status = document.getElementById('membersStatus');
    if (!container) return;

    try {
        const res = await fetch(`${channelApiBase()}/members?page=${page}&limit=${membersLimit}`);
        const data = await res.json();
        if (!data.success) { showAlert('Error: ' + data.error, 'danger'); return; }

        container.innerHTML = data.members.map(m => `
            <tr>
                <td>
                    <div class="d-flex align-items-center gap-2">
                        <div class="member-avatar" style="background:${m.avatar_color || '#0088cc'}">
                            ${m.avatar_letter || '?'}
                        </div>
                        <span>${escHtml(m.name)}</span>
                        ${m.is_bot ? '<span class="badge bg-info ms-1" style="font-size:.7rem">Bot</span>' : ''}
                    </div>
                </td>
                <td>${m.username ? `<a href="https://t.me/${m.username}" target="_blank">@${escHtml(m.username)}</a>` : '<span class="text-muted">—</span>'}</td>
                <td><span class="badge bg-light text-dark">${escHtml(m.status)}</span></td>
            </tr>`).join('');

        membersPage = page;
        if (status) {
            status.textContent = `Page ${page} · Showing ${data.members.length} members`;
        }
        document.getElementById('membersPrevBtn').disabled = page <= 1;
        document.getElementById('membersNextBtn').disabled = data.members.length < membersLimit;
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
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
    const status = document.getElementById('messagesStatus');
    if (!container) return;

    try {
        const res = await fetch(`${channelApiBase()}/messages?page=${page}&limit=${messagesLimit}`);
        const data = await res.json();
        if (!data.success) { showAlert('Error: ' + data.error, 'danger'); return; }

        container.innerHTML = data.messages.map(msg => `
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
                        ${msg.short_text ? escHtml(msg.short_text) : (msg.media_label ? `<span class="text-muted">${msg.media_label}</span>` : '<span class="text-muted">Empty message</span>')}
                    </p>
                </div>
            </div>`).join('');

        messagesPage = page;
        if (status) status.textContent = `Page ${page} · Showing ${data.messages.length} messages`;
        document.getElementById('messagesPrevBtn').disabled = page <= 1;
        document.getElementById('messagesNextBtn').disabled = data.messages.length < messagesLimit;
    } catch (e) {
        showAlert('Network error: ' + e.message, 'danger');
    } finally {
        if (btnEl) setLoading(btnEl, false);
    }
}

function messagesPrev() { if (messagesPage > 1) loadMessages(messagesPage - 1); }
function messagesNext() { loadMessages(messagesPage + 1); }

// ─── Member search filter ─────────────────────────────────────────────────────

function filterMembers(q) {
    q = q.toLowerCase();
    document.querySelectorAll('#membersTableBody tr').forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function fmtNum(n) {
    if (n == null) return '';
    return Number(n).toLocaleString();
}
