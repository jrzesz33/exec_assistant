// Executive Assistant Chat UI
// Handles authentication and chat interaction

// Configuration - will be replaced during deployment
const API_ENDPOINT = window.location.hostname.includes('localhost')
    ? 'http://localhost:3000'  // Local development
    : 'API_ENDPOINT_PLACEHOLDER';  // Will be replaced by Pulumi

// State management
let accessToken = null;
let refreshToken = null;
let currentUser = null;
let currentSessionId = null;  // Track current chat session

// DOM elements
const elements = {
    loading: document.getElementById('loading'),
    authContainer: document.getElementById('auth-container'),
    chatContainer: document.getElementById('chat-container'),
    errorContainer: document.getElementById('error-container'),
    loginButton: document.getElementById('login-button'),
    logoutButton: document.getElementById('logout-button'),
    userAvatar: document.getElementById('user-avatar'),
    userName: document.getElementById('user-name'),
    userEmail: document.getElementById('user-email'),
    messages: document.getElementById('messages'),
    messageInput: document.getElementById('message-input'),
    sendButton: document.getElementById('send-button'),
};

// Initialize app
async function init() {
    console.log('Initializing Executive Assistant UI...');

    // Check for tokens in URL (OAuth callback)
    const urlParams = new URLSearchParams(window.location.search);
    const accessTokenParam = urlParams.get('access_token');
    const refreshTokenParam = urlParams.get('refresh_token');
    const errorParam = urlParams.get('error');

    if (errorParam) {
        showError(`Authentication failed: ${errorParam}`);
        showAuth();
        return;
    }

    if (accessTokenParam && refreshTokenParam) {
        // Save tokens from OAuth callback
        accessToken = accessTokenParam;
        refreshToken = refreshTokenParam;
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);

        // Clean up URL
        window.history.replaceState({}, document.title, window.location.pathname);
    } else {
        // Check for stored tokens
        accessToken = localStorage.getItem('access_token');
        refreshToken = localStorage.getItem('refresh_token');
    }

    // If we have tokens, try to authenticate
    if (accessToken) {
        try {
            await fetchUserInfo();
            showChat();
        } catch (error) {
            console.error('Failed to fetch user info:', error);
            // Try to refresh token
            if (refreshToken) {
                try {
                    await refreshAccessToken();
                    await fetchUserInfo();
                    showChat();
                } catch (refreshError) {
                    console.error('Failed to refresh token:', refreshError);
                    clearAuth();
                    showAuth();
                }
            } else {
                clearAuth();
                showAuth();
            }
        }
    } else {
        showAuth();
    }

    // Set up event listeners
    elements.loginButton.addEventListener('click', handleLogin);
    elements.logoutButton.addEventListener('click', handleLogout);
    elements.sendButton.addEventListener('click', handleSendMessage);
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    // Auto-resize textarea
    elements.messageInput.addEventListener('input', () => {
        elements.messageInput.style.height = 'auto';
        elements.messageInput.style.height = elements.messageInput.scrollHeight + 'px';
    });
}

// Authentication functions
function handleLogin() {
    console.log('Redirecting to login...');
    window.location.href = `${API_ENDPOINT}/auth/login`;
}

function handleLogout() {
    console.log('Logging out...');
    clearAuth();
    showAuth();
}

function clearAuth() {
    accessToken = null;
    refreshToken = null;
    currentUser = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
}

async function fetchUserInfo() {
    console.log('Fetching user info...');

    const response = await fetch(`${API_ENDPOINT}/auth/me`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch user info: ${response.status}`);
    }

    currentUser = await response.json();
    console.log('User info fetched:', currentUser);
    updateUserInfo();
}

async function refreshAccessToken() {
    console.log('Refreshing access token...');

    const response = await fetch(`${API_ENDPOINT}/auth/refresh`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            refresh_token: refreshToken,
        }),
    });

    if (!response.ok) {
        throw new Error(`Failed to refresh token: ${response.status}`);
    }

    const data = await response.json();
    accessToken = data.access_token;
    localStorage.setItem('access_token', accessToken);
    console.log('Access token refreshed');
}

function updateUserInfo() {
    if (!currentUser) return;

    elements.userName.textContent = currentUser.name;
    elements.userEmail.textContent = currentUser.email;

    if (currentUser.picture) {
        elements.userAvatar.src = currentUser.picture;
    } else {
        // Use a default avatar if no picture
        elements.userAvatar.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(currentUser.name)}&background=667eea&color=fff`;
    }
}

// UI state management
function showAuth() {
    elements.loading.style.display = 'none';
    elements.authContainer.style.display = 'block';
    elements.chatContainer.style.display = 'none';
}

function showChat() {
    elements.loading.style.display = 'none';
    elements.authContainer.style.display = 'none';
    elements.chatContainer.style.display = 'flex';
}

function showError(message) {
    elements.errorContainer.innerHTML = `<div class="error">${message}</div>`;
    elements.errorContainer.style.display = 'block';
    setTimeout(() => {
        elements.errorContainer.style.display = 'none';
    }, 5000);
}

// Chat functions
async function handleSendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message) return;

    // Disable input while processing
    elements.sendButton.disabled = true;
    elements.messageInput.disabled = true;

    // Add user message to chat
    addMessage('user', message);

    // Clear input
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';

    try {
        // Send message to agent API
        const response = await fetch(`${API_ENDPOINT}/chat/send`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`,
            },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId,  // Maintain session across messages
            }),
        });

        if (!response.ok) {
            if (response.status === 401) {
                // Token expired, try to refresh
                await refreshAccessToken();
                // Retry the request
                return handleSendMessage();
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Update session ID
        currentSessionId = data.session_id;

        // Add agent response to chat
        addMessage('assistant', data.message);

    } catch (error) {
        console.error('Failed to send message:', error);
        addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
    } finally {
        // Re-enable input
        elements.sendButton.disabled = false;
        elements.messageInput.disabled = false;
        elements.messageInput.focus();
    }
}

function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    messageDiv.appendChild(contentDiv);
    elements.messages.appendChild(messageDiv);

    // Scroll to bottom
    elements.messages.scrollTop = elements.messages.scrollHeight;
}

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
