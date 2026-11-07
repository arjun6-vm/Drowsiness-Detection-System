const STORAGE_KEY = 'safedrive_theme';
const TOGGLE_BTN_ID = 'theme-toggle-btn';

function getTheme() {
    return localStorage.getItem(STORAGE_KEY) || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    updateToggleIcon(theme);
    window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: theme } }));
}

function updateToggleIcon(theme) {
    const btn = document.getElementById(TOGGLE_BTN_ID);
    if (btn) {
        const lightIcon = btn.querySelector('.light-icon');
        const darkIcon = btn.querySelector('.dark-icon');
        if (theme === 'dark') {
            if (darkIcon) { darkIcon.style.background = '#2563EB'; darkIcon.style.color = '#ffffff'; }
            if (lightIcon) { lightIcon.style.background = 'transparent'; lightIcon.style.color = 'var(--text-muted, #94a3b8)'; }
            btn.style.background = '#0B1121';
            btn.style.borderColor = '#334155';
        } else {
            if (lightIcon) { lightIcon.style.background = '#2563EB'; lightIcon.style.color = '#ffffff'; }
            if (darkIcon) { darkIcon.style.background = 'transparent'; darkIcon.style.color = 'var(--text-muted, #64748b)'; }
            btn.style.background = '#E2E8F0';
            btn.style.borderColor = '#CBD5E1';
        }
    }
}

function initTheme() {
    const currentTheme = getTheme();
    setTheme(currentTheme);
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    const btn = document.getElementById(TOGGLE_BTN_ID);
    if (btn) {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const currentTheme = document.documentElement.getAttribute('data-theme');
            setTheme(currentTheme === 'dark' ? 'light' : 'dark');
        });
    }
});

// Run once immediately so no flash of wrong theme occurs
initTheme();
