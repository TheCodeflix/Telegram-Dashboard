// Telegram Web Dashboard - Main Script

document.addEventListener('DOMContentLoaded', function () {
    checkHealth();
    loadDeferredPhotos();
    observeDeferredThumbnails();
    initializeChannelTabs();
    initializeDashboardReplica();
});

function initializeDashboardReplica() {
    const dataElement = document.getElementById('dashboard-data');
    const list = document.getElementById('items-list');
    if (!dataElement || !list) return;

    let chats;
    try {
        chats = JSON.parse(dataElement.textContent);
    } catch (error) {
        console.error('Could not read dashboard chat data:', error);
        return;
    }

    let activeTab = 'groups';
    const searchInput = document.getElementById('search-input');
    const clearSearch = document.getElementById('clear-search');
    const emptyState = document.getElementById('empty-state');
    const profileView = document.getElementById('profile-view');
    const mainListView = document.getElementById('main-list-view');
    const chatView = document.getElementById('chat-view');
    const messageContainer = document.getElementById('chat-messages-container');
    const chatDetailView = document.getElementById('chat-detail-view');
    const chatDetailContent = document.getElementById('chat-detail-content');
    const chatMenu = document.getElementById('chat-menu-dropdown');
    let activeChat = null;
    let requestToken = 0;
    let loadingMessages = false;
    let hasMoreMessages = false;
    let currentMessagesPage = 1;

    function render() {
        const query = (searchInput?.value || '').trim().toLocaleLowerCase();
        const filtered = chats.filter(chat => {
            if (chat.category !== activeTab) return false;
            return !query || [
                chat.title, chat.username, chat.chat_id, chat.last_message, chat.type
            ].some(value => String(value || '').toLocaleLowerCase().includes(query));
        });

        list.innerHTML = filtered.map(chat => {
            const title = escHtml(chat.title || 'Unknown');
            const preview = escHtml(
                chat.last_message
                || (chat.username ? `@${chat.username}` : '')
                || (chat.member_count ? `${fmtNum(chat.member_count)} members` : '')
                || (chat.type === 'bot' ? 'Bot' : chat.type || 'Telegram chat')
            );
            const date = formatDialogDate(chat.last_message_date);
            const unread = Number(chat.unread_count) || 0;
            const background = escHtml(chat.avatar_color || '#248bfe');
            const letter = escHtml(chat.avatar_letter || title[0] || '?');
            return `<li class="telegram-chat-row">
                <a class="telegram-chat-link" href="${escHtml(chat.url)}" data-chat-id="${escHtml(chat.chat_id)}">
                    <span class="telegram-chat-avatar" data-photo-fallback style="background:${background}">${letter}</span>
                    <img class="telegram-chat-avatar" data-photo-chat-id="${Number(chat.chat_id)}"
                         data-photo-endpoint="${escHtml(document.querySelector('[data-photo-endpoint]')?.dataset.photoEndpoint || '')}"
                         alt="" hidden>
                    <span class="telegram-chat-content">
                        <span class="telegram-chat-title-line">
                            <span class="telegram-chat-title">${title}</span>
                            ${chat.is_verified ? '<i class="fa-solid fa-circle-check telegram-chat-verified" title="Verified"></i>' : ''}
                        </span>
                        <span class="telegram-chat-preview">${preview}</span>
                    </span>
                    <span class="telegram-chat-meta">
                        ${date ? `<time>${escHtml(date)}</time>` : ''}
                        ${unread > 0 ? `<span class="telegram-unread-count">${unread > 99 ? '99+' : unread}</span>` : ''}
                    </span>
                </a>
            </li>`;
        }).join('');

        emptyState.hidden = filtered.length > 0;
        if (clearSearch) clearSearch.hidden = !query;
        document.querySelectorAll('.telegram-tab-btn').forEach(button => {
            const active = button.dataset.tab === activeTab;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        loadDeferredPhotos(list);
    }

    function showChat(chat) {
        activeChat = chat;
        requestToken += 1;
        loadingMessages = false;
        hasMoreMessages = false;
        currentMessagesPage = 1;
        document.body.dataset.channelId = String(chat.chat_id);
        document.body.dataset.chatUsername = chat.username || '';

        const title = document.getElementById('chat-header-name');
        const status = document.getElementById('chat-header-status');
        const avatarRoot = document.getElementById('chat-header-avatar');
        const menuButton = document.getElementById('chat-menu-btn');
        if (title) title.textContent = chat.title || 'Unknown';
        if (status) {
            status.textContent = chat.member_count
                ? `${fmtNum(chat.member_count)} members`
                : (chat.username ? `@${chat.username}` : (chat.type || chat.category || 'Telegram chat'));
        }
        if (avatarRoot) {
            const fallback = document.createElement('span');
            fallback.className = 'telegram-chat-avatar chat-header-avatar-fallback';
            fallback.dataset.photoFallback = '';
            fallback.textContent = chat.avatar_letter || (chat.title || '?')[0];
            fallback.style.background = chat.avatar_color || '#248bfe';
            const image = document.createElement('img');
            image.className = 'telegram-chat-avatar chat-header-avatar-image';
            image.dataset.photoChatId = String(chat.chat_id);
            image.dataset.photoEndpoint = chatView.dataset.photoEndpoint || '';
            image.alt = '';
            image.hidden = true;
            avatarRoot.replaceChildren(fallback, image);
        }
        if (menuButton) {
            menuButton.hidden = chat.category === 'users';
            menuButton.setAttribute('aria-expanded', 'false');
        }
        if (chatMenu) chatMenu.hidden = true;
        if (chatDetailView) chatDetailView.hidden = true;
        if (messageContainer) {
            messageContainer.innerHTML = '<div class="telegram-chat-loading" role="status"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>Loading chat history…</span></div>';
        }
        if (mainListView) mainListView.hidden = true;
        if (profileView) profileView.hidden = true;
        if (chatView) chatView.hidden = false;
        loadDeferredPhotos(chatView);
        loadChatMessages(1, requestToken);
    }

    async function loadChatMessages(page, token = requestToken) {
        if (!activeChat || !messageContainer || loadingMessages) return;
        loadingMessages = true;
        const isOlderPage = page > 1;
        const oldHeight = messageContainer.scrollHeight;
        const oldTop = messageContainer.scrollTop;
        if (!isOlderPage) {
            messageContainer.innerHTML = '<div class="telegram-chat-loading" role="status"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>Loading chat history…</span></div>';
        }

        try {
            const response = await fetch(`${channelApiBase()}/messages?page=${page}&limit=30`);
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || `HTTP ${response.status}`);
            }
            if (token !== requestToken) return;
            if (!Array.isArray(result.messages)) throw new Error('Invalid chat history response.');

            const rendered = result.messages.map(renderDashboardMessage).join('');
            messageContainer.querySelector('.telegram-history-retry')?.remove();
            if (isOlderPage) {
                if (rendered) messageContainer.insertAdjacentHTML('afterbegin', rendered);
                messageContainer.scrollTop = oldTop + messageContainer.scrollHeight - oldHeight;
            } else {
                messageContainer.innerHTML = rendered || '<div class="telegram-chat-empty">No messages found.</div>';
                requestAnimationFrame(() => { messageContainer.scrollTop = messageContainer.scrollHeight; });
            }
            currentMessagesPage = page;
            hasMoreMessages = result.messages.length >= 30;
            observeDeferredThumbnails(messageContainer);
        } catch (error) {
            if (token !== requestToken) return;
            if (isOlderPage) {
                hasMoreMessages = false;
                messageContainer.querySelector('.telegram-history-retry')?.remove();
                messageContainer.insertAdjacentHTML('afterbegin', `<div class="telegram-history-retry" role="alert">
                    <span>Could not load older messages: ${escHtml(error.message)}</span>
                    <button class="telegram-chat-retry" type="button" data-retry-message-page="${page}">Retry</button>
                </div>`);
            } else {
                messageContainer.innerHTML = `<div class="telegram-chat-error" role="alert">
                    <span>Could not load chat history: ${escHtml(error.message)}</span>
                    <button class="telegram-chat-retry" type="button" data-retry-chat>Retry</button>
                </div>`;
            }
        } finally {
            if (token === requestToken) loadingMessages = false;
        }
    }

    function renderDashboardMessage(message) {
        const id = Number(message.id) || 0;
        const mediaType = String(message.media_type || '').toUpperCase();
        const mediaLabel = message.media_label || 'Media';
        const mediaIcon = message.media_icon || 'fa-paperclip';
        const mediaName = message.media_name || message.media_mime_type || '';
        const text = message.text || message.short_text || '';
        const hasMedia = Boolean(message.has_media);
        const thumbnail = message.media_preview
            ? `<div class="telegram-media-thumbnail"><img src="${escHtml(message.media_preview)}" alt="${escHtml(mediaLabel)} thumbnail" loading="lazy">
                ${['VIDEO', 'ANIMATION', 'VIDEO_NOTE'].includes(mediaType)
                    ? '<span class="telegram-media-play"><i class="fa-solid fa-play"></i></span>' : ''}</div>`
            : `<div class="telegram-media-thumbnail media-thumbnail-placeholder"
                    data-message-id="${id}" data-media-type="${escHtml(mediaType)}"
                    data-media-label="${escHtml(mediaLabel)}">
                    <i class="fa-solid ${escHtml(mediaIcon)}"></i>
               </div>`;
        const media = hasMedia
            ? `<div class="telegram-message-media">${thumbnail}
                <div class="telegram-message-media-info">
                    <strong>${escHtml(mediaLabel)}</strong>
                    ${mediaName ? `<span>${escHtml(mediaName)}</span>` : ''}
                    ${message.media_duration ? `<span>${escHtml(message.media_duration)} sec</span>` : ''}
                </div></div>`
            : '';
        const time = message.date
            ? formatMessageTime(message.date)
            : '';

        return `<article class="telegram-message" id="msg-${id}">
            <header class="telegram-message-header">
                <span class="telegram-message-sender">${escHtml(message.sender || activeChat?.title || 'Telegram')}</span>
                <time>${escHtml(time)}</time>
                <div class="telegram-message-action-wrap">
                    <button type="button" class="telegram-message-action-button"
                            aria-label="Message actions" aria-expanded="false">
                        <i class="fa-solid fa-ellipsis"></i>
                    </button>
                    <div class="telegram-message-menu" hidden>
                        <button type="button" data-copy-message="${id}"><i class="fa-solid fa-link"></i>Copy message link</button>
                        <button type="button" data-delete-message="${id}"><i class="fa-solid fa-trash"></i>Delete message</button>
                    </div>
                </div>
            </header>
            ${media}
            ${text ? `<p class="telegram-message-text">${escHtml(text)}</p>` : (hasMedia ? '' : '<p class="telegram-message-text telegram-message-muted">Empty message</p>')}
            ${message.views ? `<span class="telegram-message-views"><i class="fa-solid fa-eye"></i> ${fmtNum(message.views)}</span>` : ''}
        </article>`;
    }

    function formatMessageTime(value) {
        const date = new Date(String(value).replace(' ', 'T'));
        return Number.isNaN(date.getTime())
            ? String(value)
            : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }

    function showChatDetail(title, content) {
        if (!chatDetailView || !chatDetailContent) return;
        document.getElementById('chat-detail-title').textContent = title;
        chatDetailContent.innerHTML = content;
        chatDetailView.hidden = false;
    }

    async function loadChatMembers(page = 1) {
        if (!activeChat || !chatDetailContent) return;
        const chatId = activeChat.chat_id;
        chatDetailContent.innerHTML = '<div class="telegram-chat-loading"><span class="spinner-border spinner-border-sm"></span><span>Loading members…</span></div>';
        try {
            const response = await fetch(`${channelApiBase()}/members?page=${page}&limit=50`);
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || `HTTP ${response.status}`);
            if (String(activeChat?.chat_id) !== String(chatId)) return;
            const rows = result.members.map(member => `<div class="telegram-member-row">
                <span class="telegram-member-avatar" style="background:${escHtml(member.avatar_color || '#248bfe')}">${escHtml(member.avatar_letter || '?')}</span>
                <span class="telegram-member-info"><strong>${escHtml(member.name || 'Unknown')}</strong>
                    <small>${member.username ? `@${escHtml(member.username)}` : escHtml(member.status || 'Member')}</small></span>
                ${member.is_bot ? '<span class="telegram-member-bot">Bot</span>' : ''}
            </div>`).join('');
            const more = result.members.length >= 50
                ? `<button type="button" class="telegram-detail-more" data-members-page="${page + 1}">Load more members</button>`
                : '';
            chatDetailContent.innerHTML = rows || '<p class="telegram-chat-empty">No member data available.</p>';
            chatDetailContent.insertAdjacentHTML('beforeend', more);
        } catch (error) {
            if (String(activeChat?.chat_id) !== String(chatId)) return;
            chatDetailContent.innerHTML = `<div class="telegram-chat-error" role="alert">Could not load members: ${escHtml(error.message)}
                <button type="button" class="telegram-chat-retry" data-retry-members="${page}">Retry</button></div>`;
        }
    }

    async function handleChatAction(action) {
        if (!activeChat) return;
        if (action === 'members') {
            showChatDetail('Members', '');
            await loadChatMembers(1);
        } else if (action === 'invite') {
            const chatId = activeChat.chat_id;
            showChatDetail('Invite Link', '<div class="telegram-chat-loading"><span class="spinner-border spinner-border-sm"></span><span>Generating invite link…</span></div>');
            try {
                const response = await fetch(`${channelApiBase()}/invite`, { method: 'POST' });
                const result = await response.json();
                if (!response.ok || !result.success) throw new Error(result.error || `HTTP ${response.status}`);
                if (String(activeChat?.chat_id) !== String(chatId)) return;
                chatDetailContent.innerHTML = `<p class="telegram-detail-description">Invite link for ${escHtml(activeChat.title)}:</p>
                    <div class="telegram-invite-box"><input type="text" readonly value="${escHtml(result.invite_link)}" aria-label="Invite link">
                    <button type="button" data-copy-invite><i class="fa-solid fa-copy"></i><span>Copy</span></button></div>`;
            } catch (error) {
                if (String(activeChat?.chat_id) !== String(chatId)) return;
                chatDetailContent.innerHTML = `<div class="telegram-chat-error" role="alert">Could not generate invite link: ${escHtml(error.message)}</div>`;
            }
        } else if (action === 'ownership') {
            showChatDetail('Transfer Ownership', `<p class="telegram-detail-description">Transfer ownership of ${escHtml(activeChat.title)} to another Telegram user.</p>
                <form id="dashboard-transfer-form" class="telegram-transfer-form">
                    <label for="dashboard-transfer-user">Target user ID</label>
                    <input id="dashboard-transfer-user" name="user_id" type="number" required>
                    <label for="dashboard-transfer-password">Two-step verification password</label>
                    <input id="dashboard-transfer-password" name="password" type="password" required autocomplete="current-password">
                    <button type="submit">Transfer ownership</button>
                    <p class="telegram-form-error" id="dashboard-transfer-error" role="alert" hidden></p>
                </form>`);
        }
    }

    list.addEventListener('click', event => {
        const link = event.target.closest('.telegram-chat-link');
        if (!link) return;
        event.preventDefault();
        const chat = chats.find(item => String(item.chat_id) === link.dataset.chatId);
        if (chat) showChat(chat);
    });

    messageContainer?.addEventListener('scroll', () => {
        if (messageContainer.scrollTop <= 70 && hasMoreMessages && !loadingMessages) {
            loadChatMessages(currentMessagesPage + 1);
        }
    });
    messageContainer?.addEventListener('click', event => {
        const retry = event.target.closest('[data-retry-chat]');
        if (retry) loadChatMessages(1);
        const retryOlder = event.target.closest('[data-retry-message-page]');
        if (retryOlder) loadChatMessages(Number(retryOlder.dataset.retryMessagePage));

        const actionButton = event.target.closest('.telegram-message-action-button');
        if (actionButton) {
            const menu = actionButton.nextElementSibling;
            const shouldOpen = menu.hidden;
            messageContainer.querySelectorAll('.telegram-message-menu').forEach(item => { item.hidden = true; });
            messageContainer.querySelectorAll('.telegram-message-action-button').forEach(item => item.setAttribute('aria-expanded', 'false'));
            menu.hidden = !shouldOpen;
            actionButton.setAttribute('aria-expanded', String(shouldOpen));
        }
        const copyButton = event.target.closest('[data-copy-message]');
        if (copyButton) {
            copyMessageLink(Number(copyButton.dataset.copyMessage));
            const menu = copyButton.closest('.telegram-message-menu');
            if (menu) menu.hidden = true;
        }
        const deleteButton = event.target.closest('[data-delete-message]');
        if (deleteButton) {
            const messageId = Number(deleteButton.dataset.deleteMessage);
            const menu = deleteButton.closest('.telegram-message-menu');
            if (menu) menu.hidden = true;
            deleteMessage(messageId, document.getElementById(`msg-${messageId}`));
        }
    });
    document.getElementById('back-to-list-btn')?.addEventListener('click', () => {
        requestToken += 1;
        loadingMessages = false;
        if (chatView) chatView.hidden = true;
        if (mainListView) mainListView.hidden = false;
        if (chatMenu) chatMenu.hidden = true;
    });
    document.getElementById('back-from-chat-detail-btn')?.addEventListener('click', () => {
        if (chatDetailView) chatDetailView.hidden = true;
    });
    document.getElementById('chat-menu-btn')?.addEventListener('click', event => {
        event.stopPropagation();
        if (!chatMenu) return;
        chatMenu.hidden = !chatMenu.hidden;
        event.currentTarget.setAttribute('aria-expanded', String(!chatMenu.hidden));
    });
    chatMenu?.addEventListener('click', event => {
        const button = event.target.closest('[data-action]');
        if (!button) return;
        chatMenu.hidden = true;
        document.getElementById('chat-menu-btn')?.setAttribute('aria-expanded', 'false');
        handleChatAction(button.dataset.action);
    });
    document.addEventListener('click', event => {
        if (chatMenu && !chatMenu.hidden && !chatMenu.contains(event.target)
            && !document.getElementById('chat-menu-btn')?.contains(event.target)) {
            chatMenu.hidden = true;
            document.getElementById('chat-menu-btn')?.setAttribute('aria-expanded', 'false');
        }
    });
    chatDetailContent?.addEventListener('click', event => {
        const more = event.target.closest('[data-members-page]');
        if (more) loadChatMembers(Number(more.dataset.membersPage));
        const retry = event.target.closest('[data-retry-members]');
        if (retry) loadChatMembers(Number(retry.dataset.retryMembers));
        if (event.target.closest('[data-copy-invite]')) {
            const input = chatDetailContent.querySelector('.telegram-invite-box input');
            if (input) copyToClipboard(input.value, 'Invite link copied!');
        }
    });
    chatDetailContent?.addEventListener('submit', async event => {
        if (event.target.id !== 'dashboard-transfer-form') return;
        event.preventDefault();
        const form = event.target;
        const errorBox = form.querySelector('#dashboard-transfer-error');
        const submitButton = form.querySelector('button[type="submit"]');
        const formData = new FormData(form);
        if (!confirm('Transfer ownership? This action cannot be undone.')) return;
        submitButton.disabled = true;
        try {
            const response = await fetch(`${channelApiBase()}/transfer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_user_id: formData.get('user_id'),
                    password: formData.get('password')
                })
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || `HTTP ${response.status}`);
            chatDetailContent.innerHTML = '<p class="telegram-chat-empty">Ownership transferred successfully.</p>';
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.hidden = false;
        } finally {
            submitButton.disabled = false;
        }
    });

    document.querySelectorAll('.telegram-tab-btn').forEach(button => {
        button.addEventListener('click', () => {
            activeTab = button.dataset.tab;
            const scrollArea = document.getElementById('list-scroll-area');
            if (scrollArea) scrollArea.scrollTop = 0;
            render();
        });
    });

    searchInput?.addEventListener('input', render);
    clearSearch?.addEventListener('click', () => {
        searchInput.value = '';
        searchInput.focus();
        render();
    });

    document.getElementById('open-profile-btn')?.addEventListener('click', () => {
        if (mainListView) mainListView.hidden = true;
        if (profileView) profileView.hidden = false;
        loadDeferredPhotos(profileView);
    });
    document.getElementById('back-from-profile-btn')?.addEventListener('click', () => {
        if (profileView) profileView.hidden = true;
        if (mainListView) mainListView.hidden = false;
    });

    render();
}

function formatDialogDate(value) {
    if (!value) return '';
    const date = new Date(String(value).replace(' ', 'T'));
    if (Number.isNaN(date.getTime())) return '';
    const today = new Date();
    if (date.toDateString() === today.toDateString()) {
        return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

const thumbnailQueues = new Map();
const thumbnailTimers = new Map();
const activeThumbnailRequests = new Set();
let thumbnailObserver;
let thumbnailObserverRoot;

function observeDeferredThumbnails(root = document) {
    const placeholders = root.querySelectorAll
        ? root.querySelectorAll('.media-thumbnail-placeholder:not([data-thumbnail-loaded])')
        : [];
    if (!placeholders.length) return;

    if (!('IntersectionObserver' in window)) {
        placeholders.forEach(enqueueThumbnail);
        return;
    }

    const scrollRoot = root?.id === 'messagesContainer' || root?.id === 'chat-messages-container'
        ? root
        : (document.getElementById('messagesContainer') || document.getElementById('chat-messages-container'));
    if (!thumbnailObserver || thumbnailObserverRoot !== scrollRoot) {
        thumbnailObserver?.disconnect();
        thumbnailObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                thumbnailObserver.unobserve(entry.target);
                enqueueThumbnail(entry.target);
            });
        }, { root: scrollRoot, rootMargin: '180px' });
        thumbnailObserverRoot = scrollRoot;
    }
    placeholders.forEach(placeholder => thumbnailObserver.observe(placeholder));
}

function enqueueThumbnail(placeholder) {
    if (placeholder.dataset.thumbnailQueued) return;
    placeholder.dataset.thumbnailQueued = 'true';
    const endpoint = `${channelApiBase()}/thumbnails`;
    if (!thumbnailQueues.has(endpoint)) thumbnailQueues.set(endpoint, []);
    thumbnailQueues.get(endpoint).push(placeholder);
    scheduleThumbnailBatch(endpoint);
}

function scheduleThumbnailBatch(endpoint) {
    if (thumbnailTimers.has(endpoint) || activeThumbnailRequests.has(endpoint)) return;
    thumbnailTimers.set(endpoint, setTimeout(() => loadThumbnailBatch(endpoint), 50));
}

async function loadThumbnailBatch(endpoint) {
    thumbnailTimers.delete(endpoint);
    const queue = thumbnailQueues.get(endpoint) || [];
    const batch = queue.splice(0, 8);
    if (!batch.length) return;
    activeThumbnailRequests.add(endpoint);
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message_ids: batch.map(element => Number(element.dataset.messageId))
            })
        });
        if (!response.ok) throw new Error(`Thumbnail request failed: HTTP ${response.status}`);
        const result = await response.json();
        if (!result.success) throw new Error(result.error || 'Thumbnail request failed');

        batch.forEach(placeholder => {
            placeholder.dataset.thumbnailLoaded = 'true';
            const preview = result.previews[String(placeholder.dataset.messageId)];
            if (!preview) return;
            const image = document.createElement('img');
            image.className = 'media-thumbnail';
            image.alt = `${placeholder.dataset.mediaLabel || 'Media'} thumbnail`;
            image.src = preview;
            const iconClass = placeholder.querySelector('i')?.className || 'fas fa-paperclip';
            image.onerror = () => {
                placeholder.className = 'media-type-icon media-thumbnail-placeholder';
                const fallback = document.createElement('i');
                fallback.className = iconClass;
                placeholder.replaceChildren(fallback);
            };
            placeholder.className = 'media-thumbnail-wrap';
            placeholder.replaceChildren(image);
            if (['VIDEO', 'ANIMATION', 'VIDEO_NOTE'].includes(placeholder.dataset.mediaType)) {
                const play = document.createElement('span');
                play.className = 'media-play-indicator';
                play.setAttribute('aria-hidden', 'true');
                play.innerHTML = '<i class="fas fa-play"></i>';
                placeholder.appendChild(play);
            }
        });
    } catch (error) {
        batch.forEach(placeholder => { placeholder.dataset.thumbnailQueued = ''; });
        showToast(`Could not load media previews: ${error.message}`, 'warning');
    } finally {
        activeThumbnailRequests.delete(endpoint);
        if (queue.length) scheduleThumbnailBatch(endpoint);
    }
}

function initializeChannelTabs() {
    const channelTabs = document.getElementById('channelTabs');
    if (!channelTabs) return;
    loadMessages(1);
    channelTabs.addEventListener('shown.bs.tab', event => {
        const target = event.target.getAttribute('href');
        if (target === '#tab-admins') loadAdmins();
        if (target === '#tab-members' && document.getElementById('tab-members')?.dataset.loaded !== 'true') {
            loadMembers(1);
        }
    });
}

async function loadAdmins() {
    const container = document.getElementById('adminsContainer');
    if (!container || container.dataset.loaded === 'true' || container.dataset.loading === 'true') return;
    container.dataset.loading = 'true';
    container.innerHTML = '<div class="text-center text-muted py-5"><span class="spinner-border spinner-border-sm me-2"></span>Loading administrators…</div>';
    try {
        const response = await fetch(`${channelApiBase()}/admins`);
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || `HTTP ${response.status}`);
        container.dataset.loaded = 'true';
        const badge = document.getElementById('adminsCount');
        if (badge) badge.textContent = result.count;
        container.innerHTML = result.admins.length
            ? `<div class="table-responsive"><table class="table table-hover align-middle mb-0">
                <thead class="table-light"><tr><th>Admin</th><th>Username</th><th>Role</th><th>Title</th></tr></thead>
                <tbody>${result.admins.map(admin => `
                    <tr><td><div class="d-flex align-items-center gap-2">
                        <div class="member-avatar">${escHtml((admin.name || '?')[0].toUpperCase())}</div>
                        <span class="fw-semibold">${escHtml(admin.name)}</span>
                        ${admin.is_bot ? '<span class="badge bg-info admin-badge">Bot</span>' : ''}
                    </div></td><td>${admin.username
                        ? `<a href="https://t.me/${escHtml(admin.username)}" target="_blank" rel="noopener">@${escHtml(admin.username)}</a>`
                        : '<span class="text-muted">—</span>'}</td>
                    <td>${String(admin.status).toUpperCase().includes('OWNER')
                        ? '<span class="badge-owner">👑 Owner</span>'
                        : '<span class="badge-admin">🛡 Admin</span>'}</td>
                    <td>${escHtml(admin.custom_title || '—')}</td></tr>`).join('')}
                </tbody></table></div>`
            : '<div class="text-center text-muted py-5"><i class="fas fa-shield-alt fa-2x mb-2"></i><p>No admin data available.</p></div>';
    } catch (error) {
        container.innerHTML = `<div class="alert alert-warning">Could not load administrators: ${escHtml(error.message)}
            <button class="btn btn-sm btn-outline-secondary ms-2" onclick="loadAdmins()">Retry</button></div>`;
    } finally {
        container.dataset.loading = 'false';
    }
}

function loadDeferredPhotos(root = document) {
    if (!root) return;
    const images = [...root.querySelectorAll('img[data-photo-chat-id]')].filter(img =>
        img.dataset.photoChatId && Number.isSafeInteger(Number(img.dataset.photoChatId))
    );
    if (!images.length) return;

    const queues = new Map();
    const timers = new Map();
    const active = new Set();

    function schedule(endpoint) {
        if (timers.has(endpoint) || active.has(endpoint)) return;
        timers.set(endpoint, setTimeout(() => loadBatch(endpoint), 50));
    }

    async function loadBatch(endpoint) {
        timers.delete(endpoint);
        const queue = queues.get(endpoint) || [];
        const batch = queue.splice(0, 12);
        if (!batch.length) return;
        const requestedIds = new Map(batch.map(img => [img, img.dataset.photoChatId]));
        active.add(endpoint);
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_ids: batch.map(img => Number(requestedIds.get(img))) })
            });
            if (!response.ok) throw new Error(`Photo request failed: HTTP ${response.status}`);
            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Photo request failed');

            batch.forEach(img => {
                img.dataset.photoQueued = '';
                if (img.dataset.photoChatId !== requestedIds.get(img)) {
                    enqueue(img);
                    return;
                }
                const photo = result.photos[String(requestedIds.get(img))];
                img.dataset.photoLoaded = 'true';
                if (!photo) return;
                img.onload = () => {
                    img.hidden = false;
                    const fallback = img.previousElementSibling;
                    if (fallback && fallback.hasAttribute('data-photo-fallback')) fallback.hidden = true;
                };
                img.onerror = () => {
                    img.hidden = true;
                    const fallback = img.previousElementSibling;
                    if (fallback && fallback.hasAttribute('data-photo-fallback')) fallback.hidden = false;
                };
                img.src = photo;
            });
        } catch (error) {
            batch.forEach(img => {
                img.dataset.photoQueued = '';
                img.dataset.photoObserved = '';
            });
            console.warn('Could not load chat photos:', error);
        } finally {
            active.delete(endpoint);
            if (queue.length) schedule(endpoint);
        }
    }

    function enqueue(img) {
        if (img.dataset.photoQueued || img.dataset.photoLoaded) return;
        const endpoint = img.dataset.photoEndpoint;
        const chatId = Number(img.dataset.photoChatId);
        if (!endpoint || !Number.isSafeInteger(chatId)) return;
        img.dataset.photoQueued = 'true';
        if (!queues.has(endpoint)) queues.set(endpoint, []);
        queues.get(endpoint).push(img);
        schedule(endpoint);
    }

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                const img = entry.target.matches('img')
                    ? entry.target
                    : entry.target.nextElementSibling;
                if (img) enqueue(img);
            });
        }, { rootMargin: '250px' });
        images.filter(img => !img.dataset.photoObserved).forEach(img => {
            const fallback = img.previousElementSibling;
            img.dataset.photoObserved = 'true';
            observer.observe(
                fallback && fallback.hasAttribute('data-photo-fallback') ? fallback : img
            );
        });
    } else {
        images.forEach(enqueue);
    }
}

// ─── Health check ─────────────────────────────────────────────────────────────

async function checkHealth() {
    const indicator = document.getElementById('health-indicator');
    const dot = document.querySelector('.telegram-status-dot');
    try {
        const res = await fetch('/health');
        if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`);
        const data = await res.json();
        const el = indicator;
        if (el) {
            el.classList.remove('status-active', 'status-inactive');
            if (data.status === 'healthy' && data.database === 'connected') {
                el.textContent = 'Online';
                el.classList.add('status-active');
            } else if (data.status === 'degraded' || data.database === 'disconnected') {
                el.textContent = 'Storage offline';
                el.classList.add('status-inactive');
            } else {
                el.textContent = 'Offline';
                el.classList.add('status-inactive');
            }
            if (dot) dot.classList.toggle('status-inactive', el.classList.contains('status-inactive'));
        }
    } catch {
        if (indicator) {
            indicator.textContent = 'Unreachable';
            indicator.classList.add('status-inactive');
        }
        if (dot) dot.classList.add('status-inactive');
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

function getMessageLink(messageId) {
    const channelId = String(document.body.dataset.channelId || '');
    const username = String(document.body.dataset.chatUsername || '').replace(/^@/, '');
    if (username) {
        return `https://t.me/${encodeURIComponent(username)}/${encodeURIComponent(messageId)}`;
    }

    const privateChannelId = channelId.match(/^-100(\d+)$/);
    if (privateChannelId) {
        return `https://t.me/c/${privateChannelId[1]}/${encodeURIComponent(messageId)}`;
    }

    return `tg://openmessage?chat_id=${encodeURIComponent(channelId)}&message_id=${encodeURIComponent(messageId)}`;
}

function copyMessageLink(messageId) {
    copyToClipboard(getMessageLink(messageId), 'Telegram message link copied');
}

// ─── Members pagination ───────────────────────────────────────────────────────

let membersPage = 1;
const membersLimit = 50;

async function loadMembers(page, btnEl) {
    if (btnEl) setLoading(btnEl, true);
    const tbody  = document.getElementById('membersTableBody');
    const status = document.getElementById('membersStatus');
    if (!tbody) return;
    if (status) status.textContent = `Loading page ${page}…`;

    try {
        const res = await fetch(`${channelApiBase()}/members?page=${page}&limit=${membersLimit}`);
        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.error || `HTTP ${res.status}`);
        }

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
        const membersPane = document.getElementById('tab-members');
        if (membersPane) membersPane.dataset.loaded = 'true';
        if (status) status.textContent = `Page ${page} · Showing ${data.members.length} members`;

        const prevBtn = document.getElementById('membersPrevBtn');
        const nextBtn = document.getElementById('membersNextBtn');
        if (prevBtn) prevBtn.disabled = page <= 1;
        if (nextBtn) nextBtn.disabled = data.members.length < membersLimit;
    } catch (e) {
        if (status) status.textContent = 'Could not load members. Use Refresh to retry.';
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

function renderChatMessage(msg) {
    const messageId = Number(msg.id) || 0;
    const mediaLabel = escHtml(msg.media_label || 'Media');
    const mediaType = String(msg.media_type || '').toUpperCase();
    const mediaIcon = escHtml(msg.media_icon || 'fa-paperclip');
    const mediaName = msg.media_name || msg.media_mime_type || '';
    const mediaPreview = msg.media_preview
        ? `<div class="media-thumbnail-wrap">
                <img class="media-thumbnail" src="${escHtml(msg.media_preview)}" alt="${mediaLabel} thumbnail" loading="lazy">
                ${['VIDEO', 'ANIMATION', 'VIDEO_NOTE'].includes(mediaType)
                    ? '<span class="media-play-indicator" aria-hidden="true"><i class="fas fa-play"></i></span>'
                    : ''}
           </div>`
        : `<div class="media-type-icon media-thumbnail-placeholder"
                data-message-id="${messageId}"
                data-media-type="${escHtml(mediaType)}"
                data-media-label="${mediaLabel}"
                aria-label="Load ${mediaLabel} preview">
                <i class="fas ${mediaIcon}"></i>
           </div>`;
    const media = msg.has_media
        ? `<div class="chat-media-preview">${mediaPreview}
                <div class="media-details">
                    <span class="media-type-label">${mediaLabel}</span>
                    ${mediaName ? `<span class="media-name">${escHtml(mediaName)}</span>` : ''}
                    ${msg.media_duration ? `<span class="media-name">${escHtml(msg.media_duration)} sec</span>` : ''}
                </div>
           </div>`
        : '';
    const text = msg.short_text
        ? `<p class="chat-message-text">${escHtml(msg.short_text)}</p>`
        : (msg.has_media ? '' : '<p class="chat-message-text text-muted">Empty message</p>');

    return `
        <article class="chat-message" id="msg-${messageId}">
            <div class="chat-message-header">
                <span class="chat-sender">${escHtml(msg.sender || 'Channel')}</span>
                <div class="chat-meta">
                    ${msg.views ? `<span><i class="fas fa-eye me-1"></i>${fmtNum(msg.views)}</span>` : ''}
                    ${msg.is_pinned ? '<span title="Pinned"><i class="fas fa-thumbtack"></i></span>' : ''}
                    <time>${escHtml(msg.date)}</time>
                    <div class="dropup message-actions">
                        <button class="btn btn-sm btn-outline-secondary message-action-button" type="button"
                                data-bs-toggle="dropdown" aria-expanded="false"
                                aria-label="Actions for message ${messageId}" title="Message actions">
                            <i class="fas fa-ellipsis"></i>
                        </button>
                        <ul class="dropdown-menu dropdown-menu-end">
                            <li><button class="dropdown-item" type="button" onclick="copyMessageLink(${messageId})">
                                <i class="fas fa-link me-2"></i>Copy message link
                            </button></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><button class="dropdown-item text-danger" type="button"
                                onclick="deleteMessage(${messageId}, document.getElementById('msg-${messageId}'))">
                                <i class="fas fa-trash-alt me-2"></i>Delete message
                            </button></li>
                        </ul>
                    </div>
                </div>
            </div>
            ${media}
            ${text}
        </article>`;
}

async function loadMessages(page, btnEl) {
    if (btnEl) setLoading(btnEl, true);
    const container = document.getElementById('messagesContainer');
    const status    = document.getElementById('messagesStatus');
    if (!container) return;
    if (status) status.textContent = 'Loading messages…';

    try {
        const res = await fetch(`${channelApiBase()}/messages?page=${page}&limit=${messagesLimit}`);
        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.error || `HTTP ${res.status}`);
        }

        const renderedMessages = data.messages.map(renderChatMessage).join('');
        if (page > messagesPage && renderedMessages) {
            const previousHeight = container.scrollHeight;
            const previousTop = container.scrollTop;
            container.insertAdjacentHTML('afterbegin', renderedMessages);
            container.scrollTop = previousTop + container.scrollHeight - previousHeight;
        } else {
            container.innerHTML = renderedMessages
                || '<div class="text-center text-muted py-4"><i class="fas fa-comment fa-2x mb-2"></i><p>No messages found.</p></div>';
            if (page === 1) container.scrollTop = container.scrollHeight;
        }

        observeDeferredThumbnails(container);
        messagesPage = page;
        if (status) status.textContent = `${container.querySelectorAll('.chat-message').length} messages loaded`;

        const nextBtn = document.getElementById('messagesNextBtn');
        if (nextBtn) nextBtn.disabled = data.messages.length < messagesLimit;
    } catch (e) {
        if (status) status.textContent = 'Could not load messages.';
        if (page === 1 && !container.querySelector('.chat-message')) {
            container.innerHTML = `<div class="alert alert-warning">Could not load chat history: ${escHtml(e.message)}
                <button class="btn btn-sm btn-outline-secondary ms-2" onclick="loadMessages(1, this)">Retry</button></div>`;
        }
        showToast('Failed to load messages: ' + e.message, 'danger');
    } finally {
        if (btnEl) setLoading(btnEl, false);
    }
}

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
