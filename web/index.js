// plugins/leona-custom-discord/web/index.js — Settings tab for Leona Discord plugin

import { registerPluginSettings } from '/static/shared/plugin-registry.js';

const PLUGIN_NAME = 'leona_discord';
const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

const _DEFAULTS = {
    bot_response_chance: 15,
    human_response_chance: 15,
    cooldown_seconds: 120,
    cooldown_scope: 'per_channel',
    name_match_enabled: true,
    name_match_case_sensitive: false,
    reactions_enabled: true,
    reaction_chance: 50,
    react_to_trigger: true,
    react_to_any: false,
    allowed_emojis: ['<:smile:123456789>'],
    reaction_backend: 'vader',
    image_enabled: false,
    image_model_provider: '',
    image_model_name: '',
    image_model_max_tokens: 500,
    append_to_user_message_enabled: false,
    append_to_user_message: '',
};

// Cached provider+model data fetched from Sapphire core
let _LLM_PROVIDERS = null;

// ── Local timezone ↔ UTC hour conversion (settings UI) ─────────────────────
// Backend schedules still run on UTC; we convert only in the browser.

function _localTimezoneLabel() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
    } catch (_) {
        return 'local time';
    }
}

function _normalizeHour(h) {
    const n = parseInt(h, 10);
    if (!Number.isFinite(n)) return 0;
    return ((n % 24) + 24) % 24;
}

function _utcHourToLocal(utcHour) {
    const d = new Date();
    d.setUTCHours(_normalizeHour(utcHour), 0, 0, 0);
    return d.getHours();
}

function _localHourToUtc(localHour) {
    const now = new Date();
    const d = new Date(
        now.getFullYear(), now.getMonth(), now.getDate(),
        _normalizeHour(localHour), 0, 0, 0,
    );
    return d.getUTCHours();
}

function _formatHourLabel(h) {
    const hour = _normalizeHour(h);
    return `${String(hour).padStart(2, '0')}:00`;
}

// Full emoji list loaded from API; used as the grid source so all 1340 are available
let _API_EMOJIS = null;
let _presencePresetCatalog = [];

// Custom Discord emoji input field + add button for building the allowlist.
// All standard Unicode emoji are always allowed and not shown in the grid.
// ─────────────────────────────────────────────────────────────────────────────
const _ALL_EMOJIS = [
    '😀','😃','😄','😁','😆','😅','🤣','😂','🙂','🙃','😉','😊','😇','🥰','😍','🤩','😘','😗','😋','😜','🤪','😝','🤑','🤗','🤔','😎','🤓','🧐','😕','😟','🙁','☹️','😮','😯','😲','😳','🥺','😥','😢','😭','😱','😡','😠','🤬','😈','👿','💀','☠️','💩','🤡','👻','👽','👾','🤖',
    '👍','👎','👊','✋','🤚','🖐️','✌️','🤞','🤟','🤘','👏','🙌','👐','🤝','🙏','💪','🦾','🦿','🦵','🦶','👂','🦻','👃','🧠','👀','👁️','👅','👄','👶','🧒','👦','👧','🧑','👱','👨','👩','👴','👵','🙍','🙎','🙅','🙆','💁','🙋','👮','🕵️','👷','🤴','👸','👳','🤵','👰','🤰',
    '❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💟','💌','💋','💍','👙','👗','👠','👡','👢','💄','🥾','🧣','🧤','🧥','👓','🕶️','👒','🎩','🎓','👑',
    '🐱','🐶','🐕','🦮','🐕‍🦺','🐩','🐺','🦊','🐈','🐈‍⬛','🐾','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🐒','🐔','🐧','🐦','🐤','🦆','🦅','🦉','🦇','🐢','🐍','🦎','🐙','🦑','🦐','🦀','🐡','🐠','🐟','🐬','🐳','🐋','🦈','🐊','🐘','🦛','🦏','🦌','🐑','🦙','🦒','🦘','🦣','🐪','🐫',
    '🍎','🍏','🍐','🍊','🍋','🍌','🍉','🍇','🍓','🫐','🍈','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🍆','🥑','🥦','🥬','🥒','🌶️','🌽','🥕','🥔','🍠','🥐','🥯','🍞','🥖','🥨','🧀','🥚','🍳','🧈','🥞','🥓','🥩','🍗','🍖','🌭','🍔','🍟','🍕','🥪','🥙','🧆','🌮','🌯','🥗','🥘','🍝','🍜','🍲','🍛','🍣','🍱','🥟','🍤','🍙','🍚','🍦','🍧','🍨','🍰','🎂','🍭','🍬','🍫','🍿','🍩','🍪','🌰','🥜','🍯','☕','🍵','🍺','🍻','🥂','🍷','🥃','🍸','🍹','🍾',
    '🚗','🚕','🚙','🚌','🚎','🏎️','🚓','🚑','🚒','🚐','🚚','🚛','🚜','🚲','🛵','🏍️','✈️','🛫','🛬','🛩️','💺','🛰️','🚀','🛸','🚁','⛵','🚤','🛥️','🛳️','🚢','⚓','⛽','🚧','🚦','🚥','🗺️','🗿','🗽','🗼','🏰','🏯','🏟️','🎡','🎢','🎠','⛲','🏖️','🏝️','🌋','⛰️','🏔️','🗻','🏕️','⛺','🏠','🏡','🏥','🏦','🏨','🏪','🏫','🏩','💒','⛪','🕌','🕍','🛕','⛩️',
    '⌚','📱','💻','📷','📸','📹','🎥','📺','📻','🎙️','🎚️','🎛️','⏱️','⏰','🕰️','⌛','⏳','💡','🔦','💰','💳','💎','⚖️','🔧','🔨','⚒️','🛠️','🔩','⚙️','🔗','⚡','🧿','🏧','⚜️','🔱','⚔️','🛡️','☮️','✝️','☪️','☸️','✡️','☯️','☦️','⛎','♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓','🆔','⚛️','☢️','☣️','❌','⭕','✅','❎','✔️','☑️','🔘','🔰','🔮',
    '🏁','🚩','🎌','🏴','🏳️','🏳️‍🌈','🏴‍☠️',
    '⚽','⚾','🥎','🏀','🏐','🏈','🏉','🎾','🥏','🎳','🏏','🏑','🏒','🥍','🏓','🏸','🥊','🥋','🥅','⛳','🎣','🤿','🥌','🎽','🎿','🛷','🏂','🏋️','🤼','🤸','🤺','⛹️','🤾','🏌️','🏇','🧘','🏄','🏊','🤽','🚣','🧗','🏆','🥇','🥈','🥉','🏅','🎖️','🏵️','🎗️','🎫','🤹','🎭','🎨','🎬','🎤','🎧','🎼','🎹','🥁','🎷','🎺','🎸','🎻','🎲','♟️','🎯',
    '🔥','⭐','🌟','✨','💫','🌈','☀️','🌤️','⛅','🌥️','☁️','🌧️','⛈️','❄️','☃️','⛄','🌬️','💨','🌪️','💧','💦','☔','🌊','🌀','🌙','🌛','🌜','🌚','🌝','🌞','🌱','🌲','🌳','🌴','🌵','🌾','🌿','☘️','🍀','🍁','🍂','🍃','🍄','🌸','💐','🌷','🌹','🥀','🌺','🌻','🌼','🌽','🌰','🐚','🪨',
    '👩‍🦰','👨‍🦰','👩‍🦱','👨‍🦱','👩‍🦲','👨‍🦲','👩‍🦳','👨‍🦳','👱‍♀️','👱‍♂️','🧑‍🦰','🧑‍🦱','🧑‍🦲','🧑‍🦳','🧑‍🤝‍🧑','🧑‍🧒','🧑‍🧓','🧑‍🧔','🧑‍🧕','🧑‍⚕️','🧑‍🎓','🧑‍🏫','🧑‍⚖️','🧑‍🌾','🧑‍🍳','🧑‍🔧','🧑‍🏭','🧑‍💼','🧑‍🔬','🧑‍💻','🧑‍🎤','🧑‍🎨','🧑‍✈️','🧑‍🚀','🧑‍🚒',
    '👩‍👩‍👦','👩‍👩‍👧','👩‍👩‍👧‍👦','👩‍👩‍👦‍👦','👩‍👩‍👧‍👧','👨‍👨‍👦','👨‍👨‍👧','👨‍👨‍👧‍👦','👨‍👨‍👦‍👦','👨‍👨‍👧‍👧','👨‍👩‍👦','👨‍👩‍👧','👨‍👩‍👧‍👦','👨‍👩‍👦‍👦','👨‍👩‍👧‍👧','👩‍👦','👩‍👧','👩‍👧‍👦','👩‍👦‍👦','👩‍👧‍👧','👨‍👦','👨‍👧','👨‍👧‍👦','👨‍👦‍👦','👨‍👧‍👧',
    // Custom server emojis: use format "<:name:ID>" or "<a:name:ID>" (animated)
    '<:smile:123456789>',
];


// ── Injected CSS ───────────────────────────────────────────────────────────────

const _CSS = `
.dc-plugin { font-family: inherit; }

/* Section chrome */
.dc-section { margin-bottom: 4px; }
.dc-section-header {
    display: flex; align-items: center; gap: 10px;
    padding: 20px 0 10px;
}
.dc-section-label {
    font-size: 0.7em; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--text-muted, #72767d);
    white-space: nowrap;
}
.dc-section-divider {
    flex: 1; height: 1px; background: var(--border, rgba(255,255,255,0.08));
}

/* Cards */
.dc-card {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 8px; padding: 4px 14px; margin-bottom: 6px;
}
.dc-card-inner {
    background: var(--bg-primary, rgba(0,0,0,0.15)); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 12px; margin: 4px 0 6px;
}

/* Setting rows */
.dc-row {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 20px; padding: 9px 0;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.05));
}
.dc-row:last-child { border-bottom: none; }
.dc-row-label { flex: 1; min-width: 0; }
.dc-row-label > label {
    font-size: 0.875em; font-weight: 500;
    color: var(--text, #dcddde); display: block;
}
.dc-row-help {
    font-size: 0.78em; color: var(--text-muted, #72767d);
    margin-top: 3px; line-height: 1.45;
}
.dc-row-help code {
    background: rgba(255,255,255,0.07); padding: 1px 5px;
    border-radius: 3px; font-size: 0.9em;
}
.dc-row-control {
    flex-shrink: 0; display: flex; align-items: center;
    gap: 8px; padding-top: 1px;
}
.dc-row-col {
    flex-shrink: 0; display: flex; flex-direction: column;
    gap: 8px; padding-top: 1px; align-items: flex-start;
}

/* Toggle switch */
.dc-toggle {
    position: relative; display: inline-block;
    width: 40px; height: 22px; flex-shrink: 0; cursor: pointer;
}
.dc-toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
.dc-toggle-track {
    position: absolute; inset: 0;
    background: var(--border, #4f545c);
    border-radius: 22px;
    transition: background 0.18s;
}
.dc-toggle-thumb {
    position: absolute; width: 16px; height: 16px;
    background: #fff; border-radius: 50%;
    top: 3px; left: 3px;
    transition: transform 0.18s, box-shadow 0.18s;
    pointer-events: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.dc-toggle input:checked ~ .dc-toggle-track { background: var(--accent, #7289da); }
.dc-toggle input:checked ~ .dc-toggle-thumb { transform: translateX(18px); }

/* Slider */
.dc-slider-wrap { display: flex; align-items: center; gap: 10px; }
.dc-slider-wrap input[type=range] {
    width: 130px; accent-color: var(--accent, #7289da);
    cursor: pointer;
}
.dc-slider-val {
    min-width: 38px; text-align: right; font-size: 0.82em;
    font-weight: 600; color: var(--accent, #7289da);
    background: rgba(114,137,218,0.12); padding: 2px 7px;
    border-radius: 4px;
}

/* Radio pills */
.dc-radio-group { display: flex; gap: 5px; flex-wrap: wrap; }
.dc-radio-pill { position: relative; }
.dc-radio-pill input { position: absolute; opacity: 0; width: 0; height: 0; }
.dc-radio-pill label {
    display: block; padding: 4px 12px;
    border-radius: 20px; border: 1px solid var(--border, #4f545c);
    font-size: 0.8em; font-weight: 500; cursor: pointer;
    color: var(--text-muted, #72767d);
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    white-space: nowrap; user-select: none;
}
.dc-radio-pill input:checked + label {
    background: var(--accent, #7289da);
    border-color: var(--accent, #7289da);
    color: #fff;
}
.dc-radio-pill label:hover { border-color: var(--accent, #7289da); }

/* Buttons */
.dc-btn {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 14px; border-radius: 6px;
    border: 1px solid var(--border, #4f545c);
    font-size: 0.82em; font-weight: 500; cursor: pointer;
    background: transparent; color: var(--text, #dcddde);
    transition: background 0.15s, border-color 0.15s, filter 0.15s, opacity 0.15s;
    white-space: nowrap;
}
.dc-btn:hover:not(:disabled) { background: rgba(255,255,255,0.06); }
.dc-btn:disabled { opacity: 0.5; cursor: default; }
.dc-btn-primary {
    background: var(--accent, #7289da);
    border-color: var(--accent, #7289da); color: #fff;
}
.dc-btn-primary:hover:not(:disabled) {
    filter: brightness(1.1); background: var(--accent, #7289da);
}
.dc-btn-danger { border-color: var(--error, #f04747); color: var(--error, #f04747); }
.dc-btn-danger:hover:not(:disabled) { background: rgba(240,71,71,0.1); }
.dc-btn-sm { padding: 4px 11px; font-size: 0.79em; }

/* Account cards */
.dc-account-card {
    display: flex; align-items: center;
    justify-content: space-between; gap: 14px;
    padding: 11px 14px;
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 7px;
    transition: border-color 0.15s;
}
.dc-account-card:hover { border-color: rgba(114,137,218,0.35); }
.dc-account-info { flex: 1; min-width: 0; }
.dc-account-name { font-size: 0.9em; font-weight: 600; }
.dc-account-meta {
    display: flex; align-items: center; gap: 8px;
    margin-top: 4px; font-size: 0.77em;
    color: var(--text-muted, #72767d);
}
.dc-account-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* Status badges */
.dc-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 2px 8px; border-radius: 10px;
    font-size: 0.73em; font-weight: 600; letter-spacing: 0.03em;
}
.dc-badge::before {
    content: ''; width: 5px; height: 5px;
    border-radius: 50%; flex-shrink: 0;
}
.dc-badge-online { background: rgba(67,181,129,0.12); color: #43b581; }
.dc-badge-online::before { background: #43b581; }
.dc-badge-offline { background: rgba(255,255,255,0.05); color: var(--text-muted, #72767d); }
.dc-badge-offline::before { background: var(--text-muted, #72767d); }
.dc-badge-override { background: rgba(114,137,218,0.12); color: var(--accent, #7289da); }
.dc-badge-override::before { background: var(--accent, #7289da); }

/* Server rows */
.dc-server-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 14px; padding: 10px 0;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.05));
}
.dc-server-row:last-of-type { border-bottom: none; }
.dc-server-info { flex: 1; min-width: 0; }
.dc-server-name { font-size: 0.88em; font-weight: 600; }
.dc-server-meta { font-size: 0.77em; color: var(--text-muted, #72767d); margin-top: 3px; }
.dc-server-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* Sub-forms (add bot / server override) */
.dc-subform {
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 16px; margin: 4px 0 10px;
}
.dc-subform-title { font-weight: 600; font-size: 0.9em; }
.dc-subform-hint { font-size: 0.78em; color: var(--text-muted, #72767d); margin-top: 3px; margin-bottom: 12px; }
.dc-subform-footer {
    display: flex; align-items: center; gap: 10px;
    margin-top: 14px; padding-top: 10px;
    border-top: 1px solid var(--border, rgba(255,255,255,0.06));
}

/* Status text */
.dc-status { font-size: 0.82em; }
.dc-status-ok { color: var(--success, #43b581); }
.dc-status-err { color: var(--error, #f04747); }

/* Text inputs */
.dc-input {
    padding: 5px 10px; border: 1px solid var(--border, #4f545c);
    border-radius: 6px; background: var(--bg-primary, rgba(0,0,0,0.2));
    color: var(--text, #dcddde); font-size: 0.88em;
    transition: border-color 0.15s; outline: none;
}
.dc-input:focus { border-color: var(--accent, #7289da); }
.dc-input-sm { width: 80px; }
.dc-input-md { width: 200px; }
.dc-input-lg { width: 260px; }

/* Select */
.dc-select {
    padding: 5px 10px; border: 1px solid var(--border, #4f545c);
    border-radius: 6px; background: var(--bg-secondary);
    color: var(--text, #dcddde); font-size: 0.88em;
    cursor: pointer; outline: none; transition: border-color 0.15s;
}
.dc-select:focus { border-color: var(--accent, #7289da); }

/* Greeting target picker */
.dc-greeting-selected {
    display: flex; flex-wrap: wrap; gap: 6px;
    min-height: 28px; margin-bottom: 8px;
}
.dc-greeting-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 8px 3px 10px; border-radius: 12px;
    background: rgba(114,137,218,0.15); border: 1px solid rgba(114,137,218,0.35);
    font-size: 0.78em; color: var(--text, #dcddde);
}
.dc-greeting-chip button {
    border: none; background: transparent; color: var(--text-muted, #72767d);
    cursor: pointer; font-size: 1.1em; line-height: 1; padding: 0 2px;
}
.dc-greeting-chip button:hover { color: var(--error, #f04747); }
.dc-greeting-picker-toolbar {
    display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
}
.dc-greeting-picker {
    max-height: 220px; overflow-y: auto;
    border: 1px solid var(--border, rgba(255,255,255,0.08));
    border-radius: 6px; padding: 8px 10px;
    background: var(--bg-primary, rgba(0,0,0,0.15));
}
.dc-greeting-group { margin-bottom: 10px; }
.dc-greeting-group-title {
    font-size: 0.78em; font-weight: 600; color: var(--accent, #7289da);
    margin-bottom: 4px;
}
.dc-greeting-option {
    display: flex; align-items: center; gap: 8px;
    padding: 3px 0; font-size: 0.84em; cursor: pointer;
}
.dc-greeting-option input { cursor: pointer; }
.dc-greeting-advanced { margin-top: 8px; font-size: 0.78em; color: var(--text-muted, #72767d); }
.dc-greeting-advanced summary { cursor: pointer; margin-bottom: 4px; }

/* Emoji */
.dc-emoji-grid { display: flex; flex-wrap: wrap; gap: 5px; }
.dc-add-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.dc-add-row .dc-input { flex: 1; max-width: 320px; }
.dc-add-hint { font-size: 0.73em; color: var(--text-muted, #72767d); margin-top: 5px; }

/* Save bar */
.dc-save-bar { display: flex; align-items: center; gap: 12px; padding: 14px 0 4px; }

/* Empty / error states */
.dc-empty { font-size: 0.85em; color: var(--text-muted, #72767d); padding: 4px 0; }
.dc-error-text { font-size: 0.85em; color: var(--error, #f04747); padding: 4px 0; }

/* Warning banner — used by the "Image Understanding is off" notice. */
.dc-warning {
    font-size: 0.82em;
    line-height: 1.45;
    color: #faa61a;
    background: rgba(250, 166, 26, 0.10);
    border: 1px solid rgba(250, 166, 26, 0.35);
    border-radius: 6px;
    padding: 8px 12px;
    margin: 6px 0 8px;
}
.dc-warning strong { color: #faa61a; }

/* Global settings tabs */
.dc-tabs {
    display: flex; flex-wrap: wrap; gap: 2px;
    margin: 0 0 12px; padding: 0;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.dc-tab-btn {
    padding: 8px 14px; margin: 0 0 -1px;
    border: none; border-bottom: 2px solid transparent;
    background: transparent; color: var(--text-muted, #72767d);
    cursor: pointer; font-size: 0.88em; font-family: inherit;
    border-radius: 4px 4px 0 0;
}
.dc-tab-btn:hover { color: var(--text, #fff); background: rgba(255,255,255,0.03); }
.dc-tab-btn.active {
    color: var(--accent, #7289da);
    border-bottom-color: var(--accent, #7289da);
    font-weight: 600;
}
.dc-tab-panel { display: none; padding-top: 4px; }
.dc-tab-panel.active { display: block; }
.dc-tab-intro {
    font-size: 0.85em; color: var(--text-muted, #72767d);
    margin: 0 0 10px; line-height: 1.45;
}

/* LLM debug messaging modal */
.dc-modal-overlay {
    position: fixed; inset: 0; z-index: 10050;
    background: rgba(0, 0, 0, 0.62);
    display: flex; align-items: center; justify-content: center;
    padding: 16px;
}
.dc-modal {
    width: min(960px, 96vw); max-height: 90vh;
    background: var(--bg-secondary, #2f3136);
    border: 1px solid var(--border, rgba(255,255,255,0.10));
    border-radius: 10px;
    display: flex; flex-direction: column;
    box-shadow: 0 16px 48px rgba(0,0,0,0.45);
}
.dc-modal-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 14px 16px;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}
.dc-modal-header h3 { margin: 0; font-size: 1em; font-weight: 600; }
.dc-modal-actions { display: flex; gap: 8px; align-items: center; }
.dc-modal-body { padding: 14px 16px; overflow-y: auto; flex: 1; }
.dc-debug-list-item {
    border: 1px solid var(--border, rgba(255,255,255,0.08));
    border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;
    cursor: pointer; background: rgba(0,0,0,0.12);
}
.dc-debug-list-item:hover { border-color: var(--accent, #7289da); }
.dc-debug-list-item.selected { border-color: var(--accent, #7289da); background: rgba(114,137,218,0.12); }
.dc-debug-section { margin-bottom: 14px; }
.dc-debug-section h4 {
    margin: 0 0 6px; font-size: 0.82em; font-weight: 600;
    color: var(--accent, #7289da); text-transform: uppercase; letter-spacing: 0.04em;
}
.dc-debug-pre {
    margin: 0; padding: 10px 12px; border-radius: 6px;
    background: var(--bg-primary, rgba(0,0,0,0.22));
    border: 1px solid var(--border, rgba(255,255,255,0.06));
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.78em; line-height: 1.45; white-space: pre-wrap; word-break: break-word;
    max-height: 280px; overflow-y: auto;
}
.dc-debug-meta { font-size: 0.82em; color: var(--text-muted, #72767d); line-height: 1.5; }
.dc-debug-badge {
    display: inline-block; font-size: 0.72em; padding: 2px 6px; border-radius: 4px;
    background: rgba(67,181,129,0.18); color: var(--success, #43b581); margin-left: 6px;
}
.dc-debug-badge.pending { background: rgba(250,166,26,0.15); color: #faa61a; }
.dc-debug-badge.edit { background: rgba(114,137,218,0.18); color: #7289da; }
`;

function _injectCSS() {
    if (document.getElementById('dc-plugin-styles')) return;
    const el = document.createElement('style');
    el.id = 'dc-plugin-styles';
    el.textContent = _CSS;
    document.head.appendChild(el);
}


registerPluginSettings({
    id: PLUGIN_NAME,
    name: 'Leona Discord',
    icon: '🎮',
    helpText: 'Leona Discord bot accounts. Create a bot at discord.com/developers, enable Message Content Intent, and paste the token here.',

    render(container, settings) {
        _injectCSS();
        _activeContainer = container;  // remembered for host's reg.save() call

        container.innerHTML = `
            <div class="dc-plugin">

                <!-- ── Bot Accounts ── -->
                <div class="dc-section">
                    <div class="dc-section-header">
                        <span class="dc-section-label">Bot Accounts</span>
                        <span class="dc-section-divider"></span>
                    </div>
                    <div id="dc-accounts-list"></div>
                    <div id="dc-add-form"></div>
                    <div style="margin-top:8px">
                        <button class="dc-btn dc-btn-sm" id="dc-add-account">＋ Add Bot</button>
                    </div>
                </div>

                <!-- ── Global Settings ── -->
                <div class="dc-section">
                    <div class="dc-section-header">
                        <span class="dc-section-label">Global Settings</span>
                        <span class="dc-section-divider"></span>
                    </div>
                    <p class="dc-empty" style="margin-bottom:10px">
                        Apply to all servers unless overridden per-server below.
                    </p>

                    <nav class="dc-tabs" id="dc-global-tabs" aria-label="Global settings sections">
                        <button type="button" class="dc-tab-btn active" data-tab="general">General</button>
                        <button type="button" class="dc-tab-btn" data-tab="replies">Replies</button>
                        <button type="button" class="dc-tab-btn" data-tab="reactions">Reactions &amp; Media</button>
                        <button type="button" class="dc-tab-btn" data-tab="memory">Memory</button>
                        <button type="button" class="dc-tab-btn" data-tab="profiles">Profiles</button>
                        <button type="button" class="dc-tab-btn" data-tab="status">Status</button>
                        <button type="button" class="dc-tab-btn" data-tab="presence">Presence</button>
                        <button type="button" class="dc-tab-btn" data-tab="advanced">Advanced</button>
                        <button type="button" class="dc-tab-btn" data-tab="debug">Debug</button>
                    </nav>

                    <div class="dc-tab-panel active" data-tab="general" id="dc-tab-general">
                        <p class="dc-tab-intro">Connection timing, slash commands, and core bot behaviour.</p>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Batch Delay (seconds)</label>
                                    <div class="dc-row-help">How long to wait for follow-up messages before processing. (1–300 s)</div>
                                </div>
                                <div class="dc-row-control">
                                    <input type="number" id="dc-batch-delay" min="1" max="300" step="1" value="8"
                                        class="dc-input dc-input-sm">
                                </div>
                            </div>
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Always Online</label>
                                    <div class="dc-row-help">When on, all configured bot accounts connect on startup. When off, bots only connect if a Schedule daemon task is active for that account.</div>
                                </div>
                                <div class="dc-row-control">
                                    <label class="dc-toggle">
                                        <input type="checkbox" id="dc-always-online" checked>
                                        <span class="dc-toggle-track"></span>
                                        <span class="dc-toggle-thumb"></span>
                                    </label>
                                </div>
                            </div>
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Slash Commands</label>
                                    <div class="dc-row-help">Register /ask, /summarize, and /remember (synced on bot connect).</div>
                                </div>
                                <div class="dc-row-control">
                                    <label class="dc-toggle">
                                        <input type="checkbox" id="dc-slash-enabled" checked>
                                        <span class="dc-toggle-track"></span>
                                        <span class="dc-toggle-thumb"></span>
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="dc-tab-panel" data-tab="replies" id="dc-tab-replies"></div>

                    <div class="dc-tab-panel" data-tab="reactions" id="dc-tab-reactions">
                        <p class="dc-tab-intro">Silent reactions, message edits, image descriptions, and GIF follow-ups.</p>
                        <div id="dc-reactions-fields-mount"></div>
                        <div id="dc-image-settings"></div>
                        <div id="dc-gif-settings"></div>
                    </div>

                    <div class="dc-tab-panel" data-tab="memory" id="dc-tab-memory">
                        <p class="dc-tab-intro">SQLite memory injection and LLM context limits.</p>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Discord Memory</label>
                                    <div class="dc-row-help">Auto-inject relevant past messages into every reply (SQLite, built into this plugin). No tool calls.</div>
                                </div>
                                <div class="dc-row-control">
                                    <label class="dc-toggle">
                                        <input type="checkbox" id="dc-g-memory-enabled" checked>
                                        <span class="dc-toggle-track"></span>
                                        <span class="dc-toggle-thumb"></span>
                                    </label>
                                </div>
                            </div>
                        </div>
                        <div class="dc-card" style="margin-top:8px">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>LLM Max History</label>
                                    <div class="dc-row-help">Max conversation messages sent to the LLM (0 = unlimited; token trim only). Applies globally — affects Discord Bot Reply and main chat. Try 32 for busy servers.</div>
                                </div>
                                <div class="dc-row-control">
                                    <input type="number" id="dc-llm-max-history" min="0" max="500" step="1" value="0"
                                        class="dc-input dc-input-sm">
                                </div>
                            </div>
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Reply Context Limit</label>
                                    <div class="dc-row-help">Token budget for the Discord Bot Reply Schedule task (0 = use global CONTEXT_LIMIT). Includes tool schemas. Try 32000 with the Discord toolset.</div>
                                </div>
                                <div class="dc-row-control">
                                    <input type="number" id="dc-reply-context-limit" min="0" max="200000" step="1000" value="0"
                                        class="dc-input dc-input-sm" style="width:110px">
                                </div>
                            </div>
                            <p id="dc-reply-context-note" class="dc-empty" style="margin:4px 0 0;font-size:0.85em"></p>
                        </div>
                        <div id="dc-tab-memory-detail"></div>
                    </div>

                    <div class="dc-tab-panel" data-tab="profiles" id="dc-tab-profiles">
                        <p class="dc-tab-intro">Inspect per-user profiling state (one profile per user across all servers) and manually reset any profile.</p>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Disposition Legend</label>
                                    <div class="dc-row-help">
                                        Values are 0.00–1.00 internal scores (around 0.50 is neutral, higher means stronger).<br>
                                        <code>fam</code> familiarity · <code>warm</code> warmth · <code>trust</code> trust · <code>play</code> playfulness · <code>pat</code> patience · <code>int</code> interest/engagement.
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Filters</label>
                                    <div class="dc-row-help">Optional filters. Guild id limits to users with message activity in that server.</div>
                                </div>
                                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                                    <input type="text" id="dc-profile-filter-account" class="dc-input dc-input-sm" placeholder="account" style="width:120px">
                                    <input type="text" id="dc-profile-filter-guild" class="dc-input dc-input-sm" placeholder="guild activity filter" style="width:160px">
                                    <input type="text" id="dc-profile-filter-username" class="dc-input dc-input-sm" placeholder="username/display name" style="width:190px">
                                    <button class="dc-btn dc-btn-sm" id="dc-apply-profile-filters">Apply</button>
                                    <button class="dc-btn dc-btn-sm" id="dc-clear-profile-filters">Clear</button>
                                </div>
                            </div>
                        </div>
                        <div class="dc-save-bar" style="margin:12px 0 8px">
                            <button class="dc-btn dc-btn-sm" id="dc-refresh-profiles">Refresh Profiles</button>
                            <button class="dc-btn dc-btn-sm" id="dc-run-profile-distill">Run Distill Now</button>
                            <span id="dc-profile-status" class="dc-status"></span>
                        </div>
                        <div id="dc-profile-list" class="dc-card"><p class="dc-empty">Loading profiles…</p></div>
                    </div>

                    <div class="dc-tab-panel" data-tab="status" id="dc-tab-status"></div>

                    <div class="dc-tab-panel" data-tab="presence" id="dc-tab-presence"></div>

                    <div class="dc-tab-panel" data-tab="advanced" id="dc-tab-advanced"></div>

                    <div class="dc-tab-panel" data-tab="debug" id="dc-tab-debug">
                        <p class="dc-tab-intro">Gate logging and LLM prompt inspection — see what context is sent before each reply.</p>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>Server-side Debug Logging</label>
                                    <div class="dc-row-help">Log gate-by-gate decisions for each incoming message to SQLite. Turn off to stop writing new traces (existing traces remain viewable below).</div>
                                </div>
                                <div class="dc-row-control">
                                    <label class="dc-toggle">
                                        <input type="checkbox" id="dc-debug-trace" checked>
                                        <span class="dc-toggle-track"></span>
                                        <span class="dc-toggle-thumb"></span>
                                    </label>
                                </div>
                            </div>
                        </div>
                        <div class="dc-card">
                            <div class="dc-row">
                                <div class="dc-row-label">
                                    <label>LLM Debug Messaging</label>
                                    <div class="dc-row-help">Keep the last ~40 Discord→LLM exchanges (formatted prompt, injections, history, and model response). Opens in a popup viewer.</div>
                                </div>
                                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center">
                                    <label class="dc-toggle">
                                        <input type="checkbox" id="dc-llm-debug-enabled" checked>
                                        <span class="dc-toggle-track"></span>
                                        <span class="dc-toggle-thumb"></span>
                                    </label>
                                    <button type="button" class="dc-btn dc-btn-sm" id="dc-open-llm-debug">Open Debug Messaging</button>
                                </div>
                            </div>
                        </div>
                        <div class="dc-save-bar" style="margin:12px 0 8px">
                            <button class="dc-btn dc-btn-sm" id="dc-refresh-traces">Refresh Traces</button>
                            <span id="dc-memory-status" class="dc-status"></span>
                        </div>
                        <div id="dc-trace-list" class="dc-card"><p class="dc-empty">Loading traces…</p></div>
                    </div>

                    <div class="dc-save-bar" style="margin-top:12px">
                        <button class="dc-btn dc-btn-primary dc-btn-sm" id="dc-save-global">Save Global Settings</button>
                        <span id="dc-global-status" class="dc-status"></span>
                    </div>
                </div>

                <!-- ── Per-Server Overrides ── -->
                <div class="dc-section">
                    <div class="dc-section-header">
                        <span class="dc-section-label">Per-Server Overrides</span>
                        <span class="dc-section-divider"></span>
                    </div>
                    <p class="dc-empty" style="margin-bottom:10px">
                        Fine-tune behaviour per server. @mentions always bypass all filters.
                    </p>
                    <div id="dc-server-list" class="dc-card">
                        <p class="dc-empty">Loading servers…</p>
                    </div>
                </div>

            </div>
        `;

        _initGlobalSettingsFields(container);
        _wireGlobalTabs(container);
        _loadImageSettings(container).then(() => _loadGlobalSettings(container));

        _loadAccounts(container);
        _loadServers(container);
        _loadTraces(container);
        _loadProfiles(container);

        container.querySelector('#dc-add-account')?.addEventListener('click', () => _showAddForm(container));
        container.querySelector('#dc-save-global')?.addEventListener('click', () => _saveGlobalSettings(container));
        container.querySelector('#dc-refresh-traces')?.addEventListener('click', () => _loadTraces(container));
        container.querySelector('#dc-open-llm-debug')?.addEventListener('click', () => _openLlmDebugModal());
        container.querySelector('#dc-refresh-profiles')?.addEventListener('click', () => _loadProfiles(container));
        container.querySelector('#dc-run-profile-distill')?.addEventListener('click', async () => {
            const btn = container.querySelector('#dc-run-profile-distill');
            const status = container.querySelector('#dc-profile-status');
            if (!btn) return;
            const old = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Running…';
            try {
                const res = await fetch('/api/plugin/leona_discord/profiles/distill-now', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                    body: JSON.stringify({}),
                });
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                if (status) {
                    status.textContent = data.message || 'Distill run complete';
                    status.className = 'dc-status dc-status-ok';
                }
                await _loadProfiles(container);
            } catch (e) {
                if (status) {
                    status.textContent = `Distill failed: ${e.message}`;
                    status.className = 'dc-status dc-status-err';
                }
            } finally {
                btn.disabled = false;
                btn.textContent = old;
            }
        });
        container.querySelector('#dc-apply-profile-filters')?.addEventListener('click', () => _loadProfiles(container));
        container.querySelector('#dc-clear-profile-filters')?.addEventListener('click', () => {
            const a = container.querySelector('#dc-profile-filter-account');
            const g = container.querySelector('#dc-profile-filter-guild');
            const u = container.querySelector('#dc-profile-filter-username');
            if (a) a.value = '';
            if (g) g.value = '';
            if (u) u.value = '';
            _loadProfiles(container);
        });
        container.querySelector('#dc-profile-filter-username')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') _loadProfiles(container);
        });
    },

    load: async () => ({}),
    // ── Hooks called by the host Settings shell's "Save Changes" button ──────
    // The shell calls reg.getSettings(box) to read the form, then reg.save(s)
    // to persist. Previously both were no-op stubs — clicking the prominent
    // "Save Changes" button at the top of the page did nothing for this plugin
    // (the user had to find the small "Save Global Settings" button inside the
    // plugin's card instead, which most people don't notice). Now both buttons
    // save the same data: global settings + any open per-server subforms.
    getSettings: (box) => {
        _activeContainer = box || _activeContainer;
        return _readFieldsGlobal(_activeContainer) || {};
    },
    save: async (settings) => {
        const box = _activeContainer;
        if (!box) {
            console.warn('[leona_discord] reg.save called before render — no container');
            return { success: false, error: 'plugin not rendered yet' };
        }
        return _saveAllSettings(box);
    },
});

// Module-level handle to whichever Settings box the host most recently passed
// to render(). The host's top-level "Save Changes" button calls reg.save()
// without the box argument, so we stash it here when render runs and again
// from getSettings() (which the host does call with the box).
let _activeContainer = null;

// Per-server overrides cover message BEHAVIOUR only. _readFields always
// returns image_* and append_* keys (with default false/'' when the per-
// server subform doesn't have those inputs), which would clobber the
// merged image/append state on a per-server save. Strip them at every
// per-server save point so neither the inline "Save Override" button nor
// the host's top "Save Changes" button can mutate those fields here.
const PRESET_VALUES = {
    lurker: {
        human_response_chance: 5, bot_response_chance: 0, reaction_chance: 70,
        cooldown_seconds: 300, name_match_enabled: false, react_to_any: true,
    },
    helper: {
        human_response_chance: 0, bot_response_chance: 0, reaction_chance: 25,
        cooldown_seconds: 60, name_match_enabled: false, react_to_any: false,
        reply_mode: 'mentions_only',
    },
    chatterbox: {
        human_response_chance: 40, bot_response_chance: 10, reaction_chance: 45,
        cooldown_seconds: 30, name_match_enabled: true, react_to_any: false,
    },
    moderator: {
        human_response_chance: 0, bot_response_chance: 0, reaction_chance: 15,
        cooldown_seconds: 90, name_match_enabled: true, react_to_any: false,
    },
};

const PER_SERVER_FIELDS = new Set([
    'personality_preset', 'reply_mode',
    'bot_response_chance', 'human_response_chance',
    'cooldown_seconds', 'cooldown_scope',
    'name_match_enabled', 'name_match_case_sensitive',
    'reactions_enabled', 'reaction_chance', 'reaction_cooldown_seconds',
    'react_to_trigger', 'react_to_any',
    'allowed_emojis', 'reaction_backend',
    'keyword_triggers', 'always_respond_role_ids',
    'user_denylist', 'user_allowlist', 'bot_allowlist', 'ignore_bots',
]);
function _perServerFields(formEl, prefix) {
    const out = {};
    for (const [k, v] of Object.entries(_readFields(formEl, prefix))) {
        if (PER_SERVER_FIELDS.has(k)) out[k] = v;
    }
    const chKey = formEl.querySelector(`#${prefix}-ch-key`)?.value?.trim();
    const chMode = formEl.querySelector(`#${prefix}-ch-mode`)?.value;
    if (chKey && chMode) {
        out.channels = { [chKey]: { reply_mode: chMode } };
    }
    return out;
}


// ── Field HTML ─────────────────────────────────────────────────────────────────

function _emojiGridHTML(prefix) {
    const customEmojis = (_API_EMOJIS && _API_EMOJIS.length > 0)
        ? _API_EMOJIS.filter(e => typeof e === 'string' && e.startsWith('<'))
        : [];
    return customEmojis.map(e =>
        `<button type="button" class="dc-emoji-btn active" data-emoji="${e}"
            style="font-size:1.35em;padding:4px 6px;border:2px solid var(--accent,#7289da);
                   border-radius:6px;background:var(--bg-secondary);cursor:pointer;
                   transition:opacity 0.15s,border-color 0.15s"
            title="${e}">${e}</button>`
    ).join('');
}


function _replyFieldsHTML(prefix) {
    return `
        <div class="dc-card">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Personality Preset</label>
                    <div class="dc-row-help">Quick-start behaviour profiles. Pick one then fine-tune sliders below.</div>
                </div>
                <div class="dc-row-control">
                    <select id="${prefix}-personality-preset" class="dc-input dc-input-sm">
                        <option value="custom">Custom</option>
                        <option value="lurker">Lurker — low replies, high reactions</option>
                        <option value="helper">Helper — @mentions only</option>
                        <option value="chatterbox">Chatterbox — frequent replies</option>
                        <option value="moderator">Moderator — mentions + keywords</option>
                    </select>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Reply Mode</label>
                    <div class="dc-row-help">Channel-wide default. Per-channel overrides can refine further.</div>
                </div>
                <div class="dc-row-control">
                    <select id="${prefix}-reply-mode" class="dc-input dc-input-sm">
                        <option value="default">Default — use chances below</option>
                        <option value="mentions_only">Mentions + name/keyword only</option>
                        <option value="reactions_only">Reactions only — never reply</option>
                        <option value="never">Never reply or react</option>
                    </select>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Keyword Triggers</label>
                    <div class="dc-row-help">Messages containing these words count as directed at the bot.</div>
                </div>
                <div class="dc-row-control">
                    <input type="text" id="${prefix}-keyword-triggers" class="dc-input" placeholder="help, mod, report">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Always-Respond Role IDs</label>
                    <div class="dc-row-help">Role mentions or members with these roles always queue a reply.</div>
                </div>
                <div class="dc-row-control">
                    <input type="text" id="${prefix}-role-ids" class="dc-input" placeholder="123456789">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>User Denylist / Allowlist</label>
                    <div class="dc-row-help">Discord user IDs. Allowlist empty = everyone allowed.</div>
                </div>
                <div class="dc-row-control" style="display:flex;flex-direction:column;gap:4px">
                    <input type="text" id="${prefix}-user-denylist" class="dc-input" placeholder="deny: user ids">
                    <input type="text" id="${prefix}-user-allowlist" class="dc-input" placeholder="allow: optional">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Ignore Bots</label>
                    <div class="dc-row-help">Skip bot messages except bot allowlist IDs.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-ignore-bots">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                    <input type="text" id="${prefix}-bot-allowlist" class="dc-input" placeholder="bot allowlist ids">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Bot Response Chance</label>
                    <div class="dc-row-help">Chance of responding to another bot's message. 0 = never, 100 = always.</div>
                </div>
                <div class="dc-row-control">
                    <div class="dc-slider-wrap">
                        <input type="range" id="${prefix}-bot-chance" min="0" max="100" step="1" value="15">
                        <span id="${prefix}-bot-chance-lbl" class="dc-slider-val">15%</span>
                    </div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Human Response Chance</label>
                    <div class="dc-row-help">Chance of responding to a human message that doesn't @mention or name-match the bot.</div>
                </div>
                <div class="dc-row-control">
                    <div class="dc-slider-wrap">
                        <input type="range" id="${prefix}-human-chance" min="0" max="100" step="1" value="15">
                        <span id="${prefix}-human-chance-lbl" class="dc-slider-val">15%</span>
                    </div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Cooldown (seconds)</label>
                    <div class="dc-row-help">After responding, ignore non-@mention messages for this long. 0 = no cooldown. (0–600 s)</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-cooldown" min="0" max="600" step="1" value="120"
                        class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Cooldown Scope</label>
                    <div class="dc-row-help">Per Channel silences just that channel; All Channels silences the entire server.</div>
                </div>
                <div class="dc-row-control">
                    <div class="dc-radio-group">
                        <span class="dc-radio-pill">
                            <input type="radio" name="${prefix}-scope" id="${prefix}-scope-ch" value="per_channel" checked>
                            <label for="${prefix}-scope-ch">Per Channel</label>
                        </span>
                        <span class="dc-radio-pill">
                            <input type="radio" name="${prefix}-scope" id="${prefix}-scope-gl" value="global">
                            <label for="${prefix}-scope-gl">All Channels</label>
                        </span>
                    </div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Name Match</label>
                    <div class="dc-row-help">Always respond if the bot's name appears anywhere in a message (soft @mention).</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-name-match" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Case-Sensitive Name Match</label>
                    <div class="dc-row-help">When on, "Remmi" ≠ "remmi". Off by default.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-name-case">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
        </div>
    `;
}


function _reactionsFieldsHTML(prefix) {
    const emojiGrid = _emojiGridHTML(prefix);
    return `
        <!-- Reactions card -->
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Reactions</label>
                    <div class="dc-row-help">Allow the bot to add emoji reactions to messages.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-reactions-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div id="${prefix}-reaction-options" style="display:none">
                <div class="dc-card-inner">
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Reaction Chance</label>
                            <div class="dc-row-help">Even when the bot decides to react, this keeps things unpredictable.</div>
                        </div>
                        <div class="dc-row-control">
                            <div class="dc-slider-wrap">
                                <input type="range" id="${prefix}-reaction-chance" min="0" max="100" step="1" value="50">
                                <span id="${prefix}-reaction-chance-lbl" class="dc-slider-val">50%</span>
                            </div>
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Reaction Cooldown (seconds)</label>
                            <div class="dc-row-help">Separate from reply cooldown — limits how often silent reactions fire.</div>
                        </div>
                        <div class="dc-row-control">
                            <input type="number" id="${prefix}-reaction-cooldown" min="0" max="600" step="1" value="30"
                                class="dc-input dc-input-sm">
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>React to Triggering Message</label>
                            <div class="dc-row-help">Bot can react to the message that was sent to it.</div>
                        </div>
                        <div class="dc-row-control">
                            <label class="dc-toggle">
                                <input type="checkbox" id="${prefix}-react-trigger" checked>
                                <span class="dc-toggle-track"></span>
                                <span class="dc-toggle-thumb"></span>
                            </label>
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>React to Any Message</label>
                            <div class="dc-row-help">Bot can browse channel history and react to any message it chooses, not just the one sent to it.</div>
                        </div>
                        <div class="dc-row-control">
                            <label class="dc-toggle">
                                <input type="checkbox" id="${prefix}-react-any">
                                <span class="dc-toggle-track"></span>
                                <span class="dc-toggle-thumb"></span>
                            </label>
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Sentiment Backend</label>
                            <div class="dc-row-help">
                                VADER is lightweight and always available.
                                DistilBERT (twitter-roberta) is trained on social-media text and more
                                accurate on Discord slang, but requires
                                <code>pip install transformers torch</code> (~500 MB on first use).
                            </div>
                        </div>
                        <div class="dc-row-col">
                            <span class="dc-radio-pill">
                                <input type="radio" name="${prefix}-reaction-backend" id="${prefix}-rb-vader" value="vader" checked>
                                <label for="${prefix}-rb-vader">VADER — rule-based, no extra install</label>
                            </span>
                            <span class="dc-radio-pill">
                                <input type="radio" name="${prefix}-reaction-backend" id="${prefix}-rb-bert" value="distilbert">
                                <label for="${prefix}-rb-bert">DistilBERT — twitter-roberta, better on Discord slang</label>
                            </span>
                        </div>
                    </div>
                    <div class="dc-row" style="flex-direction:column;align-items:flex-start;gap:8px">
                        <div>
                            <div style="font-size:0.84em;font-weight:600;margin-bottom:2px">Allowed Custom Emoji</div>
                            <div class="dc-row-help" style="margin:0">
                                All standard Unicode emoji are always allowed. Only custom server emoji appear here.
                            </div>
                        </div>
                        <div id="${prefix}-emoji-grid" class="dc-emoji-grid">
                            ${emojiGrid}
                        </div>
                        <div class="dc-add-row">
                            <input type="text" id="${prefix}-custom-emoji" class="dc-input"
                                placeholder="&lt;:BUG:123456&gt; &lt;:ALERT:789456&gt; …">
                            <button type="button" id="${prefix}-add-custom-emoji"
                                class="dc-btn dc-btn-sm dc-btn-primary">Add</button>
                        </div>
                        <div class="dc-add-hint">
                            Paste multiple custom emoji codes from Discord, separated by spaces or commas.
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Message edits -->
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Message Edits</label>
                    <div class="dc-row-help">Occasionally edit messages after sending — typo fixes, quick afterthoughts, and optional LLM <code>[edit:…]</code> tags.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-message-edits-enabled" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Auto Typos</label>
                    <div class="dc-row-help">When the user's message has no <code>?</code>, occasionally misspell a common word (e.g. “the” → “teh”), send that version, then edit it correct after a short pause. LLM <code>[edit:…]</code> tags take priority.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-auto-typo-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Auto Typo Chance</label>
                    <div class="dc-row-help">Probability per eligible reply when Auto Typos is on (0–100%). Default 12%.</div>
                </div>
                <div class="dc-row-control">
                    <div class="dc-slider-wrap">
                        <input type="range" id="${prefix}-auto-typo-chance" min="0" max="100" step="1" value="12">
                        <span id="${prefix}-auto-typo-chance-lbl" class="dc-slider-val">12%</span>
                    </div>
                </div>
            </div>
            <div id="${prefix}-auto-typo-delay-options" style="display:none">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Typo Fix Delay (seconds)</label>
                        <div class="dc-row-help">Random pause between sending the typo and editing it correct (min–max).</div>
                    </div>
                    <div class="dc-row-control" style="display:flex;gap:8px;align-items:center">
                        <input type="number" id="${prefix}-auto-typo-delay-min" min="0.5" max="120" step="0.5" value="2"
                            class="dc-input dc-input-sm" style="width:72px">
                        <span class="dc-row-help">to</span>
                        <input type="number" id="${prefix}-auto-typo-delay-max" min="0.5" max="120" step="0.5" value="6"
                            class="dc-input dc-input-sm" style="width:72px">
                    </div>
                </div>
            </div>
        </div>
    `;
}


function _memoryFieldsHTML(prefix) {
    return `
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Recent Chat Lines</label>
                    <div class="dc-row-help">How many prior messages to send to the LLM (5–100). Full channel cache keeps 100 for mentions/search.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-history-inject-limit" min="5" max="100" step="1" value="25"
                        class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Max Chars per Line</label>
                    <div class="dc-row-help">Truncate each history line before injection (80–1000). Images show as “(+N image)”.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-history-line-max-chars" min="80" max="1000" step="10" value="280"
                        class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Memory Token Budget</label>
                    <div class="dc-row-help">Max tokens of older relevant messages (not in recent chat). Default 300.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-memory-max-tokens" min="100" max="1200" step="50" value="300"
                        class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Memory Match Threshold</label>
                    <div class="dc-row-help">Higher = stricter semantic matching (0.0–1.0). Default 0.35.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-memory-threshold" min="0" max="1" step="0.05" value="0.35"
                        class="dc-input dc-input-sm" style="width:90px">
                </div>
            </div>
        </div>
    `;
}


function _profilingFieldsHTML(prefix) {
    const providerHtml = _llmProviderOptionsHtml();
    return `
        <div class="dc-section-header" style="padding-top:14px">
            <span class="dc-section-label">User Profiling</span>
            <span class="dc-section-divider"></span>
        </div>
        <p class="dc-tab-intro" style="margin:0 0 8px">Build per-user relationship memory from Discord interactions. Injected into replies automatically — no tool calls.</p>
        <div class="dc-card">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>User Profiling</label>
                    <div class="dc-row-help">Track who people are and how Leona feels toward them. Off by default — enable when you want personalized recall.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-profiling-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
        </div>
        <div id="${prefix}-profiling-options" style="display:none">
            <div class="dc-card" style="margin-top:6px">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>DMs Only</label>
                        <div class="dc-row-help">When on, profiling and injection only run in direct messages — not guild channels.</div>
                    </div>
                    <div class="dc-row-control">
                        <label class="dc-toggle">
                            <input type="checkbox" id="${prefix}-profiling-dm-only">
                            <span class="dc-toggle-track"></span>
                            <span class="dc-toggle-thumb"></span>
                        </label>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Modulate Reply Chance</label>
                        <div class="dc-row-help">Scale organic reply probability by per-user interest and familiarity.</div>
                    </div>
                    <div class="dc-row-control">
                        <label class="dc-toggle">
                            <input type="checkbox" id="${prefix}-profiling-modulate" checked>
                            <span class="dc-toggle-track"></span>
                            <span class="dc-toggle-thumb"></span>
                        </label>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>LLM Profile Distillation</label>
                        <div class="dc-row-help">Background job extracts facts and summaries from conversations. Runs only when there is queued new content.</div>
                    </div>
                    <div class="dc-row-control">
                        <label class="dc-toggle">
                            <input type="checkbox" id="${prefix}-profiling-use-llm" checked>
                            <span class="dc-toggle-track"></span>
                            <span class="dc-toggle-thumb"></span>
                        </label>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Imperfect Recall</label>
                        <div class="dc-row-help">Occasionally omit profile context for a more human feel.</div>
                    </div>
                    <div class="dc-row-control">
                        <label class="dc-toggle">
                            <input type="checkbox" id="${prefix}-profiling-imperfect">
                            <span class="dc-toggle-track"></span>
                            <span class="dc-toggle-thumb"></span>
                        </label>
                    </div>
                </div>
            </div>
            <div class="dc-card" style="margin-top:6px">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Min Messages Before LLM</label>
                        <div class="dc-row-help">Wait until a user has sent this many messages before running distillation.</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-min-messages" min="1" max="100" step="1" value="5"
                            class="dc-input dc-input-sm">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Profile Token Budget</label>
                        <div class="dc-row-help">Max tokens of per-user context injected per reply.</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-max-tokens" min="80" max="800" step="20" value="300"
                            class="dc-input dc-input-sm">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Fact Confidence Minimum</label>
                        <div class="dc-row-help">Only inject facts at or above this confidence (0.0–1.0).</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-fact-min" min="0" max="1" step="0.05" value="0.6"
                            class="dc-input dc-input-sm" style="width:90px">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Imperfect Recall Chance</label>
                        <div class="dc-row-help">Probability of skipping profile injection when imperfect recall is on.</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-imperfect-chance" min="0" max="0.5" step="0.01" value="0.05"
                            class="dc-input dc-input-sm" style="width:90px">
                    </div>
                </div>
            </div>
            <div id="${prefix}-profiling-llm-options" class="dc-card" style="margin-top:6px">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Distiller Model Provider</label>
                        <div class="dc-row-help">Optional — leave blank to use the default chat model.</div>
                    </div>
                    <div class="dc-row-control">
                        <select id="${prefix}-profiling-provider" class="dc-select dc-input-md">${providerHtml}</select>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Distiller Model Name</label>
                    </div>
                    <div class="dc-row-control">
                        <input type="text" id="${prefix}-profiling-model" class="dc-input dc-input-md" placeholder="model id">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Distiller Interval (minutes)</label>
                        <div class="dc-row-help">Minimum spacing between distillation passes when new content is queued.</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-distill-interval" min="1" max="60" step="1" value="3"
                            class="dc-input dc-input-sm">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Distiller Max Tokens</label>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-profiling-distill-max" min="120" max="800" step="20" value="400"
                            class="dc-input dc-input-sm">
                    </div>
                </div>
            </div>
        </div>
    `;
}


function _appendFieldsHTML(prefix) {
    return `
        <!-- Append to user message card -->
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Append to User Message</label>
                    <div class="dc-row-help">Append custom text to every user message sent to the base model.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-append-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div id="${prefix}-append-options" style="display:none">
                <div class="dc-card-inner">
                    <div class="dc-row" style="flex-direction:column;align-items:flex-start;gap:6px">
                        <div class="dc-row-label">
                            <label>Append Text</label>
                            <div class="dc-row-help">This text will be appended to every user message. Max 2000 chars.</div>
                        </div>
                        <textarea id="${prefix}-append-text" rows="4" maxlength="2000"
                            placeholder="e.g. Remember to keep responses short and casual."
                            class="dc-input" style="width:100%;resize:vertical"></textarea>
                    </div>
                </div>
            </div>
        </div>
    `;
}


function _msgFieldsHTML(prefix) {
    return _replyFieldsHTML(prefix)
        + _reactionsFieldsHTML(prefix)
        + _appendFieldsHTML(prefix);
}


function _initGlobalSettingsFields(container) {
    const p = 'dc-g';
    const mount = (sel, html) => {
        const el = container.querySelector(sel);
        if (el) el.innerHTML = html;
    };
    mount('#dc-tab-replies',
        '<p class="dc-tab-intro">Personality presets, reply chances, cooldowns, and access lists.</p>'
        + _replyFieldsHTML(p));
    mount('#dc-reactions-fields-mount', _reactionsFieldsHTML(p));
    mount('#dc-tab-memory-detail', _memoryFieldsHTML(p) + _profilingFieldsHTML(p));
    mount('#dc-tab-advanced',
        '<p class="dc-tab-intro">Inject extra text into every user message sent to the base model.</p>'
        + _appendFieldsHTML(p));
    mount('#dc-tab-status',
        '<p class="dc-tab-intro">Random Discord status rotation, editable preset lists, and AI-written short statuses.</p>'
        + _statusFieldsHTML(p));
    mount('#dc-tab-presence',
        '<p class="dc-tab-intro">Quiet hours, DMs, sleep, scheduled greetings, outreach, and safety.</p>'
        + _personalityFieldsHTML(p));
    _wireSliders(container, p);
    _wireReactionToggle(container, p);
    _wireAppendToggle(container, p);
    _wirePreset(container, p);
    _renderImageSettings(container, p);
    _renderGifSettings(container, p);
    _wireGreetingTargetPicker(container, p);
    _wireForcedWakeTest(container, p);
    _wirePresenceCyclingToggle(container, p);
    _wireLlmStatusTest(container, p);
    _wireOutreachTargetPicker(container, p);
    _wireLocalScheduleHours(container, p);
    _wireProfilingToggle(container, p);
    _wireAutoTypoToggle(container, p);
}


function _wireAutoTypoToggle(root, prefix) {
    const enabled = root.querySelector(`#${prefix}-auto-typo-enabled`);
    const opts = root.querySelector(`#${prefix}-auto-typo-delay-options`);
    if (!enabled || !opts) return;
    const sync = () => { opts.style.display = enabled.checked ? 'block' : 'none'; };
    enabled.addEventListener('change', sync);
    sync();
}


function _wireProfilingToggle(root, prefix) {
    const enabled = root.querySelector(`#${prefix}-profiling-enabled`);
    const opts = root.querySelector(`#${prefix}-profiling-options`);
    if (!enabled || !opts) return;
    const sync = () => { opts.style.display = enabled.checked ? 'block' : 'none'; };
    enabled.addEventListener('change', sync);
    sync();
}


function _refreshLocalScheduleHourHints(root, prefix) {
    const tzEl = root.querySelector(`#${prefix}-local-tz-name`);
    if (tzEl) tzEl.textContent = _localTimezoneLabel();

    const quietHint = root.querySelector(`#${prefix}-quiet-hours-utc`);
    const quietStart = root.querySelector(`#${prefix}-quiet-start`);
    const quietEnd = root.querySelector(`#${prefix}-quiet-end`);
    if (quietHint && quietStart && quietEnd) {
        const s = _formatHourLabel(_localHourToUtc(quietStart.value));
        const e = _formatHourLabel(_localHourToUtc(quietEnd.value));
        quietHint.textContent = `Saved as ${s} – ${e} UTC`;
    }

    const outreachHint = root.querySelector(`#${prefix}-outreach-active-utc`);
    const outreachStart = root.querySelector(`#${prefix}-outreach-active-start`);
    const outreachEnd = root.querySelector(`#${prefix}-outreach-active-end`);
    if (outreachHint && outreachStart && outreachEnd) {
        const s = _formatHourLabel(_localHourToUtc(outreachStart.value));
        const e = _formatHourLabel(_localHourToUtc(outreachEnd.value));
        outreachHint.textContent = `Saved as ${s} – ${e} UTC`;
    }

    root.querySelectorAll(`[data-local-hour]`).forEach((el) => {
        if (el === quietStart || el === quietEnd || el === outreachStart || el === outreachEnd) return;
        const hintId = el.getAttribute('aria-describedby');
        const hint = hintId ? root.querySelector(`#${hintId}`) : null;
        if (hint) hint.textContent = `Saved as ${_formatHourLabel(_localHourToUtc(el.value))} UTC`;
    });
}

function _wireLocalScheduleHours(root, prefix) {
    _refreshLocalScheduleHourHints(root, prefix);

    const quietStart = root.querySelector(`#${prefix}-quiet-start`);
    const quietEnd = root.querySelector(`#${prefix}-quiet-end`);
    if (quietStart && quietEnd) {
        const updateQuiet = () => _refreshLocalScheduleHourHints(root, prefix);
        quietStart.addEventListener('input', updateQuiet);
        quietEnd.addEventListener('input', updateQuiet);
    }

    const outreachStart = root.querySelector(`#${prefix}-outreach-active-start`);
    const outreachEnd = root.querySelector(`#${prefix}-outreach-active-end`);
    if (outreachStart && outreachEnd) {
        const updateOutreach = () => _refreshLocalScheduleHourHints(root, prefix);
        outreachStart.addEventListener('input', updateOutreach);
        outreachEnd.addEventListener('input', updateOutreach);
    }

    root.querySelectorAll(`[data-local-hour]`).forEach((el) => {
        if (el === quietStart || el === quietEnd || el === outreachStart || el === outreachEnd) return;
        const update = () => _refreshLocalScheduleHourHints(root, prefix);
        el.addEventListener('input', update);
        el.addEventListener('change', update);
    });
}


function _wireGlobalTabs(container) {
    const nav = container.querySelector('#dc-global-tabs');
    if (!nav || nav.dataset.wired) return;
    nav.dataset.wired = '1';
    const section = nav.closest('.dc-section');
    const panels = section ? section.querySelectorAll('.dc-tab-panel') : container.querySelectorAll('.dc-tab-panel');
    nav.querySelectorAll('.dc-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            nav.querySelectorAll('.dc-tab-btn').forEach(b => b.classList.toggle('active', b === btn));
            panels.forEach(panel => panel.classList.toggle('active', panel.dataset.tab === tab));
            if (tab === 'profiles') _loadProfiles(container);
        });
    });
}


function _wireSliders(root, prefix) {
    [
        ['bot-chance',      'bot-chance-lbl'],
        ['human-chance',    'human-chance-lbl'],
        ['reaction-chance', 'reaction-chance-lbl'],
        ['auto-typo-chance', 'auto-typo-chance-lbl'],
    ].forEach(([id, lbl]) => {
        const el = root.querySelector(`#${prefix}-${id}`);
        const lb = root.querySelector(`#${prefix}-${lbl}`);
        if (el && lb) el.addEventListener('input', () => { lb.textContent = `${el.value}%`; });
    });
}


function _wireReactionToggle(root, prefix) {
    const chk  = root.querySelector(`#${prefix}-reactions-enabled`);
    const opts = root.querySelector(`#${prefix}-reaction-options`);
    if (chk && opts) {
        chk.addEventListener('change', () => {
            opts.style.display = chk.checked ? 'block' : 'none';
        });
    }
    // Wire emoji toggle buttons
    root.querySelectorAll(`#${prefix}-emoji-grid .dc-emoji-btn`).forEach(btn => {
        btn.addEventListener('click', () => _toggleEmoji(btn));
    });
    // Wire custom emoji Add button
    const addBtn = root.querySelector(`#${prefix}-add-custom-emoji`);
    if (addBtn) {
        addBtn.addEventListener('click', () => _addCustomEmoji(root, prefix));
    }
}


function _wireAppendToggle(root, prefix) {
    const chk  = root.querySelector(`#${prefix}-append-enabled`);
    const opts = root.querySelector(`#${prefix}-append-options`);
    if (chk && opts) {
        chk.addEventListener('change', () => {
            opts.style.display = chk.checked ? 'block' : 'none';
        });
    }
}


async function _loadImageSettings(container) {
    // Fetch Sapphire's LLM providers to populate provider dropdowns.
    if (!_LLM_PROVIDERS) {
        try {
            const res = await fetch('/api/llm/providers');
            if (res.ok) _LLM_PROVIDERS = await res.json();
        } catch (_) {}
    }
    _refreshLlmProviderDropdowns(container, 'dc-g');
}


function _llmProviderOptionsHtml() {
    const providerOptions = [{ value: '', label: '— Select provider —' }];
    if (_LLM_PROVIDERS && Array.isArray(_LLM_PROVIDERS.providers)) {
        for (const prov of _LLM_PROVIDERS.providers) {
            providerOptions.push({
                value: prov.key || prov.display_name || '',
                label: prov.display_name || prov.key || '',
            });
        }
    }
    return providerOptions.map(o =>
        `<option value="${_esc(o.value)}">${_esc(o.label)}</option>`
    ).join('');
}


function _refreshLlmProviderDropdowns(root, prefix) {
    const keys = [
        'image-provider',
        'gif-query-provider',
        'greeting-provider',
        'outreach-provider',
        'sleep-provider',
        'profiling-provider',
    ];
    for (const key of keys) {
        const sel = root.querySelector(`#${prefix}-${key}`);
        if (!sel || !_LLM_PROVIDERS || !Array.isArray(_LLM_PROVIDERS.providers)) continue;
        const current = sel.value;
        sel.innerHTML = _llmProviderOptionsHtml();
        if (current) sel.value = current;
    }
}

function _renderImageSettings(root, prefix) {
    const container = root.querySelector('#dc-image-settings');
    if (!container) return;

    const providerHtml = _llmProviderOptionsHtml();

    container.innerHTML = `
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Image Understanding</label>
                    <div class="dc-row-help">
                        When a Discord user sends an image or GIF, this plugin asks a vision-capable
                        model to describe it and prepends the description to the user message sent
                        to the base model. <strong>Enable this when your base model is text-only.</strong>
                        When disabled, the image/GIF URL is included in the prompt instead so a
                        vision-capable base model can fetch and view it natively. Sapphire's chat
                        pipeline only sends text to the base model, so the URL is the only signal
                        the base model has that an image was sent.
                    </div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-image-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div id="${prefix}-image-warning" class="dc-warning" style="display:none">
                ⚠ Image Understanding is disabled. When a user sends an image or GIF, the bot
                will only see the Discord CDN URL in its prompt (no description). If your base
                model is vision-capable and can fetch URLs, it can view the image itself. If not,
                the bot will be told an image was sent but won't know what's in it. Enable this
                and pick a vision-capable model below to have the image described for the base
                model.
            </div>
            <div id="${prefix}-image-options" style="display:none">
                <div class="dc-card-inner">
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Vision Model Provider</label>
                            <div class="dc-row-help">Sapphire LLM provider with a vision-capable model (e.g. Claude, OpenAI, Fireworks).</div>
                        </div>
                        <div class="dc-row-control">
                            <select id="${prefix}-image-provider" class="dc-select dc-input-md">
                                ${providerHtml}
                            </select>
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Vision Model Name</label>
                            <div class="dc-row-help">
                                Exact model key from the provider, e.g. "claude-sonnet-4-6", "gpt-4o",
                                "qwen3-vl-235b-a22b-thinking". Must be a vision-capable model.
                            </div>
                        </div>
                        <div class="dc-row-control">
                            <input type="text" id="${prefix}-image-model"
                                placeholder="e.g. claude-sonnet-4-6"
                                class="dc-input dc-input-lg">
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>Vision Model Max Tokens</label>
                            <div class="dc-row-help">
                                Maximum tokens for the vision model's image description.
                                Higher values allow more detailed descriptions. (1–2000)
                            </div>
                        </div>
                        <div class="dc-row-control">
                            <input type="number" id="${prefix}-image-max-tokens" min="1" max="2000" step="1" value="500"
                                class="dc-input dc-input-sm">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const chk = root.querySelector(`#${prefix}-image-enabled`);
    const opts = root.querySelector(`#${prefix}-image-options`);
    const warn = root.querySelector(`#${prefix}-image-warning`);
    if (chk && opts && !chk.dataset.wired) {
        chk.dataset.wired = '1';
        chk.addEventListener('change', () => {
            opts.style.display = chk.checked ? 'block' : 'none';
            if (warn) warn.style.display = chk.checked ? 'none' : 'block';
        });
    }
}


function _renderGifSettings(root, prefix) {
    const container = root.querySelector('#dc-gif-settings');
    if (!container) return;

    const providerHtml = _llmProviderOptionsHtml();

    container.innerHTML = `
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">GIF / Meme Replies</label>
                    <div class="dc-row-help">
                        After the bot sends a text reply, it may automatically follow up with a GIF.
                        Klipy is the recommended provider (Tenor API shuts down June 2026). A small LLM picks the search query, with VADER-style sentiment fallback.
                    </div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-gif-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div id="${prefix}-gif-options" style="display:none">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>GIF Provider</label>
                        <div class="dc-row-help">Klipy — free signup at partner.klipy.com (Tenor-compatible). Giphy — developers.giphy.com. Tenor — legacy only until Jun 2026.</div>
                    </div>
                    <div class="dc-row-control">
                        <select id="${prefix}-gif-search-provider" class="dc-select dc-input-md">
                            <option value="klipy" selected>Klipy (recommended)</option>
                            <option value="giphy">Giphy</option>
                            <option value="tenor">Tenor (legacy)</option>
                        </select>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>GIF API Key</label>
                        <div class="dc-row-help">Provider API key (Klipy or Giphy dashboard).</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="password" id="${prefix}-gif-api-key" class="dc-input dc-input-lg" placeholder="API key" autocomplete="off">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>GIF Reply Chance (%)</label>
                        <div class="dc-row-help">Roll after each text reply — keeps memes from firing every time.</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-gif-chance" min="0" max="100" value="15" class="dc-input dc-input-sm">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>GIF Cooldown (seconds)</label>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-gif-cooldown" min="0" max="3600" value="120" class="dc-input dc-input-sm">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label"><label>Content Filter</label></div>
                    <div class="dc-row-control">
                        <select id="${prefix}-gif-content-filter" class="dc-select dc-input-sm">
                            <option value="off">Off</option>
                            <option value="low">Low</option>
                            <option value="medium" selected>Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Use LLM for GIF Query</label>
                        <div class="dc-row-help">Tiny model picks GIF search terms; falls back to sentiment mapping if empty or NONE.</div>
                    </div>
                    <div class="dc-row-control">
                        <label class="dc-toggle">
                            <input type="checkbox" id="${prefix}-gif-use-llm" checked>
                            <span class="dc-toggle-track"></span>
                            <span class="dc-toggle-thumb"></span>
                        </label>
                    </div>
                </div>
                <div id="${prefix}-gif-llm-options">
                    <div class="dc-row">
                        <div class="dc-row-label">
                            <label>GIF Query Model Provider</label>
                            <div class="dc-row-help">Fast/cheap model recommended.</div>
                        </div>
                        <div class="dc-row-control">
                            <select id="${prefix}-gif-query-provider" class="dc-select dc-input-md">${providerHtml}</select>
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label"><label>GIF Query Model Name</label></div>
                        <div class="dc-row-control">
                            <input type="text" id="${prefix}-gif-model" class="dc-input dc-input-lg" placeholder="e.g. claude-haiku-4-5">
                        </div>
                    </div>
                    <div class="dc-row">
                        <div class="dc-row-label"><label>GIF Query Max Tokens</label></div>
                        <div class="dc-row-control">
                            <input type="number" id="${prefix}-gif-max-tokens" min="20" max="120" value="80" class="dc-input dc-input-sm">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const gifChk = root.querySelector(`#${prefix}-gif-enabled`);
    const gifOpts = root.querySelector(`#${prefix}-gif-options`);
    if (gifChk && gifOpts && !gifChk.dataset.wired) {
        gifChk.dataset.wired = '1';
        gifChk.addEventListener('change', () => {
            gifOpts.style.display = gifChk.checked ? 'block' : 'none';
        });
    }
    const llmChk = root.querySelector(`#${prefix}-gif-use-llm`);
    const llmOpts = root.querySelector(`#${prefix}-gif-llm-options`);
    if (llmChk && llmOpts && !llmChk.dataset.wired) {
        llmChk.dataset.wired = '1';
        llmChk.addEventListener('change', () => {
            llmOpts.style.display = llmChk.checked ? 'block' : 'none';
        });
    }
}


function _statusFieldsHTML(prefix) {
    return `
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Random Discord Status</label>
                    <div class="dc-row-help">While awake, rotate status/activity on a timer. Sleep still shows a sleep-related custom status; when off, status is cleared (online, no activity).</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-presence-cycling">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>LLM Status Chance (%)</label>
                    <div class="dc-row-help">Chance that an awake status refresh asks the LLM for a very short chat-relevant custom status instead of using the preset pool.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <input type="number" id="${prefix}-presence-llm-chance" min="0" max="100" value="0" class="dc-input dc-input-sm" style="width:70px">
                    <button type="button" class="dc-btn dc-btn-sm" id="${prefix}-llm-status-test">Test LLM status</button>
                </div>
            </div>
            <p id="${prefix}-llm-status-test-status" class="dc-row-help" style="margin:-4px 0 8px 0"></p>
            <div id="${prefix}-presence-cycling-options" style="display:none">
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Change Every (minutes)</label>
                        <div class="dc-row-help">How often to pick a new activity while awake (5–180).</div>
                    </div>
                    <div class="dc-row-control">
                        <input type="number" id="${prefix}-presence-interval" min="5" max="180" value="10" class="dc-input dc-input-sm" style="width:70px">
                    </div>
                </div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Default Activities</label>
                        <div class="dc-row-help">Check the statuses to include in the rotation. Loaded from <code>statuses/awake.json</code> (reload settings page after edits). Sleep-only statuses come from <code>statuses/sleep.json</code> and are used automatically while asleep — they are not listed here.</div>
                    </div>
                </div>
                <div id="${prefix}-presence-presets" class="dc-presence-presets"></div>
                <div class="dc-row">
                    <div class="dc-row-label">
                        <label>Custom Activities</label>
                        <div class="dc-row-help">One per line, added on top of checked defaults. Plain text becomes a custom status (e.g. <code>enjoying alone time</code>). Typed prefixes: <code>playing:</code>, <code>listening:</code>, <code>watching:</code>, <code>competing:</code>. Use <code>-</code> for cleared.</div>
                    </div>
                    <div class="dc-row-control" style="flex:1;max-width:420px">
                        <textarea id="${prefix}-presence-custom" class="dc-input" rows="3" placeholder="enjoying alone time&#10;looking forward to Friday&#10;playing: Minecraft"></textarea>
                    </div>
                </div>
            </div>
        </div>
    `;
}


function _personalityFieldsHTML(prefix) {
    const providerHtml = _llmProviderOptionsHtml();
    return `
        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Presence &amp; Access</label>
                    <div class="dc-row-help">Quiet hours, reply pacing, and global schedule behavior.</div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Quiet Hours (local)</label>
                    <div class="dc-row-help">Schedule uses your timezone (<span id="${prefix}-local-tz-name">local</span>). Overnight window when random replies are suppressed.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-quiet-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                    <input type="number" id="${prefix}-quiet-start" data-local-hour min="0" max="23" value="22" class="dc-input dc-input-sm" style="width:60px" title="Start hour (local)" aria-describedby="${prefix}-quiet-hours-utc">
                    <span>to</span>
                    <input type="number" id="${prefix}-quiet-end" data-local-hour min="0" max="23" value="8" class="dc-input dc-input-sm" style="width:60px" title="End hour (local)" aria-describedby="${prefix}-quiet-hours-utc">
                    <select id="${prefix}-quiet-mode" class="dc-input dc-input-sm">
                        <option value="reactions_only">Reactions only</option>
                        <option value="silent">Fully silent</option>
                    </select>
                </div>
            </div>
            <p id="${prefix}-quiet-hours-utc" class="dc-row-help" style="margin:-4px 0 8px 0"></p>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Activity Decay</label>
                    <div class="dc-row-help">Lower reply chance when a channel is very active (last 5 min).</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-activity-decay">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                    <input type="number" id="${prefix}-activity-threshold" min="2" max="100" value="10" class="dc-input dc-input-sm" style="width:60px" title="Msg threshold">
                    <span>msgs ×</span>
                    <input type="number" id="${prefix}-activity-multiplier" min="0" max="1" step="0.1" value="0.5" class="dc-input dc-input-sm" style="width:60px" title="Chance multiplier">
                </div>
            </div>
        </div>

        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Direct Messages</label>
                    <div class="dc-row-help">Separate behaviour for DMs (overrides global chances when set).</div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label"><label>DM Human Reply Chance</label></div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-dm-human-chance" min="0" max="100" value="25" class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label"><label>DM Reaction Chance</label></div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-dm-reaction-chance" min="0" max="100" value="40" class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label"><label>DM Cooldown (seconds)</label></div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-dm-cooldown" min="0" max="600" value="60" class="dc-input dc-input-sm">
                </div>
            </div>
        </div>

        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Sleep Schedule</label>
                    <div class="dc-row-help">At <strong>sleep hour (local)</strong> the bot posts a goodnight (shared or per-channel slot at :00, :15, :30, or :45), then goes dormant. Direct @mentions are held until the <strong>morning greeting</strong> hour; only the newest buffered mentions get replies (limit below).</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-sleep-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label"><label>Sleep Hour (local)</label></div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-sleep-hour" data-local-hour min="0" max="23" value="22" class="dc-input dc-input-sm" aria-describedby="${prefix}-sleep-hour-utc">
                </div>
            </div>
            <p id="${prefix}-sleep-hour-utc" class="dc-row-help" style="margin:-4px 0 8px 0"></p>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Same Time for All Channels</label>
                    <div class="dc-row-help">When on, every greeting channel shares one random goodnight slot (:00, :15, :30, or :45) each night. When off, each channel gets its own slot.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-sleep-same-minute" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Buffered @Mention Replies</label>
                    <div class="dc-row-help">Max replies to overnight @mentions after good morning (newest first; older ones skipped).</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-sleep-buffer-max" min="1" max="10" value="3" class="dc-input dc-input-sm" style="width:60px">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Forced Wake</label>
                    <div class="dc-row-help">If enough @mentions arrive while asleep, the bot wakes briefly, replies (and grumbles), then goes back to sleep.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-sleep-forced-wake-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>@Mentions to Wake</label>
                    <div class="dc-row-help">Number of direct @mentions required within the window below.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-sleep-forced-wake-count" min="2" max="20" value="3" class="dc-input dc-input-sm" style="width:60px">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Wake Window (minutes)</label>
                    <div class="dc-row-help">Rolling window for counting @mentions toward the threshold.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-sleep-forced-wake-window" min="1" max="120" value="15" class="dc-input dc-input-sm" style="width:60px">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Stay Awake (minutes)</label>
                    <div class="dc-row-help">How long @mentions get live replies before the bot goes dormant again.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-sleep-forced-wake-duration" min="5" max="180" value="30" class="dc-input dc-input-sm" style="width:60px">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Test Forced Wake</label>
                    <div class="dc-row-help">Marks selected channels asleep + forced-awake, then queues a test @mention reply (needs <strong>Discord Bot Reply</strong> task with auto-reply). Uses greeting channels when <strong>Use Greeting Channels</strong> is on.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <button type="button" class="dc-btn dc-btn-sm" id="${prefix}-forced-wake-test">Test forced wake</button>
                    <span id="${prefix}-forced-wake-test-status" class="dc-row-help" style="margin:0"></span>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Use Greeting Channels</label>
                    <div class="dc-row-help">Goodnight/dormancy applies to the same channels as Morning Greeting below.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-sleep-use-greeting-targets" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>AI-Generated Goodnight</label>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-sleep-use-llm" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Goodnight Instructions</label>
                <textarea id="${prefix}-sleep-message" class="dc-input" rows="2">Write a short, warm good-night message for this Discord channel. Sound like a friendly community member signing off for the night. One or two sentences. Vary your wording.</textarea>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Goodnight Fallback</label>
                <input type="text" id="${prefix}-sleep-fallback" class="dc-input" value="Good night, everyone! 🌙">
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Goodnight Model (optional)</label>
                    <div class="dc-row-help">Leave blank to use greeting model or default chat provider.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                    <select id="${prefix}-sleep-provider" class="dc-select dc-input-md">${providerHtml}</select>
                    <input type="text" id="${prefix}-sleep-model" class="dc-input" placeholder="model name">
                    <input type="number" id="${prefix}-sleep-max-tokens" min="40" max="500" value="180" class="dc-input dc-input-sm" style="width:70px">
                </div>
            </div>
        </div>

        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Morning Greeting</label>
                    <div class="dc-row-help">Scheduled via Sapphire continuity (hourly cron). Use <strong>Send test greeting</strong> to try it now. Times are in your local timezone.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-greeting-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label"><label>Wake Hour (local)</label></div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-greeting-hour" data-local-hour min="0" max="23" value="9" class="dc-input dc-input-sm" aria-describedby="${prefix}-greeting-hour-utc">
                </div>
            </div>
            <p id="${prefix}-greeting-hour-utc" class="dc-row-help" style="margin:-4px 0 8px 0"></p>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>AI-Generated Greeting</label>
                    <div class="dc-row-help">When on, the LLM writes a fresh message each day from the instructions below.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-greeting-use-llm" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Greeting Instructions</label>
                <div class="dc-row-help">Prompt for the LLM — not posted verbatim. Describe tone, length, and style.</div>
                <textarea id="${prefix}-greeting-message" class="dc-input" rows="3">Write a short, warm good-morning message for this Discord channel. Sound like a friendly community member. One or two sentences. Vary your wording each day.</textarea>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Fallback Message</label>
                <div class="dc-row-help">Used if the LLM is unavailable or returns empty text.</div>
                <input type="text" id="${prefix}-greeting-fallback" class="dc-input" value="Good morning, everyone! ☀️">
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Greeting Model (optional)</label>
                    <div class="dc-row-help">Leave blank to use the default chat provider. Otherwise set provider + model name.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                    <select id="${prefix}-greeting-provider" class="dc-select dc-input-md">${providerHtml}</select>
                    <input type="text" id="${prefix}-greeting-model" class="dc-input" placeholder="model name">
                    <input type="number" id="${prefix}-greeting-max-tokens" min="40" max="500" value="180" class="dc-input dc-input-sm" style="width:70px" title="Max tokens">
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Greeting Channels</label>
                <div class="dc-row-help">Select channels from connected bots. Requires the bot to be online (Always Online or an active Schedule task).</div>
                <div id="${prefix}-greeting-selected" class="dc-greeting-selected">
                    <span class="dc-row-help" style="margin:0">None selected</span>
                </div>
                <div class="dc-greeting-picker-toolbar">
                    <button type="button" class="dc-btn dc-btn-sm" id="${prefix}-greeting-refresh">Refresh from Discord</button>
                    <button type="button" class="dc-btn dc-btn-sm" id="${prefix}-greeting-test">Send test greeting</button>
                    <span id="${prefix}-greeting-picker-status" class="dc-row-help"></span>
                    <span id="${prefix}-greeting-test-status" class="dc-row-help"></span>
                </div>
                <div id="${prefix}-greeting-picker" class="dc-greeting-picker">
                    <p class="dc-empty" style="margin:0">Click Refresh to load servers and channels.</p>
                </div>
                <textarea id="${prefix}-greeting-targets" class="dc-input" rows="2" style="display:none" aria-hidden="true"></textarea>
                <details class="dc-greeting-advanced">
                    <summary>Advanced: edit raw target lines</summary>
                    <textarea id="${prefix}-greeting-targets-raw" class="dc-input" rows="2" placeholder="account:guild_id:channel_id"></textarea>
                </details>
            </div>
        </div>

        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Quiet Channel Outreach</label>
                    <div class="dc-row-help">When a channel goes quiet, the bot may casually restart conversation (checked every 15 min). Outreach uses your local timezone for active hours.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-outreach-enabled">
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Quiet After (minutes)</label>
                    <div class="dc-row-help">No human messages for this long before the channel is eligible.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-outreach-quiet-minutes" min="30" max="1440" value="240" class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Cooldown (hours)</label>
                    <div class="dc-row-help">Minimum time between outreach messages in the same channel.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-outreach-cooldown-hours" min="1" max="72" value="8" class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Skip Chance (%)</label>
                    <div class="dc-row-help">Random chance to stay silent even when quiet — avoids robotic regularity.</div>
                </div>
                <div class="dc-row-control">
                    <input type="number" id="${prefix}-outreach-skip-chance" min="0" max="90" value="25" class="dc-input dc-input-sm">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Active Hours (local)</label>
                    <div class="dc-row-help">Only outreach between these local hours. Respects global Quiet Hours too.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:6px;align-items:center">
                    <input type="number" id="${prefix}-outreach-active-start" data-local-hour min="0" max="23" value="10" class="dc-input dc-input-sm" style="width:60px" aria-describedby="${prefix}-outreach-active-utc">
                    <span class="dc-row-help" style="margin:0">to</span>
                    <input type="number" id="${prefix}-outreach-active-end" data-local-hour min="0" max="23" value="21" class="dc-input dc-input-sm" style="width:60px" aria-describedby="${prefix}-outreach-active-utc">
                </div>
            </div>
            <p id="${prefix}-outreach-active-utc" class="dc-row-help" style="margin:-4px 0 8px 0"></p>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>AI-Generated Message</label>
                    <div class="dc-row-help">LLM writes a fresh opener from the instructions below.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-outreach-use-llm" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Typing Indicator</label>
                    <div class="dc-row-help">Brief typing pause before sending — feels more human.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-outreach-typing" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Outreach Instructions</label>
                <div class="dc-row-help">Prompt for the LLM — not posted verbatim.</div>
                <textarea id="${prefix}-outreach-message" class="dc-input" rows="3">Casually restart conversation in this Discord channel. Write one short message like a friend checking in — not an announcement or bot greeting. A question or light observation works well. Vary your wording.</textarea>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Fallback Message</label>
                <div class="dc-row-help">Used if the LLM is unavailable or returns empty text.</div>
                <input type="text" id="${prefix}-outreach-fallback" class="dc-input" value="Anyone around? 👀">
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Outreach Model (optional)</label>
                    <div class="dc-row-help">Leave blank to use the default chat provider.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                    <select id="${prefix}-outreach-provider" class="dc-select dc-input-md">${providerHtml}</select>
                    <input type="text" id="${prefix}-outreach-model" class="dc-input" placeholder="model name">
                    <input type="number" id="${prefix}-outreach-max-tokens" min="40" max="500" value="180" class="dc-input dc-input-sm" style="width:70px" title="Max tokens">
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Outreach Channels</label>
                <div class="dc-row-help">Select channels to monitor for quiet periods.</div>
                <div id="${prefix}-outreach-selected" class="dc-greeting-selected">
                    <span class="dc-row-help" style="margin:0">None selected</span>
                </div>
                <div class="dc-greeting-picker-toolbar">
                    <button type="button" class="dc-btn dc-btn-sm" id="${prefix}-outreach-refresh">Refresh from Discord</button>
                    <span id="${prefix}-outreach-picker-status" class="dc-row-help"></span>
                </div>
                <div id="${prefix}-outreach-picker" class="dc-greeting-picker">
                    <p class="dc-empty" style="margin:0">Click Refresh to load servers and channels.</p>
                </div>
                <textarea id="${prefix}-outreach-targets" class="dc-input" rows="2" style="display:none" aria-hidden="true"></textarea>
                <details class="dc-greeting-advanced">
                    <summary>Advanced: edit raw target lines</summary>
                    <textarea id="${prefix}-outreach-targets-raw" class="dc-input" rows="2" placeholder="account:guild_id:channel_id"></textarea>
                </details>
            </div>
        </div>

        <div class="dc-card" style="margin-top:6px">
            <div class="dc-row">
                <div class="dc-row-label">
                    <label style="font-weight:600">Safety &amp; Moderation</label>
                    <div class="dc-row-help">Permission checks, rate limits, and content filtering before the LLM runs.</div>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Check Bot Permissions</label>
                    <div class="dc-row-help">Skip processing when the bot lacks Send Messages in a channel.</div>
                </div>
                <div class="dc-row-control">
                    <label class="dc-toggle">
                        <input type="checkbox" id="${prefix}-safety-perms" checked>
                        <span class="dc-toggle-track"></span>
                        <span class="dc-toggle-thumb"></span>
                    </label>
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Rate Limit</label>
                    <div class="dc-row-help">Min seconds between messages from the same user + burst cap per window.</div>
                </div>
                <div class="dc-row-control" style="display:flex;gap:8px;align-items:center">
                    <input type="number" id="${prefix}-rate-limit-secs" min="0" max="120" value="2" class="dc-input dc-input-sm" style="width:60px" title="Min gap (0=off)">
                    <span>sec · burst</span>
                    <input type="number" id="${prefix}-rate-limit-burst" min="1" max="50" value="8" class="dc-input dc-input-sm" style="width:50px">
                    <span>/</span>
                    <input type="number" id="${prefix}-rate-limit-window" min="10" max="600" value="60" class="dc-input dc-input-sm" style="width:50px" title="Window seconds">
                    <span>sec</span>
                </div>
            </div>
            <div class="dc-row" style="flex-direction:column;align-items:stretch">
                <label>Content Blocklist</label>
                <div class="dc-row-help">Comma-separated words/phrases — matching messages are dropped (logged in debug traces).</div>
                <input type="text" id="${prefix}-content-blocklist" class="dc-input" placeholder="spam, slur, …">
            </div>
        </div>
    `;
}


function _wirePreset(root, prefix) {
    const sel = root.querySelector(`#${prefix}-personality-preset`);
    if (!sel) return;
    sel.addEventListener('change', () => {
        const p = sel.value;
        if (p === 'custom' || !PRESET_VALUES[p]) return;
        const vals = PRESET_VALUES[p];
        const v = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.value = val; };
        const c = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.checked = !!val; };
        const lb = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.textContent = `${val}%`; };
        if (vals.bot_response_chance != null) { v(`${prefix}-bot-chance`, vals.bot_response_chance); lb(`${prefix}-bot-chance-lbl`, vals.bot_response_chance); }
        if (vals.human_response_chance != null) { v(`${prefix}-human-chance`, vals.human_response_chance); lb(`${prefix}-human-chance-lbl`, vals.human_response_chance); }
        if (vals.reaction_chance != null) { v(`${prefix}-reaction-chance`, vals.reaction_chance); lb(`${prefix}-reaction-chance-lbl`, vals.reaction_chance); }
        if (vals.cooldown_seconds != null) v(`${prefix}-cooldown`, vals.cooldown_seconds);
        if (vals.name_match_enabled != null) c(`${prefix}-name-match`, vals.name_match_enabled);
        if (vals.react_to_any != null) c(`${prefix}-react-any`, vals.react_to_any);
        if (vals.reply_mode != null) v(`${prefix}-reply-mode`, vals.reply_mode);
        if (p === 'moderator') {
            const kw = root.querySelector(`#${prefix}-keyword-triggers`);
            if (kw && !kw.value.trim()) kw.value = 'help, mod, report, admin';
        }
    });
}


const _greetingSelections = {};
const _greetingCatalog = {};


function _getGreetingSet(prefix) {
    if (!_greetingSelections[prefix]) _greetingSelections[prefix] = new Set();
    return _greetingSelections[prefix];
}


function _greetingLabel(value) {
    return _greetingCatalog[value]?.label || value;
}


function _syncGreetingTargets(root, prefix) {
    const lines = [..._getGreetingSet(prefix)].sort();
    const hidden = root.querySelector(`#${prefix}-greeting-targets`);
    const raw = root.querySelector(`#${prefix}-greeting-targets-raw`);
    if (hidden) hidden.value = lines.join('\n');
    if (raw && document.activeElement !== raw) raw.value = lines.join('\n');
}


function _renderGreetingChips(root, prefix) {
    const box = root.querySelector(`#${prefix}-greeting-selected`);
    if (!box) return;
    const sel = _getGreetingSet(prefix);
    box.innerHTML = '';
    if (!sel.size) {
        box.innerHTML = '<span class="dc-row-help" style="margin:0">None selected</span>';
        return;
    }
    [...sel].sort().forEach(value => {
        const chip = document.createElement('span');
        chip.className = 'dc-greeting-chip';
        chip.title = value;
        const text = document.createElement('span');
        text.textContent = _greetingLabel(value);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('aria-label', 'Remove');
        btn.textContent = '×';
        btn.addEventListener('click', () => {
            sel.delete(value);
            const cb = root.querySelector(`#${prefix}-greeting-picker input[data-value="${CSS.escape(value)}"]`);
            if (cb) cb.checked = false;
            _renderGreetingChips(root, prefix);
            _syncGreetingTargets(root, prefix);
        });
        chip.appendChild(text);
        chip.appendChild(btn);
        box.appendChild(chip);
    });
}


function _populateGreetingTargets(root, prefix, targets) {
    if (!root.querySelector(`#${prefix}-greeting-picker`)) return;
    const sel = _getGreetingSet(prefix);
    sel.clear();
    (targets || []).forEach(t => {
        const line = String(t).trim();
        if (line) sel.add(line);
    });
    _syncGreetingTargets(root, prefix);
    _renderGreetingChips(root, prefix);
    sel.forEach(value => {
        const cb = root.querySelector(`#${prefix}-greeting-picker input[data-value="${CSS.escape(value)}"]`);
        if (cb) cb.checked = true;
    });
}


function _renderGreetingPickerList(root, prefix, targets) {
    const box = root.querySelector(`#${prefix}-greeting-picker`);
    if (!box) return;
    box.innerHTML = '';
    if (!targets.length) {
        box.innerHTML = '<p class="dc-empty" style="margin:0">No text channels found. Connect a bot and ensure it is online.</p>';
        return;
    }
    const groups = {};
    targets.forEach(t => {
        _greetingCatalog[t.value] = t;
        const key = `${t.account}|${t.guild_id}`;
        if (!groups[key]) groups[key] = { title: `${t.account} · ${t.guild_name}`, items: [] };
        groups[key].items.push(t);
    });
    const sel = _getGreetingSet(prefix);
    Object.values(groups).forEach(group => {
        const gEl = document.createElement('div');
        gEl.className = 'dc-greeting-group';
        const title = document.createElement('div');
        title.className = 'dc-greeting-group-title';
        title.textContent = group.title;
        gEl.appendChild(title);
        group.items.forEach(t => {
            const label = document.createElement('label');
            label.className = 'dc-greeting-option';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.dataset.value = t.value;
            cb.checked = sel.has(t.value);
            cb.addEventListener('change', () => {
                if (cb.checked) sel.add(t.value);
                else sel.delete(t.value);
                _renderGreetingChips(root, prefix);
                _syncGreetingTargets(root, prefix);
            });
            const span = document.createElement('span');
            span.textContent = `#${t.channel_name}`;
            label.appendChild(cb);
            label.appendChild(span);
            gEl.appendChild(label);
        });
        box.appendChild(gEl);
    });
}


async function _loadGreetingPicker(root, prefix) {
    const status = root.querySelector(`#${prefix}-greeting-picker-status`);
    const btn = root.querySelector(`#${prefix}-greeting-refresh`);
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Loading…';
    try {
        const res = await fetch('/api/plugin/leona_discord/greeting/targets');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        _renderGreetingPickerList(root, prefix, data.targets || []);
        const n = (data.targets || []).length;
        if (status) {
            status.textContent = n
                ? `${n} channel${n === 1 ? '' : 's'} available`
                : 'No connected bots — enable Always Online or run a Schedule task';
        }
        _renderGreetingChips(root, prefix);
    } catch (e) {
        if (status) status.textContent = e.message || 'Failed to load';
    }
    if (btn) btn.disabled = false;
}


async function _sendTestGreeting(root, prefix) {
    const btn = root.querySelector(`#${prefix}-greeting-test`);
    const status = root.querySelector(`#${prefix}-greeting-test-status`);
    if (!btn) return;

    _syncGreetingTargets(root, prefix);
    const targets = [..._getGreetingSet(prefix)];
    if (!targets.length) {
        if (status) {
            status.textContent = 'Select at least one greeting channel first.';
            status.style.color = 'var(--error, #f04747)';
        }
        return;
    }

    btn.disabled = true;
    if (status) {
        status.textContent = 'Sending…';
        status.style.color = '';
    }

    const v = (id) => root.querySelector(`#${id}`)?.value ?? '';
    const b = (id) => root.querySelector(`#${id}`)?.checked ?? false;
    const i = (id) => parseInt(v(id) || '0', 10);

    try {
        const res = await fetch('/api/plugin/leona_discord/greeting/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
            body: JSON.stringify({
                greeting_use_llm: b(`${prefix}-greeting-use-llm`),
                greeting_message: v(`${prefix}-greeting-message`),
                greeting_fallback: v(`${prefix}-greeting-fallback`),
                greeting_model_provider: v(`${prefix}-greeting-provider`),
                greeting_model_name: v(`${prefix}-greeting-model`),
                greeting_max_tokens: i(`${prefix}-greeting-max-tokens`),
                greeting_targets: targets,
            }),
        });
        const data = await res.json();
        if (status) {
            status.textContent = data.message || data.error || (data.success ? 'Sent' : 'Failed');
            status.style.color = data.success ? 'var(--success, #43b581)' : 'var(--error, #f04747)';
        }
    } catch (e) {
        if (status) {
            status.textContent = e.message || 'Request failed';
            status.style.color = 'var(--error, #f04747)';
        }
    }
    btn.disabled = false;
}


async function _sendTestForcedWake(root, prefix) {
    const btn = root.querySelector(`#${prefix}-forced-wake-test`);
    const status = root.querySelector(`#${prefix}-forced-wake-test-status`);
    if (!btn) return;

    _syncGreetingTargets(root, prefix);
    const useGreeting = root.querySelector(`#${prefix}-sleep-use-greeting-targets`)?.checked !== false;
    const targets = useGreeting ? [..._getGreetingSet(prefix)] : [];

    if (useGreeting && !targets.length) {
        if (status) {
            status.textContent = 'Select at least one greeting channel first.';
            status.style.color = 'var(--error, #f04747)';
        }
        return;
    }

    btn.disabled = true;
    if (status) {
        status.textContent = 'Queuing…';
        status.style.color = '';
    }

    const v = (id) => root.querySelector(`#${id}`)?.value ?? '';
    const b = (id) => root.querySelector(`#${id}`)?.checked ?? false;
    const i = (id) => parseInt(v(id) || '0', 10);

    try {
        const res = await fetch('/api/plugin/leona_discord/sleep/forced-wake/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
            body: JSON.stringify({
                sleep_forced_wake_enabled: b(`${prefix}-sleep-forced-wake-enabled`),
                sleep_forced_wake_mention_count: i(`${prefix}-sleep-forced-wake-count`),
                sleep_forced_wake_window_minutes: i(`${prefix}-sleep-forced-wake-window`),
                sleep_forced_wake_duration_minutes: i(`${prefix}-sleep-forced-wake-duration`),
                sleep_use_greeting_targets: useGreeting,
                greeting_targets: targets,
            }),
        });
        const data = await res.json();
        if (status) {
            status.textContent = data.message || data.error || (data.success ? 'Queued' : 'Failed');
            status.style.color = data.success ? 'var(--success, #43b581)' : 'var(--error, #f04747)';
        }
    } catch (e) {
        if (status) {
            status.textContent = e.message || 'Request failed';
            status.style.color = 'var(--error, #f04747)';
        }
    }
    btn.disabled = false;
}


function _syncPresenceCyclingToggle(root, prefix) {
    const enabled = root.querySelector(`#${prefix}-presence-cycling`);
    const opts = root.querySelector(`#${prefix}-presence-cycling-options`);
    if (!enabled || !opts) return;
    opts.style.display = enabled.checked ? 'block' : 'none';
}


function _wirePresenceCyclingToggle(root, prefix) {
    const enabled = root.querySelector(`#${prefix}-presence-cycling`);
    if (!enabled || enabled.dataset.wired) return;
    enabled.dataset.wired = '1';
    enabled.addEventListener('change', () => _syncPresenceCyclingToggle(root, prefix));
    _syncPresenceCyclingToggle(root, prefix);
}


async function _sendTestLlmStatus(root, prefix) {
    const btn = root.querySelector(`#${prefix}-llm-status-test`);
    const status = root.querySelector(`#${prefix}-llm-status-test-status`);
    if (!btn) return;

    btn.disabled = true;
    if (status) {
        status.textContent = 'Generating…';
        status.style.color = '';
    }

    try {
        const res = await fetch('/api/plugin/leona_discord/status/llm/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
            body: JSON.stringify({ apply: true }),
        });
        const data = await res.json();
        if (status) {
            status.textContent = data.message || data.error || (data.success ? 'Done' : 'Failed');
            status.style.color = data.success ? 'var(--success, #43b581)' : 'var(--error, #f04747)';
        }
    } catch (e) {
        if (status) {
            status.textContent = e.message || 'Request failed';
            status.style.color = 'var(--error, #f04747)';
        }
    }
    btn.disabled = false;
}


function _wireLlmStatusTest(root, prefix) {
    const testBtn = root.querySelector(`#${prefix}-llm-status-test`);
    if (testBtn && !testBtn.dataset.wired) {
        testBtn.dataset.wired = '1';
        testBtn.addEventListener('click', () => _sendTestLlmStatus(root, prefix));
    }
}


function _wireForcedWakeTest(root, prefix) {
    const testBtn = root.querySelector(`#${prefix}-forced-wake-test`);
    if (testBtn && !testBtn.dataset.wired) {
        testBtn.dataset.wired = '1';
        testBtn.addEventListener('click', () => _sendTestForcedWake(root, prefix));
    }
}


function _wireGreetingTargetPicker(root, prefix) {
    const refresh = root.querySelector(`#${prefix}-greeting-refresh`);
    if (refresh && !refresh.dataset.wired) {
        refresh.dataset.wired = '1';
        refresh.addEventListener('click', () => _loadGreetingPicker(root, prefix));
    }
    const testBtn = root.querySelector(`#${prefix}-greeting-test`);
    if (testBtn && !testBtn.dataset.wired) {
        testBtn.dataset.wired = '1';
        testBtn.addEventListener('click', () => _sendTestGreeting(root, prefix));
    }
    const raw = root.querySelector(`#${prefix}-greeting-targets-raw`);
    if (raw && !raw.dataset.wired) {
        raw.dataset.wired = '1';
        const applyRaw = () => {
            const lines = raw.value.split('\n').map(s => s.trim()).filter(Boolean);
            _populateGreetingTargets(root, prefix, lines);
        };
        raw.addEventListener('change', applyRaw);
        raw.addEventListener('blur', applyRaw);
    }
}


const _outreachSelections = {};


function _getOutreachSet(prefix) {
    if (!_outreachSelections[prefix]) _outreachSelections[prefix] = new Set();
    return _outreachSelections[prefix];
}


function _syncOutreachTargets(root, prefix) {
    const lines = [..._getOutreachSet(prefix)].sort();
    const hidden = root.querySelector(`#${prefix}-outreach-targets`);
    const raw = root.querySelector(`#${prefix}-outreach-targets-raw`);
    if (hidden) hidden.value = lines.join('\n');
    if (raw && document.activeElement !== raw) raw.value = lines.join('\n');
}


function _renderOutreachChips(root, prefix) {
    const box = root.querySelector(`#${prefix}-outreach-selected`);
    if (!box) return;
    const sel = _getOutreachSet(prefix);
    box.innerHTML = '';
    if (!sel.size) {
        box.innerHTML = '<span class="dc-row-help" style="margin:0">None selected</span>';
        return;
    }
    [...sel].sort().forEach(value => {
        const chip = document.createElement('span');
        chip.className = 'dc-greeting-chip';
        chip.title = value;
        const text = document.createElement('span');
        text.textContent = _greetingLabel(value);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('aria-label', 'Remove');
        btn.textContent = '×';
        btn.addEventListener('click', () => {
            sel.delete(value);
            const cb = root.querySelector(`#${prefix}-outreach-picker input[data-value="${CSS.escape(value)}"]`);
            if (cb) cb.checked = false;
            _renderOutreachChips(root, prefix);
            _syncOutreachTargets(root, prefix);
        });
        chip.appendChild(text);
        chip.appendChild(btn);
        box.appendChild(chip);
    });
}


function _populateOutreachTargets(root, prefix, targets) {
    if (!root.querySelector(`#${prefix}-outreach-picker`)) return;
    const sel = _getOutreachSet(prefix);
    sel.clear();
    (targets || []).forEach(t => {
        const line = String(t).trim();
        if (line) sel.add(line);
    });
    _syncOutreachTargets(root, prefix);
    _renderOutreachChips(root, prefix);
    sel.forEach(value => {
        const cb = root.querySelector(`#${prefix}-outreach-picker input[data-value="${CSS.escape(value)}"]`);
        if (cb) cb.checked = true;
    });
}


function _renderOutreachPickerList(root, prefix, targets) {
    const box = root.querySelector(`#${prefix}-outreach-picker`);
    if (!box) return;
    box.innerHTML = '';
    if (!targets.length) {
        box.innerHTML = '<p class="dc-empty" style="margin:0">No text channels found. Connect a bot and ensure it is online.</p>';
        return;
    }
    const groups = {};
    targets.forEach(t => {
        _greetingCatalog[t.value] = t;
        const key = `${t.account}|${t.guild_id}`;
        if (!groups[key]) groups[key] = { title: `${t.account} · ${t.guild_name}`, items: [] };
        groups[key].items.push(t);
    });
    const sel = _getOutreachSet(prefix);
    Object.values(groups).forEach(group => {
        const gEl = document.createElement('div');
        gEl.className = 'dc-greeting-group';
        const title = document.createElement('div');
        title.className = 'dc-greeting-group-title';
        title.textContent = group.title;
        gEl.appendChild(title);
        group.items.forEach(t => {
            const label = document.createElement('label');
            label.className = 'dc-greeting-option';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.dataset.value = t.value;
            cb.checked = sel.has(t.value);
            cb.addEventListener('change', () => {
                if (cb.checked) sel.add(t.value);
                else sel.delete(t.value);
                _renderOutreachChips(root, prefix);
                _syncOutreachTargets(root, prefix);
            });
            const span = document.createElement('span');
            span.textContent = `#${t.channel_name}`;
            label.appendChild(cb);
            label.appendChild(span);
            gEl.appendChild(label);
        });
        box.appendChild(gEl);
    });
}


async function _loadOutreachPicker(root, prefix) {
    const status = root.querySelector(`#${prefix}-outreach-picker-status`);
    const btn = root.querySelector(`#${prefix}-outreach-refresh`);
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Loading…';
    try {
        const res = await fetch('/api/plugin/leona_discord/greeting/targets');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        _renderOutreachPickerList(root, prefix, data.targets || []);
        const n = (data.targets || []).length;
        if (status) {
            status.textContent = n
                ? `${n} channel${n === 1 ? '' : 's'} available`
                : 'No connected bots — enable Always Online or run a Schedule task';
        }
        _renderOutreachChips(root, prefix);
    } catch (e) {
        if (status) status.textContent = e.message || 'Failed to load';
    }
    if (btn) btn.disabled = false;
}


function _wireOutreachTargetPicker(root, prefix) {
    const refresh = root.querySelector(`#${prefix}-outreach-refresh`);
    if (refresh && !refresh.dataset.wired) {
        refresh.dataset.wired = '1';
        refresh.addEventListener('click', () => _loadOutreachPicker(root, prefix));
    }
    const raw = root.querySelector(`#${prefix}-outreach-targets-raw`);
    if (raw && !raw.dataset.wired) {
        raw.dataset.wired = '1';
        const applyRaw = () => {
            const lines = raw.value.split('\n').map(s => s.trim()).filter(Boolean);
            _populateOutreachTargets(root, prefix, lines);
        };
        raw.addEventListener('change', applyRaw);
        raw.addEventListener('blur', applyRaw);
    }
}


function _wireImageToggle(root, prefix) {
    // Wired inside _renderImageSettings via the change listener on the checkbox
}


function _toggleEmoji(btn) {
    const active = btn.classList.contains('active');
    if (active) {
        btn.classList.remove('active');
        btn.style.borderColor = 'var(--border)';
        btn.style.opacity = '0.35';
    } else {
        btn.classList.add('active');
        btn.style.borderColor = 'var(--accent,#7289da)';
        btn.style.opacity = '1';
    }
}


function _addCustomEmoji(root, prefix) {
    const input = root.querySelector(`#${prefix}-custom-emoji`);
    const grid  = root.querySelector(`#${prefix}-emoji-grid`);
    if (!input || !grid) return;
    const value = input.value.trim();
    if (!value) return;

    // Parse all custom Discord emoji from the input (handles comma, space, or newline separated)
    // Accepts both <:name:ID> (with ID) and <:name:> or <a:name:> (without ID - resolved at runtime)
    const emojiSet = new Set();
    const re = /<a?:\w+:(?:\d+)?>/g;
    let match;
    while ((match = re.exec(value)) !== null) {
        emojiSet.add(match[0]);
    }

    if (emojiSet.size === 0) return;

    emojiSet.forEach(emoji => {
        const existing = grid.querySelector(`[data-emoji="${CSS.escape(emoji)}"]`);
        if (existing) {
            existing.classList.add('active');
            existing.style.borderColor = 'var(--accent,#7289da)';
            existing.style.opacity = '1';
        } else {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'dc-emoji-btn active';
            btn.dataset.emoji = emoji;
            btn.textContent = emoji;
            btn.title = emoji;
            btn.style.cssText = (
                'font-size:1.35em;padding:4px 6px;border:2px solid var(--accent,#7289da);'
                + 'border-radius:6px;background:var(--bg-secondary);cursor:pointer;'
                + 'transition:opacity 0.15s,border-color 0.15s'
            );
            btn.addEventListener('click', () => _toggleEmoji(btn));
            grid.appendChild(btn);
        }
    });

    input.value = '';
}


function _listToStr(val) {
    if (!val) return '';
    if (Array.isArray(val)) return val.join(', ');
    return String(val);
}


const _PRESENCE_CATEGORY_LABELS = {
    none: 'No activity',
    custom: 'Custom status',
    listening: 'Listening',
    watching: 'Watching',
    playing: 'Playing',
    competing: 'Competing',
    studying: 'Studying',
    working: 'Working',
    eating: 'Eating',
};
const _PRESENCE_CATEGORY_ORDER = [
    'none', 'custom', 'listening', 'watching', 'playing', 'competing',
    'studying', 'working', 'eating',
];


function _renderPresencePresetCheckboxes(root, prefix, catalog) {
    const mount = root.querySelector(`#${prefix}-presence-presets`);
    if (!mount || !catalog?.length) return;
    let html = '';
    for (const cat of _PRESENCE_CATEGORY_ORDER) {
        const items = catalog.filter((p) => p.category === cat);
        if (!items.length) continue;
        html += `<div class="dc-presence-preset-group" style="margin-bottom:10px">`;
        html += `<div style="font-weight:600;font-size:0.85em;margin-bottom:4px;color:var(--text-secondary,#99aab5)">${_esc(_PRESENCE_CATEGORY_LABELS[cat] || cat)}</div>`;
        html += `<div style="display:flex;flex-wrap:wrap;gap:8px 16px">`;
        for (const p of items) {
            html += `<label style="display:flex;align-items:center;gap:6px;font-size:0.92em;cursor:pointer">`;
            html += `<input type="checkbox" class="${prefix}-presence-preset" data-preset-id="${_esc(p.id)}">`;
            html += `<span>${_esc(p.label)}</span></label>`;
        }
        html += `</div></div>`;
    }
    mount.innerHTML = html;
}


function _populatePresencePresets(root, prefix, data) {
    const catalog = data.presence_activity_preset_catalog || _presencePresetCatalog;
    if (catalog?.length) {
        _presencePresetCatalog = catalog;
        _renderPresencePresetCheckboxes(root, prefix, catalog);
    }
    const enabled = new Set(data.presence_activity_presets || []);
    const fallback = new Set(data.presence_activity_presets_default || []);
    root.querySelectorAll(`.${prefix}-presence-preset`).forEach((el) => {
        const id = el.dataset.presetId;
        el.checked = enabled.size ? enabled.has(id) : fallback.has(id);
    });
    const customEl = root.querySelector(`#${prefix}-presence-custom`);
    if (customEl) customEl.value = _presenceCustomToText(data.presence_activities_custom);
}


function _presenceCustomToText(val) {
    if (!val || !Array.isArray(val) || !val.length) return '';
    return val.map((line) => {
        const s = String(line ?? '').trim();
        return s === '' ? '-' : s;
    }).join('\n');
}


function _readPresencePresets(root, prefix) {
    const ids = [];
    root.querySelectorAll(`.${prefix}-presence-preset:checked`).forEach((el) => {
        if (el.dataset.presetId) ids.push(el.dataset.presetId);
    });
    return ids;
}


function _readPresenceCustom(root, prefix) {
    const el = root.querySelector(`#${prefix}-presence-custom`);
    if (!el || !el.value.trim()) return [];
    return el.value.split('\n').map((line) => {
        const s = line.trim();
        if (s === '' || s === '-' || s === '(none)' || s === '(clear)') return '';
        return s;
    });
}


function _populatePersonalityFields(root, prefix, data, dmData) {
    const v  = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.value = val; };
    const c  = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.checked = !!val; };
    c(`${prefix}-quiet-enabled`, data.quiet_hours_enabled);
    v(`${prefix}-quiet-start`, _utcHourToLocal(data.quiet_hours_start ?? 22));
    v(`${prefix}-quiet-end`, _utcHourToLocal(data.quiet_hours_end ?? 8));
    v(`${prefix}-quiet-mode`, data.quiet_hours_mode ?? 'reactions_only');
    c(`${prefix}-activity-decay`, data.activity_decay_enabled);
    v(`${prefix}-activity-threshold`, data.activity_decay_threshold ?? 10);
    v(`${prefix}-activity-multiplier`, data.activity_decay_multiplier ?? 0.5);
    c(`${prefix}-presence-cycling`, data.presence_cycling_enabled !== false);
    v(`${prefix}-presence-interval`, data.presence_cycle_interval_minutes ?? 10);
    v(`${prefix}-presence-llm-chance`, data.presence_llm_status_chance ?? 0);
    _populatePresencePresets(root, prefix, data);
    _syncPresenceCyclingToggle(root, prefix);
    c(`${prefix}-sleep-enabled`, data.sleep_schedule_enabled);
    v(`${prefix}-sleep-hour`, _utcHourToLocal(data.sleep_utc_hour ?? 22));
    v(`${prefix}-sleep-buffer-max`, data.sleep_buffered_reply_max ?? 3);
    c(`${prefix}-sleep-same-minute`, data.sleep_same_goodnight_minute !== false);
    c(`${prefix}-sleep-forced-wake-enabled`, data.sleep_forced_wake_enabled);
    v(`${prefix}-sleep-forced-wake-count`, data.sleep_forced_wake_mention_count ?? 3);
    v(`${prefix}-sleep-forced-wake-window`, data.sleep_forced_wake_window_minutes ?? 15);
    v(`${prefix}-sleep-forced-wake-duration`, data.sleep_forced_wake_duration_minutes ?? 30);
    c(`${prefix}-sleep-use-greeting-targets`, data.sleep_use_greeting_targets !== false);
    c(`${prefix}-sleep-use-llm`, data.sleep_use_llm !== false);
    v(`${prefix}-sleep-message`, data.sleep_message ?? '');
    v(`${prefix}-sleep-fallback`, data.sleep_fallback ?? 'Good night, everyone! 🌙');
    v(`${prefix}-sleep-provider`, data.sleep_model_provider ?? '');
    v(`${prefix}-sleep-model`, data.sleep_model_name ?? '');
    v(`${prefix}-sleep-max-tokens`, data.sleep_max_tokens ?? 180);
    v(`${prefix}-dm-human-chance`, dmData?.human_response_chance ?? 25);
    v(`${prefix}-dm-reaction-chance`, dmData?.reaction_chance ?? 40);
    v(`${prefix}-dm-cooldown`, dmData?.cooldown_seconds ?? 60);
    c(`${prefix}-greeting-enabled`, data.greeting_enabled);
    c(`${prefix}-greeting-use-llm`, data.greeting_use_llm !== false);
    v(`${prefix}-greeting-hour`, _utcHourToLocal(data.greeting_utc_hour ?? 9));
    v(`${prefix}-greeting-message`, data.greeting_message ?? '');
    v(`${prefix}-greeting-fallback`, data.greeting_fallback ?? 'Good morning, everyone! ☀️');
    v(`${prefix}-greeting-provider`, data.greeting_model_provider ?? '');
    v(`${prefix}-greeting-model`, data.greeting_model_name ?? '');
    v(`${prefix}-greeting-max-tokens`, data.greeting_max_tokens ?? 180);
    _populateGreetingTargets(root, prefix, data.greeting_targets || []);
    c(`${prefix}-outreach-enabled`, data.outreach_enabled);
    v(`${prefix}-outreach-quiet-minutes`, data.outreach_quiet_minutes ?? 240);
    v(`${prefix}-outreach-cooldown-hours`, data.outreach_cooldown_hours ?? 8);
    v(`${prefix}-outreach-skip-chance`, data.outreach_skip_chance ?? 25);
    v(`${prefix}-outreach-active-start`, _utcHourToLocal(data.outreach_active_start ?? 10));
    v(`${prefix}-outreach-active-end`, _utcHourToLocal(data.outreach_active_end ?? 21));
    c(`${prefix}-outreach-use-llm`, data.outreach_use_llm !== false);
    c(`${prefix}-outreach-typing`, data.outreach_typing_indicator !== false);
    v(`${prefix}-outreach-message`, data.outreach_message ?? '');
    v(`${prefix}-outreach-fallback`, data.outreach_fallback ?? 'Anyone around? 👀');
    v(`${prefix}-outreach-provider`, data.outreach_model_provider ?? '');
    v(`${prefix}-outreach-model`, data.outreach_model_name ?? '');
    v(`${prefix}-outreach-max-tokens`, data.outreach_max_tokens ?? 180);
    _populateOutreachTargets(root, prefix, data.outreach_targets || []);
    c(`${prefix}-safety-perms`, data.safety_check_permissions !== false);
    v(`${prefix}-rate-limit-secs`, data.rate_limit_seconds ?? 2);
    v(`${prefix}-rate-limit-burst`, data.rate_limit_burst ?? 8);
    v(`${prefix}-rate-limit-window`, data.rate_limit_window ?? 60);
    v(`${prefix}-content-blocklist`, _listToStr(data.content_blocklist));
}


function _readPersonalityFields(root, prefix) {
    const v = (id) => root.querySelector(`#${id}`)?.value ?? '';
    const b = (id) => root.querySelector(`#${id}`)?.checked ?? false;
    const i = (id) => parseInt(v(id) || '0', 10);
    _syncGreetingTargets(root, prefix);
    _syncOutreachTargets(root, prefix);
    const targets = [..._getGreetingSet(prefix)];
    const outreachTargets = [..._getOutreachSet(prefix)];
    return {
        quiet_hours_enabled: b(`${prefix}-quiet-enabled`),
        quiet_hours_start: _localHourToUtc(i(`${prefix}-quiet-start`)),
        quiet_hours_end: _localHourToUtc(i(`${prefix}-quiet-end`)),
        quiet_hours_mode: v(`${prefix}-quiet-mode`) || 'reactions_only',
        activity_decay_enabled: b(`${prefix}-activity-decay`),
        activity_decay_threshold: i(`${prefix}-activity-threshold`),
        activity_decay_multiplier: parseFloat(v(`${prefix}-activity-multiplier`) || '0.5'),
        presence_cycling_enabled: b(`${prefix}-presence-cycling`),
        presence_cycle_interval_minutes: i(`${prefix}-presence-interval`),
        presence_llm_status_chance: i(`${prefix}-presence-llm-chance`),
        presence_activity_presets: _readPresencePresets(root, prefix),
        presence_activities_custom: _readPresenceCustom(root, prefix),
        sleep_schedule_enabled: b(`${prefix}-sleep-enabled`),
        sleep_utc_hour: _localHourToUtc(i(`${prefix}-sleep-hour`)),
        sleep_buffered_reply_max: i(`${prefix}-sleep-buffer-max`),
        sleep_same_goodnight_minute: b(`${prefix}-sleep-same-minute`),
        sleep_forced_wake_enabled: b(`${prefix}-sleep-forced-wake-enabled`),
        sleep_forced_wake_mention_count: i(`${prefix}-sleep-forced-wake-count`),
        sleep_forced_wake_window_minutes: i(`${prefix}-sleep-forced-wake-window`),
        sleep_forced_wake_duration_minutes: i(`${prefix}-sleep-forced-wake-duration`),
        sleep_use_greeting_targets: b(`${prefix}-sleep-use-greeting-targets`),
        sleep_use_llm: b(`${prefix}-sleep-use-llm`),
        sleep_message: v(`${prefix}-sleep-message`),
        sleep_fallback: v(`${prefix}-sleep-fallback`),
        sleep_model_provider: v(`${prefix}-sleep-provider`),
        sleep_model_name: v(`${prefix}-sleep-model`),
        sleep_max_tokens: i(`${prefix}-sleep-max-tokens`),
        greeting_enabled: b(`${prefix}-greeting-enabled`),
        greeting_use_llm: b(`${prefix}-greeting-use-llm`),
        greeting_utc_hour: _localHourToUtc(i(`${prefix}-greeting-hour`)),
        greeting_message: v(`${prefix}-greeting-message`),
        greeting_fallback: v(`${prefix}-greeting-fallback`),
        greeting_model_provider: v(`${prefix}-greeting-provider`),
        greeting_model_name: v(`${prefix}-greeting-model`),
        greeting_max_tokens: i(`${prefix}-greeting-max-tokens`),
        greeting_targets: targets,
        outreach_enabled: b(`${prefix}-outreach-enabled`),
        outreach_quiet_minutes: i(`${prefix}-outreach-quiet-minutes`),
        outreach_cooldown_hours: i(`${prefix}-outreach-cooldown-hours`),
        outreach_skip_chance: i(`${prefix}-outreach-skip-chance`),
        outreach_active_start: _localHourToUtc(i(`${prefix}-outreach-active-start`)),
        outreach_active_end: _localHourToUtc(i(`${prefix}-outreach-active-end`)),
        outreach_use_llm: b(`${prefix}-outreach-use-llm`),
        outreach_typing_indicator: b(`${prefix}-outreach-typing`),
        outreach_message: v(`${prefix}-outreach-message`),
        outreach_fallback: v(`${prefix}-outreach-fallback`),
        outreach_model_provider: v(`${prefix}-outreach-provider`),
        outreach_model_name: v(`${prefix}-outreach-model`),
        outreach_max_tokens: i(`${prefix}-outreach-max-tokens`),
        outreach_targets: outreachTargets,
        safety_check_permissions: b(`${prefix}-safety-perms`),
        rate_limit_seconds: i(`${prefix}-rate-limit-secs`),
        rate_limit_burst: i(`${prefix}-rate-limit-burst`),
        rate_limit_window: i(`${prefix}-rate-limit-window`),
        content_blocklist: v(`${prefix}-content-blocklist`),
        dm: {
            human_response_chance: i(`${prefix}-dm-human-chance`),
            reaction_chance: i(`${prefix}-dm-reaction-chance`),
            cooldown_seconds: i(`${prefix}-dm-cooldown`),
        },
    };
}


function _populateFields(root, prefix, data) {
    const v  = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.value = val; };
    const c  = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.checked = !!val; };
    const lb = (id, val) => { const e = root.querySelector(`#${id}`); if (e) e.textContent = `${val}%`; };
    const r  = (name, val) => root.querySelectorAll(`input[name="${name}"]`).forEach(el => { el.checked = el.value === val; });

    v(`${prefix}-bot-chance`,       data.bot_response_chance   ?? 15);
    lb(`${prefix}-bot-chance-lbl`,  data.bot_response_chance   ?? 15);
    v(`${prefix}-human-chance`,     data.human_response_chance ?? 15);
    lb(`${prefix}-human-chance-lbl`,data.human_response_chance ?? 15);
    v(`${prefix}-personality-preset`, data.personality_preset ?? 'custom');
    v(`${prefix}-reply-mode`,       data.reply_mode ?? 'default');
    v(`${prefix}-keyword-triggers`, _listToStr(data.keyword_triggers));
    v(`${prefix}-role-ids`,         _listToStr(data.always_respond_role_ids));
    v(`${prefix}-user-denylist`,    _listToStr(data.user_denylist));
    v(`${prefix}-user-allowlist`,   _listToStr(data.user_allowlist));
    c(`${prefix}-ignore-bots`,     data.ignore_bots);
    v(`${prefix}-bot-allowlist`,   _listToStr(data.bot_allowlist));
    v(`${prefix}-cooldown`,         data.cooldown_seconds      ?? 120);
    r(`${prefix}-scope`,            data.cooldown_scope        ?? 'per_channel');
    c(`${prefix}-name-match`,       data.name_match_enabled    ?? true);
    c(`${prefix}-name-case`,        data.name_match_case_sensitive ?? false);

    // Reactions
    const reactEnabled = data.reactions_enabled ?? false;
    c(`${prefix}-reactions-enabled`, reactEnabled);
    const opts = root.querySelector(`#${prefix}-reaction-options`);
    if (opts) opts.style.display = reactEnabled ? 'block' : 'none';

    v(`${prefix}-reaction-chance`,      data.reaction_chance  ?? 50);
    lb(`${prefix}-reaction-chance-lbl`, data.reaction_chance  ?? 50);
    v(`${prefix}-reaction-cooldown`,    data.reaction_cooldown_seconds ?? 30);
    c(`${prefix}-react-trigger`,        data.react_to_trigger ?? true);
    c(`${prefix}-react-any`,            data.react_to_any     ?? false);
    r(`${prefix}-reaction-backend`,     data.reaction_backend ?? 'vader');

    // Emoji grid — only custom Discord emoji are shown (all standard Unicode are always allowed).
    // allowed_emojis only tracks custom Discord emoji (strings starting with '<').
    const customEmojis = new Set(
        (data.allowed_emojis || []).filter(e => typeof e === 'string' && e.startsWith('<'))
    );
    const grid = root.querySelector(`#${prefix}-emoji-grid`);
    if (grid) {
        grid.querySelectorAll('.dc-emoji-btn').forEach(btn => {
            const emoji = btn.dataset.emoji;
            const isActive = customEmojis.has(emoji);
            btn.classList.toggle('active', isActive);
            btn.style.borderColor = isActive ? 'var(--accent,#7289da)' : 'var(--border)';
            btn.style.opacity     = isActive ? '1' : '0.35';
        });
        // Add any custom emojis from settings that aren't in the grid yet
        customEmojis.forEach(emoji => {
            if (grid.querySelector(`[data-emoji="${CSS.escape(emoji)}"]`)) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'dc-emoji-btn active';
            btn.dataset.emoji = emoji;
            btn.textContent = emoji;
            btn.title = emoji;
            btn.style.cssText = (
                'font-size:1.35em;padding:4px 6px;border:2px solid var(--accent,#7289da);'
                + 'border-radius:6px;background:var(--bg-secondary);cursor:pointer;'
                + 'transition:opacity 0.15s,border-color 0.15s'
            );
            btn.addEventListener('click', () => _toggleEmoji(btn));
            grid.appendChild(btn);
        });
    }

    // Image settings
    const imageEnabled = data.image_enabled ?? false;
    c(`${prefix}-image-enabled`, imageEnabled);
    const imgOpts = root.querySelector(`#${prefix}-image-options`);
    if (imgOpts) imgOpts.style.display = imageEnabled ? 'block' : 'none';
    const imgWarn = root.querySelector(`#${prefix}-image-warning`);
    if (imgWarn) imgWarn.style.display = imageEnabled ? 'none' : 'block';
    v(`${prefix}-image-provider`, data.image_model_provider ?? '');
    v(`${prefix}-image-model`,    data.image_model_name    ?? '');
    v(`${prefix}-image-max-tokens`, data.image_model_max_tokens ?? 500);

    const gifEnabled = data.gif_replies_enabled ?? false;
    c(`${prefix}-gif-enabled`, gifEnabled);
    const gifOpts = root.querySelector(`#${prefix}-gif-options`);
    if (gifOpts) gifOpts.style.display = gifEnabled ? 'block' : 'none';
    v(`${prefix}-gif-api-key`, data.gif_api_key ?? data.tenor_api_key ?? '');
    v(`${prefix}-gif-search-provider`, data.gif_provider ?? 'klipy');
    v(`${prefix}-gif-chance`, data.gif_reply_chance ?? 15);
    v(`${prefix}-gif-cooldown`, data.gif_reply_cooldown_seconds ?? 120);
    v(`${prefix}-gif-content-filter`, data.gif_content_filter ?? data.tenor_content_filter ?? 'medium');
    const gifUseLlm = data.gif_use_llm !== false;
    c(`${prefix}-gif-use-llm`, gifUseLlm);
    const gifLlmOpts = root.querySelector(`#${prefix}-gif-llm-options`);
    if (gifLlmOpts) gifLlmOpts.style.display = gifUseLlm ? 'block' : 'none';
    v(`${prefix}-gif-query-provider`, data.gif_model_provider ?? '');
    v(`${prefix}-gif-model`, data.gif_model_name ?? '');
    v(`${prefix}-gif-max-tokens`, data.gif_model_max_tokens ?? 80);

    // Append to user message
    const appendEnabled = data.append_to_user_message_enabled ?? false;
    c(`${prefix}-append-enabled`, appendEnabled);
    const appendOpts = root.querySelector(`#${prefix}-append-options`);
    if (appendOpts) appendOpts.style.display = appendEnabled ? 'block' : 'none';
    v(`${prefix}-append-text`, data.append_to_user_message ?? '');

    c(`${prefix}-memory-enabled`, data.memory_enabled !== false);
    c(`${prefix}-message-edits-enabled`, data.message_edits_enabled !== false);
    const autoTypoEnabled = data.auto_typo_enabled ?? false;
    c(`${prefix}-auto-typo-enabled`, autoTypoEnabled);
    const autoTypoDelayOpts = root.querySelector(`#${prefix}-auto-typo-delay-options`);
    if (autoTypoDelayOpts) autoTypoDelayOpts.style.display = autoTypoEnabled ? 'block' : 'none';
    v(`${prefix}-auto-typo-chance`, data.auto_typo_chance ?? 12);
    lb(`${prefix}-auto-typo-chance-lbl`, data.auto_typo_chance ?? 12);
    v(`${prefix}-auto-typo-delay-min`, data.auto_typo_delay_min ?? 2);
    v(`${prefix}-auto-typo-delay-max`, data.auto_typo_delay_max ?? 6);
    v(`${prefix}-history-inject-limit`, data.history_inject_limit ?? 25);
    v(`${prefix}-history-line-max-chars`, data.history_line_max_chars ?? 280);
    v(`${prefix}-memory-max-tokens`, data.memory_max_tokens ?? 300);
    v(`${prefix}-memory-threshold`, data.memory_search_threshold ?? 0.35);

    const profilingEnabled = data.profiling_enabled ?? false;
    c(`${prefix}-profiling-enabled`, profilingEnabled);
    const profilingOpts = root.querySelector(`#${prefix}-profiling-options`);
    if (profilingOpts) profilingOpts.style.display = profilingEnabled ? 'block' : 'none';
    c(`${prefix}-profiling-dm-only`, data.profiling_dm_only ?? false);
    c(`${prefix}-profiling-modulate`, data.profiling_modulate_reply_chance !== false);
    c(`${prefix}-profiling-use-llm`, data.profiling_use_llm !== false);
    c(`${prefix}-profiling-imperfect`, data.profiling_imperfect_recall ?? false);
    v(`${prefix}-profiling-min-messages`, data.profiling_min_messages ?? 5);
    v(`${prefix}-profiling-max-tokens`, data.profiling_max_tokens ?? 300);
    v(`${prefix}-profiling-fact-min`, data.profiling_fact_confidence_min ?? 0.6);
    v(`${prefix}-profiling-imperfect-chance`, data.profiling_imperfect_recall_chance ?? 0.05);
    v(`${prefix}-profiling-provider`, data.profiling_model_provider ?? '');
    v(`${prefix}-profiling-model`, data.profiling_model_name ?? '');
    v(`${prefix}-profiling-distill-interval`, data.profiling_distill_interval_minutes ?? 3);
    v(`${prefix}-profiling-distill-max`, data.profiling_distill_max_tokens ?? 400);
}


function _readFields(root, prefix) {
    const i = (id)   => parseInt(root.querySelector(`#${id}`)?.value  ?? '0', 10);
    const b = (id)   => root.querySelector(`#${id}`)?.checked ?? false;
    const v = (id)   => root.querySelector(`#${id}`)?.value ?? '';
    const r = (name) => root.querySelector(`input[name="${name}"]:checked`)?.value ?? 'per_channel';
    const emojis = [...root.querySelectorAll(`#${prefix}-emoji-grid .dc-emoji-btn.active`)]
                       .map(btn => btn.dataset.emoji)
                       .filter(e => e.startsWith('<'));  // only custom Discord emoji
    return {
        personality_preset:        v(`${prefix}-personality-preset`) || 'custom',
        reply_mode:                v(`${prefix}-reply-mode`) || 'default',
        bot_response_chance:       i(`${prefix}-bot-chance`),
        human_response_chance:     i(`${prefix}-human-chance`),
        cooldown_seconds:          i(`${prefix}-cooldown`),
        cooldown_scope:            r(`${prefix}-scope`),
        name_match_enabled:        b(`${prefix}-name-match`),
        name_match_case_sensitive: b(`${prefix}-name-case`),
        reactions_enabled:         b(`${prefix}-reactions-enabled`),
        reaction_chance:           i(`${prefix}-reaction-chance`),
        reaction_cooldown_seconds: i(`${prefix}-reaction-cooldown`),
        react_to_trigger:          b(`${prefix}-react-trigger`),
        react_to_any:              b(`${prefix}-react-any`),
        allowed_emojis:            emojis,
        reaction_backend:          r(`${prefix}-reaction-backend`),
        keyword_triggers:          v(`${prefix}-keyword-triggers`),
        always_respond_role_ids:   v(`${prefix}-role-ids`),
        user_denylist:             v(`${prefix}-user-denylist`),
        user_allowlist:            v(`${prefix}-user-allowlist`),
        ignore_bots:               b(`${prefix}-ignore-bots`),
        bot_allowlist:             v(`${prefix}-bot-allowlist`),
        image_enabled:             b(`${prefix}-image-enabled`),
        image_model_provider:      v(`${prefix}-image-provider`),
        image_model_name:          v(`${prefix}-image-model`),
        image_model_max_tokens:    i(`${prefix}-image-max-tokens`),
        gif_replies_enabled:       b(`${prefix}-gif-enabled`),
        gif_api_key:               v(`${prefix}-gif-api-key`),
        gif_provider:              v(`${prefix}-gif-search-provider`) || 'klipy',
        gif_reply_chance:          i(`${prefix}-gif-chance`),
        gif_reply_cooldown_seconds: i(`${prefix}-gif-cooldown`),
        gif_content_filter:        v(`${prefix}-gif-content-filter`) || 'medium',
        gif_use_llm:               b(`${prefix}-gif-use-llm`),
        gif_model_provider:        v(`${prefix}-gif-query-provider`),
        gif_model_name:            v(`${prefix}-gif-model`),
        gif_model_max_tokens:      i(`${prefix}-gif-max-tokens`),
        append_to_user_message_enabled: b(`${prefix}-append-enabled`),
        append_to_user_message:    v(`${prefix}-append-text`),
        memory_enabled:            b(`${prefix}-memory-enabled`),
        message_edits_enabled:     b(`${prefix}-message-edits-enabled`),
        auto_typo_enabled:         b(`${prefix}-auto-typo-enabled`),
        auto_typo_chance:          i(`${prefix}-auto-typo-chance`),
        auto_typo_delay_min:       parseFloat(v(`${prefix}-auto-typo-delay-min`) || '2'),
        auto_typo_delay_max:       parseFloat(v(`${prefix}-auto-typo-delay-max`) || '6'),
        history_inject_limit:      i(`${prefix}-history-inject-limit`),
        history_line_max_chars:    i(`${prefix}-history-line-max-chars`),
        memory_max_tokens:         i(`${prefix}-memory-max-tokens`),
        memory_search_threshold:   parseFloat(v(`${prefix}-memory-threshold`) || '0.35'),
        profiling_enabled:         b(`${prefix}-profiling-enabled`),
        profiling_dm_only:         b(`${prefix}-profiling-dm-only`),
        profiling_modulate_reply_chance: b(`${prefix}-profiling-modulate`),
        profiling_use_llm:         b(`${prefix}-profiling-use-llm`),
        profiling_imperfect_recall: b(`${prefix}-profiling-imperfect`),
        profiling_min_messages:    i(`${prefix}-profiling-min-messages`),
        profiling_max_tokens:      i(`${prefix}-profiling-max-tokens`),
        profiling_fact_confidence_min: parseFloat(v(`${prefix}-profiling-fact-min`) || '0.6'),
        profiling_imperfect_recall_chance: parseFloat(v(`${prefix}-profiling-imperfect-chance`) || '0.05'),
        profiling_model_provider:  v(`${prefix}-profiling-provider`),
        profiling_model_name:      v(`${prefix}-profiling-model`),
        profiling_distill_interval_minutes: i(`${prefix}-profiling-distill-interval`),
        profiling_distill_max_tokens: i(`${prefix}-profiling-distill-max`),
    };
}


function _readReplyContextFields(container) {
    const histEl = container.querySelector('#dc-llm-max-history');
    const ctxEl = container.querySelector('#dc-reply-context-limit');
    return {
        llm_max_history: histEl ? parseInt(histEl.value, 10) : 0,
        reply_context_limit: ctxEl ? parseInt(ctxEl.value, 10) : 0,
    };
}


function _populateReplyContextFields(container, data) {
    const histEl = container.querySelector('#dc-llm-max-history');
    const ctxEl = container.querySelector('#dc-reply-context-limit');
    const noteEl = container.querySelector('#dc-reply-context-note');
    if (histEl) histEl.value = data.llm_max_history ?? 0;
    if (ctxEl) ctxEl.value = data.reply_context_limit ?? 0;
    if (noteEl) {
        if (data.reply_task_linked && data.reply_task_name) {
            noteEl.textContent = `Linked Schedule task: ${data.reply_task_name}`;
            noteEl.className = 'dc-empty';
        } else {
            noteEl.textContent = 'No Discord auto-reply Schedule task found — context limit is stored but not applied until one exists.';
            noteEl.className = 'dc-empty dc-status-err';
        }
    }
}


// ── Global Settings ────────────────────────────────────────────────────────────

async function _loadGlobalSettings(container) {
    try {
        const res = await fetch('/api/plugin/leona_discord/settings');
        if (!res.ok) return;
        const data = await res.json();
        if (data.presence_activity_preset_catalog) {
            _presencePresetCatalog = data.presence_activity_preset_catalog;
        }
        const batchEl = container.querySelector('#dc-batch-delay');
        if (batchEl) batchEl.value = data.batch_delay ?? 8;
        const alwaysEl = container.querySelector('#dc-always-online');
        if (alwaysEl) alwaysEl.checked = data.always_online !== false;
        const traceEl = container.querySelector('#dc-debug-trace');
        if (traceEl) traceEl.checked = data.debug_trace_enabled !== false;
        const llmDbgEl = container.querySelector('#dc-llm-debug-enabled');
        if (llmDbgEl) llmDbgEl.checked = data.llm_debug_messaging_enabled !== false;
        const slashEl = container.querySelector('#dc-slash-enabled');
        if (slashEl) slashEl.checked = data.slash_commands_enabled !== false;
        _populateReplyContextFields(container, data);
        // Store the full API emoji list for use as the grid source
        if (data.default_emojis) _API_EMOJIS = data.default_emojis;
        // Re-render the emoji grid now that _API_EMOJIS is populated (only custom emoji shown)
        const reactionsMount = container.querySelector('#dc-reactions-fields-mount');
        if (reactionsMount && _API_EMOJIS && _API_EMOJIS.length > 0) {
            reactionsMount.innerHTML = _reactionsFieldsHTML('dc-g');
            _wireReactionToggle(container, 'dc-g');
            _wireAutoTypoToggle(container, 'dc-g');
            _wireSliders(container, 'dc-g');
        }
        _populateFields(container, 'dc-g', { ...data.global, ...data });
        _populatePersonalityFields(container, 'dc-g', { ...data.global, ...data }, data.dm ?? {});
        _refreshLocalScheduleHourHints(container, 'dc-g');
        _loadGreetingPicker(container, 'dc-g');
        _loadOutreachPicker(container, 'dc-g');
    } catch (_) {}
}


async function _saveGlobalSettings(container) {
    const btn    = container.querySelector('#dc-save-global');
    const status = container.querySelector('#dc-global-status');

    const batch_delay = parseFloat(container.querySelector('#dc-batch-delay')?.value);
    if (isNaN(batch_delay) || batch_delay < 1 || batch_delay > 300) {
        if (status) { status.textContent = 'Batch delay must be 1–300 s.'; status.className = 'dc-status dc-status-err'; }
        return;
    }
    const histVal = parseInt(container.querySelector('#dc-llm-max-history')?.value ?? '0', 10);
    if (isNaN(histVal) || histVal < 0 || histVal > 500) {
        if (status) { status.textContent = 'LLM max history must be 0–500.'; status.className = 'dc-status dc-status-err'; }
        return;
    }
    const ctxVal = parseInt(container.querySelector('#dc-reply-context-limit')?.value ?? '0', 10);
    if (isNaN(ctxVal) || ctxVal < 0 || ctxVal > 200000) {
        if (status) { status.textContent = 'Reply context limit must be 0–200000.'; status.className = 'dc-status dc-status-err'; }
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
        const res = await fetch('/api/plugin/leona_discord/settings/global', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
            body: JSON.stringify({
                batch_delay,
                always_online: container.querySelector('#dc-always-online')?.checked !== false,
                debug_trace_enabled: container.querySelector('#dc-debug-trace')?.checked !== false,
                llm_debug_messaging_enabled: container.querySelector('#dc-llm-debug-enabled')?.checked !== false,
                slash_commands_enabled: container.querySelector('#dc-slash-enabled')?.checked !== false,
                apply_preset_values: false,
                ..._readReplyContextFields(container),
                ..._readFields(container, 'dc-g'),
                ..._readPersonalityFields(container, 'dc-g'),
            }),
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        _populateReplyContextFields(container, data);
        if (data.global) {
            _populatePersonalityFields(container, 'dc-g', data.global, data.dm || {});
            _syncPresenceCyclingToggle(container, 'dc-g');
        }
        if (status) {
            const warn = (data.warnings || []).join(' ');
            status.textContent = warn ? `✓ Saved — ${warn}` : '✓ Saved';
            status.className = warn ? 'dc-status dc-status-err' : 'dc-status dc-status-ok';
        }
        setTimeout(() => { if (status) { status.textContent = ''; status.className = 'dc-status'; } }, 3000);
    } catch (e) {
        if (status) { status.textContent = e.message; status.className = 'dc-status dc-status-err'; }
    }
    btn.disabled = false;
    btn.textContent = 'Save Global Settings';
}


// ── Unified save (called by host's top-level "Save Changes" button) ──────────
//
// Background: the host Settings shell renders its own prominent "Save Changes"
// button at the top of every settings tab. For plugin tabs it calls
//   reg.getSettings(box) → reg.save(s)
// Previously the Leona plugin had both as no-op stubs, so clicking the host's
// button silently did nothing — the user thought "save doesn't work" because
// the only working button was a small "Save Global Settings" inside the
// plugin's own card, easy to miss.
//
// _saveAllSettings saves:
//   1. Global settings (if the global form is present)
//   2. Any per-server subform the user currently has open (one POST per guild)
// Returns {success, saved: ['global', guildId1, ...]} so the host can render
// accurate feedback.
async function _saveAllSettings(container) {
    const saved = [];
    const errors = [];

    // ── 1. Global settings (only if the global form is rendered) ────────────
    if (container.querySelector('#dc-batch-delay')) {
        try {
            const batch_delay = parseFloat(container.querySelector('#dc-batch-delay')?.value);
            if (isNaN(batch_delay) || batch_delay < 1 || batch_delay > 300) {
                throw new Error('Batch delay must be 1–300 s');
            }
            const histVal = parseInt(container.querySelector('#dc-llm-max-history')?.value ?? '0', 10);
            if (isNaN(histVal) || histVal < 0 || histVal > 500) {
                throw new Error('LLM max history must be 0–500');
            }
            const ctxVal = parseInt(container.querySelector('#dc-reply-context-limit')?.value ?? '0', 10);
            if (isNaN(ctxVal) || ctxVal < 0 || ctxVal > 200000) {
                throw new Error('Reply context limit must be 0–200000');
            }
            const res = await fetch('/api/plugin/leona_discord/settings/global', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                body: JSON.stringify({
                batch_delay,
                always_online: container.querySelector('#dc-always-online')?.checked !== false,
                debug_trace_enabled: container.querySelector('#dc-debug-trace')?.checked !== false,
                llm_debug_messaging_enabled: container.querySelector('#dc-llm-debug-enabled')?.checked !== false,
                slash_commands_enabled: container.querySelector('#dc-slash-enabled')?.checked !== false,
                apply_preset_values: false,
                ..._readReplyContextFields(container),
                ..._readFields(container, 'dc-g'),
                ..._readPersonalityFields(container, 'dc-g'),
            }),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            _populateReplyContextFields(container, data);
            if ((data.warnings || []).length) {
                errors.push(...data.warnings);
            }
            _populatePersonalityFields(container, 'dc-g', data.global || {}, data.dm || {});
            saved.push('global');
        } catch (e) {
            errors.push(`global: ${e.message}`);
        }
    }

    // ── 2. Any open per-server subform ──────────────────────────────────────
    // Subforms have prefix `dc-sv-{guildId}` and a save button with id
    // `${prefix}-save`. If the button is currently in "Saving…" state the
    // user is mid-save, so we skip it (the in-progress click handler owns it).
    const openSubforms = container.querySelectorAll('[id^="dc-sform-"]');
    for (const formEl of openSubforms) {
        const guildId = formEl.id.replace(/^dc-sform-/, '');
        const saveBtn = formEl.querySelector(`#dc-sv-${guildId}-save`);
        if (!saveBtn) continue;
        if (saveBtn.disabled) continue;  // mid-save
        const prefix = `dc-sv-${guildId}`;
        try {
            const res = await fetch(`/api/plugin/leona_discord/settings/servers/${guildId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                body: JSON.stringify(_perServerFields(formEl, prefix)),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            saved.push(guildId);
        } catch (e) {
            errors.push(`server ${guildId}: ${e.message}`);
        }
    }

    // ── 3. Reload anything that changed so the UI reflects the saved state ──
    if (saved.includes('global')) {
        _loadGlobalSettings(container);
    }
    if (saved.some(g => g !== 'global' && /^\d+$/.test(g))) {
        _loadServers(container);
    }

    if (errors.length) {
        return { success: false, error: errors.join('; '), saved };
    }
    return { success: true, saved };
}


// Lightweight wrapper used by reg.getSettings — the host only needs SOMETHING
// to pass through to reg.save (which now ignores the payload and reads the
// DOM itself via _activeContainer), but returning the global fields keeps the
// shape consistent and is useful for the host's own debugging.
function _readFieldsGlobal(container) {
    if (!container) return null;
    if (!container.querySelector('#dc-batch-delay')) return null;
    const batch_delay = parseFloat(container.querySelector('#dc-batch-delay')?.value);
    return {
        batch_delay: isNaN(batch_delay) ? 8 : batch_delay,
        always_online: container.querySelector('#dc-always-online')?.checked !== false,
        debug_trace_enabled: container.querySelector('#dc-debug-trace')?.checked !== false,
        llm_debug_messaging_enabled: container.querySelector('#dc-llm-debug-enabled')?.checked !== false,
        slash_commands_enabled: container.querySelector('#dc-slash-enabled')?.checked !== false,
        ..._readReplyContextFields(container),
        ..._readFields(container, 'dc-g'),
        ..._readPersonalityFields(container, 'dc-g'),
    };
}


async function _loadTraces(container) {
    const panel = container.querySelector('#dc-trace-list');
    const status = container.querySelector('#dc-memory-status');
    if (!panel) return;
    try {
        const [tRes, mRes] = await Promise.all([
            fetch('/api/plugin/leona_discord/traces?limit=30'),
            fetch('/api/plugin/leona_discord/memory/stats'),
        ]);
        const traces = tRes.ok ? (await tRes.json()).traces || [] : [];
        const mem = mRes.ok ? await mRes.json() : {};
        if (status) {
            const prof = mem.profiling || {};
            const profPart = prof.enabled
                ? ` · ${prof.profile_count ?? 0} profiles`
                : '';
            status.textContent = `${mem.message_count ?? 0} messages stored · ${mem.backend || 'sqlite'}${profPart}`;
            status.className = 'dc-status dc-status-ok';
        }
        if (!traces.length) {
            panel.innerHTML = '<p class="dc-empty">No traces yet — send some messages with debug traces enabled.</p>';
            return;
        }
        panel.innerHTML = traces.map(t => {
            const gates = (t.gates || []).map(g =>
                `<span style="margin-right:6px;color:${g.passed ? 'var(--success,#43b581)' : 'var(--danger,#f04747)'}">${g.gate}${g.detail ? ` (${g.detail})` : ''}</span>`
            ).join('');
            const when = new Date((t.ts || 0) * 1000).toLocaleString();
            return `<div class="dc-row" style="flex-direction:column;align-items:flex-start;gap:4px">
                <div><strong>${_esc(t.outcome || '?')}</strong> · #${_esc(t.channel_name || t.channel_id || '?')} · ${_esc(t.username || '?')} · ${when}</div>
                <div class="dc-row-help" style="margin:0">${gates || '—'}</div>
            </div>`;
        }).join('');
    } catch (e) {
        panel.innerHTML = `<p class="dc-empty">Failed to load traces: ${_esc(e.message)}</p>`;
    }
}


let _llmDebugModalEl = null;
let _llmDebugLogsCache = [];
let _llmDebugSelectedId = null;


function _closeLlmDebugModal() {
    if (_llmDebugModalEl) {
        _llmDebugModalEl.remove();
        _llmDebugModalEl = null;
    }
    _llmDebugSelectedId = null;
}


function _llmDebugSection(title, text) {
    const body = (text || '').trim();
    if (!body) return '';
    return `<div class="dc-debug-section"><h4>${_esc(title)}</h4><pre class="dc-debug-pre">${_esc(body)}</pre></div>`;
}


function _llmDebugPostSendEditKindLabel(kind) {
    const labels = {
        auto_typo: 'Auto typo',
        llm_edit: 'LLM [edit:]',
        random_typo: 'Random typo',
        random_thought: 'Random thought',
    };
    return labels[kind] || kind || 'Post-send edit';
}


function _llmDebugPostSendEditSection(edit) {
    if (!edit || !edit.kind) return '';
    const label = _llmDebugPostSendEditKindLabel(edit.kind);
    const plannedAt = edit.planned_at
        ? new Date(edit.planned_at * 1000).toLocaleString()
        : 'unknown';
    const appliedAt = edit.applied_at
        ? new Date(edit.applied_at * 1000).toLocaleString()
        : '';
    const delay = typeof edit.delay_secs === 'number' ? `${edit.delay_secs}s` : '?';
    let status = 'pending correction';
    if (edit.applied) status = 'corrected';
    else if (edit.error) status = `failed: ${edit.error}`;
    const meta = [
        label,
        `sent ${plannedAt}`,
        `delay ${delay}`,
        appliedAt ? `corrected ${appliedAt}` : status,
        edit.discord_message_id ? `msg ${edit.discord_message_id}` : '',
    ].filter(Boolean).join(' · ');
    const body = [
        `Status: ${status}`,
        '',
        'Sent to Discord (typo / draft):',
        edit.sent_text || '',
        '',
        'Corrected to:',
        edit.corrected_text || '',
    ].join('\n');
    return `<div class="dc-debug-section"><h4>Post-send edit · ${_esc(label)}</h4>`
        + `<div class="dc-row-help" style="margin:0 0 6px">${_esc(meta)}</div>`
        + `<pre class="dc-debug-pre">${_esc(body)}</pre></div>`;
}


function _renderLlmDebugDetail(log) {
    if (!log) return '<p class="dc-empty">Select an exchange to inspect.</p>';
    const when = log.ts ? new Date(log.ts * 1000).toLocaleString() : 'unknown';
    const flags = log.flags || {};
    const flagBits = [
        flags.memory_context ? 'memory' : '',
        flags.profile_context ? 'profile' : '',
        flags.is_dm ? 'dm' : '',
        flags.slash_command ? `/${flags.slash_command}` : '',
        `batch×${flags.batch_size ?? 1}`,
        `hist ${flags.history_size ?? 0}`,
        flags.post_send_edit?.kind ? _llmDebugPostSendEditKindLabel(flags.post_send_edit.kind).toLowerCase() : '',
    ].filter(Boolean).join(' · ');
    const historyText = (log.recent_history || []).map(line => `  ${line}`).join('\n');
    const meta = [
        `#${log.channel_name || log.channel_id || '?'}`,
        log.guild_name ? `(${log.guild_name})` : '',
        `@${log.username || 'unknown'}`,
        when,
        log.source || 'batch',
        log.task_name ? `task: ${log.task_name}` : '',
    ].filter(Boolean).join(' · ');
    const hasResponse = !!(log.response_raw || log.response_clean);
    const deliveryNote = log.delivery_path === 'tool'
        ? '<div class="dc-debug-warn" style="margin:8px 0;padding:8px;border-left:3px solid var(--warning,#e6a700)">'
          + 'Discord received text from <code>discord_send_message</code> (tool), not the auto-reply path. '
          + 'The raw LLM response below may differ from what users saw in chat.'
          + '</div>'
        : '';
    const sentViaTool = log.delivery_path === 'tool' && log.discord_sent_text
        ? _llmDebugSection('Actually sent to Discord (via tool)', log.discord_sent_text)
        : '';
    return `
        <div class="dc-debug-meta" style="margin-bottom:12px">${_esc(meta)}<br>${_esc(flagBits)}</div>
        ${deliveryNote}
        ${_llmDebugSection('Task instructions (continuity initial_message)', log.task_prompt)}
        ${_llmDebugSection('Formatted user message (sent to LLM)', log.formatted_prompt)}
        ${_llmDebugSection('Enriched content (memory/profile/hints injected)', log.enriched_content)}
        ${_llmDebugSection('Trigger text (raw user message)', log.trigger_content)}
        ${_llmDebugSection('Recent chat history', historyText)}
        ${_llmDebugSection('LLM response (raw)', log.response_raw)}
        ${_llmDebugSection('LLM response (cleaned for Discord)', log.response_clean || (hasResponse ? '' : '(no response captured yet)'))}
        ${sentViaTool}
        ${_llmDebugPostSendEditSection(flags.post_send_edit)}
    `;
}


function _renderLlmDebugModalBody() {
    const listHtml = _llmDebugLogsCache.length
        ? _llmDebugLogsCache.map(log => {
            const when = log.ts ? new Date(log.ts * 1000).toLocaleString() : '';
            const hasResponse = !!(log.response_raw || log.response_clean);
            const editKind = log.flags?.post_send_edit?.kind;
            const editBadge = editKind
                ? `<span class="dc-debug-badge edit">${_esc(_llmDebugPostSendEditKindLabel(editKind))}</span>`
                : '';
            const badge = hasResponse
                ? '<span class="dc-debug-badge">response</span>'
                : '<span class="dc-debug-badge pending">pending</span>';
            const selected = log.id === _llmDebugSelectedId ? ' selected' : '';
            const preview = (log.trigger_content || log.formatted_prompt || '').replace(/\s+/g, ' ').slice(0, 90);
            return `<div class="dc-debug-list-item${selected}" data-log-id="${log.id}">
                <div><strong>#${_esc(log.channel_name || log.channel_id || '?')}</strong> · ${_esc(log.username || '?')} ${badge}${editBadge}</div>
                <div class="dc-row-help" style="margin:2px 0 0">${_esc(when)} · ${_esc(preview || '(no preview)')}${preview.length >= 90 ? '…' : ''}</div>
            </div>`;
        }).join('')
        : '<p class="dc-empty">No LLM exchanges logged yet. Chat with the bot (with LLM Debug Messaging enabled), then refresh.</p>';

    const selected = _llmDebugLogsCache.find(l => l.id === _llmDebugSelectedId) || _llmDebugLogsCache[0] || null;
    if (!_llmDebugSelectedId && selected) _llmDebugSelectedId = selected.id;

    return `
        <div style="display:grid;grid-template-columns:minmax(220px,34%) 1fr;gap:14px;align-items:start">
            <div>${listHtml}</div>
            <div id="dc-llm-debug-detail">${_renderLlmDebugDetail(selected)}</div>
        </div>
    `;
}


async function _refreshLlmDebugModal() {
    const body = _llmDebugModalEl?.querySelector('#dc-llm-debug-body');
    const status = _llmDebugModalEl?.querySelector('#dc-llm-debug-status');
    if (!body) return;
    try {
        if (status) status.textContent = 'Loading…';
        const res = await fetch('/api/plugin/leona_discord/llm-debug?limit=25');
        const data = res.ok ? await res.json() : {};
        _llmDebugLogsCache = Array.isArray(data.logs) ? data.logs : [];
        if (!_llmDebugLogsCache.some(l => l.id === _llmDebugSelectedId)) {
            _llmDebugSelectedId = _llmDebugLogsCache[0]?.id ?? null;
        }
        body.innerHTML = _renderLlmDebugModalBody();
        body.querySelectorAll('.dc-debug-list-item').forEach(el => {
            el.addEventListener('click', () => {
                _llmDebugSelectedId = Number(el.dataset.logId);
                body.querySelectorAll('.dc-debug-list-item').forEach(n => n.classList.remove('selected'));
                el.classList.add('selected');
                const detail = body.querySelector('#dc-llm-debug-detail');
                const log = _llmDebugLogsCache.find(l => l.id === _llmDebugSelectedId);
                if (detail) detail.innerHTML = _renderLlmDebugDetail(log);
            });
        });
        if (status) status.textContent = `${_llmDebugLogsCache.length} exchange(s)`;
    } catch (e) {
        body.innerHTML = `<p class="dc-empty">Failed to load: ${_esc(e.message)}</p>`;
        if (status) status.textContent = 'Error';
    }
}


async function _openLlmDebugModal() {
    _closeLlmDebugModal();
    _llmDebugLogsCache = [];
    _llmDebugSelectedId = null;

    const overlay = document.createElement('div');
    overlay.className = 'dc-modal-overlay';
    overlay.innerHTML = `
        <div class="dc-modal" role="dialog" aria-labelledby="dc-llm-debug-title">
            <div class="dc-modal-header">
                <h3 id="dc-llm-debug-title">LLM Debug Messaging</h3>
                <div class="dc-modal-actions">
                    <span id="dc-llm-debug-status" class="dc-row-help"></span>
                    <button type="button" class="dc-btn dc-btn-sm" id="dc-llm-debug-refresh">Refresh</button>
                    <button type="button" class="dc-btn dc-btn-sm" id="dc-llm-debug-close">Close</button>
                </div>
            </div>
            <div class="dc-modal-body" id="dc-llm-debug-body"><p class="dc-empty">Loading…</p></div>
        </div>
    `;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closeLlmDebugModal();
    });
    document.body.appendChild(overlay);
    _llmDebugModalEl = overlay;

    overlay.querySelector('#dc-llm-debug-close')?.addEventListener('click', _closeLlmDebugModal);
    overlay.querySelector('#dc-llm-debug-refresh')?.addEventListener('click', () => _refreshLlmDebugModal());
    await _refreshLlmDebugModal();
}


function _profileDispositionLine(p) {
    const vals = [
        ['fam', p.familiarity],
        ['warm', p.warmth],
        ['trust', p.trust],
        ['play', p.playfulness],
        ['pat', p.patience],
        ['int', p.interest],
    ];
    return vals
        .map(([k, v]) => `${k}:${Number(v ?? 0).toFixed(2)}`)
        .join(' · ');
}


async function _loadProfiles(container) {
    const panel = container.querySelector('#dc-profile-list');
    const status = container.querySelector('#dc-profile-status');
    if (!panel) return;
    try {
        const account = (container.querySelector('#dc-profile-filter-account')?.value || '').trim();
        const guildId = (container.querySelector('#dc-profile-filter-guild')?.value || '').trim();
        const username = (container.querySelector('#dc-profile-filter-username')?.value || '').trim();
        const qs = new URLSearchParams({ limit: '100' });
        if (account) qs.set('account', account);
        if (guildId) qs.set('guild_id', guildId);
        if (username) qs.set('username', username);

        const res = await fetch(`/api/plugin/leona_discord/profiles?${qs.toString()}`);
        const data = res.ok ? await res.json() : {};
        const profiles = Array.isArray(data.profiles) ? data.profiles : [];
        if (status) {
            const activeFilters = [account, guildId, username].filter(Boolean).length;
            const suffix = activeFilters ? ' (filtered)' : '';
            status.textContent = `${profiles.length} profile(s)${suffix}`;
            status.className = 'dc-status dc-status-ok';
        }
        if (!profiles.length) {
            panel.innerHTML = '<p class="dc-empty">No user profiles yet. Enable profiling and chat a bit first.</p>';
            return;
        }
        panel.innerHTML = profiles.map((p, idx) => {
            const name = p.display_name || p.username || p.author_id || 'unknown';
            const when = p.last_seen_at ? new Date(p.last_seen_at * 1000).toLocaleString() : 'unknown';
            const facts = (p.facts || []).slice(0, 4).map(f => `• ${_esc(f.fact_value || '')}`).join('<br>');
            const summary = _esc((p.summary_l1 || '').trim() || '(no summary yet)');
            const disp = _esc(_profileDispositionLine(p));
            const scope = 'all servers';
            return `
                <div class="dc-card" style="margin-bottom:8px">
                    <div class="dc-row" style="align-items:center">
                        <div class="dc-row-label">
                            <label>${_esc(name)} <span class="dc-row-help" style="display:inline;margin-left:8px">${scope}</span></label>
                            <div class="dc-row-help">@${_esc(p.username || 'unknown')} · ${_esc(p.author_id || '')} · last seen ${_esc(when)}</div>
                        </div>
                        <div class="dc-row-control">
                            <button class="dc-btn dc-btn-sm dc-btn-danger dc-reset-profile-btn"
                                data-account="${_esc(p.account || '')}"
                                data-guild-id="${_esc(p.guild_id || '')}"
                                data-author-id="${_esc(p.author_id || '')}">Reset</button>
                        </div>
                    </div>
                    <div class="dc-row-help" style="margin:2px 0 6px">${summary}</div>
                    <div class="dc-row-help" style="margin:2px 0 6px"><strong>Disposition:</strong> ${disp}</div>
                    <div class="dc-row-help" style="margin:2px 0 6px"><strong>Messages/Replies:</strong> ${Number(p.message_count || 0)} / ${Number(p.reply_count || 0)}</div>
                    <div class="dc-row-help"><strong>Top Facts:</strong><br>${facts || '• none yet'}</div>
                </div>
            `;
        }).join('');

        panel.querySelectorAll('.dc-reset-profile-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const account = btn.dataset.account || '';
                const guild_id = btn.dataset.guildId || '';
                const author_id = btn.dataset.authorId || '';
                if (!account || !author_id) return;
                if (!window.confirm('Reset this profile and all learned facts?')) return;
                btn.disabled = true;
                const old = btn.textContent;
                btn.textContent = 'Resetting…';
                try {
                    const r = await fetch('/api/plugin/leona_discord/profiles/reset', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                        body: JSON.stringify({ account, guild_id, author_id }),
                    });
                    if (!r.ok) throw new Error(`HTTP ${r.status}`);
                    _loadProfiles(container);
                } catch (e) {
                    if (status) {
                        status.textContent = `Reset failed: ${e.message}`;
                        status.className = 'dc-status dc-status-err';
                    }
                } finally {
                    btn.disabled = false;
                    btn.textContent = old;
                }
            });
        });
    } catch (e) {
        panel.innerHTML = `<p class="dc-empty">Failed to load profiles: ${_esc(e.message)}</p>`;
        if (status) {
            status.textContent = 'Profile load failed';
            status.className = 'dc-status dc-status-err';
        }
    }
}


function _computeServerEffective(globalS, override) {
    const effective = { ...globalS, ...override };
    const preset = (override.personality_preset || '').toLowerCase();
    if (preset && preset !== 'custom' && PRESET_VALUES[preset]) {
        Object.assign(effective, PRESET_VALUES[preset], override);
    }
    return effective;
}


// ── Per-Server Overrides ───────────────────────────────────────────────────────

async function _loadServers(container) {
    const panel = container.querySelector('#dc-server-list');
    if (!panel) return;

    try {
        const [sRes, cfgRes] = await Promise.all([
            fetch('/api/plugin/leona_discord/servers'),
            fetch('/api/plugin/leona_discord/settings'),
        ]);
        if (!sRes.ok) throw new Error('Could not load servers');
        const { servers } = await sRes.json();
        const cfg          = cfgRes.ok ? await cfgRes.json() : {};
        const globalS      = { ..._DEFAULTS, ...(cfg.global ?? {}) };
        const overrides    = cfg.servers ?? {};
        _renderServerList(container, panel, servers ?? [], globalS, overrides);
    } catch (e) {
        panel.innerHTML = `<p class="dc-error-text">Could not load servers: ${_esc(e.message)}</p>`;
    }
}


function _renderServerList(container, panel, servers, globalS, overrides) {
    if (servers.length === 0) {
        panel.innerHTML = '<p class="dc-empty">No servers connected yet.</p>';
        return;
    }

    panel.innerHTML = servers.map(s => {
        const hasOverride = !!(overrides[s.guild_id] && Object.keys(overrides[s.guild_id]).length > 0);
        return `
            <div class="dc-server-row">
                <div class="dc-server-info">
                    <div class="dc-server-name">${_esc(s.guild_name)}</div>
                    <div class="dc-server-meta">
                        ${hasOverride
                            ? '<span class="dc-badge dc-badge-override">Override active</span>'
                            : '<span style="color:var(--text-muted,#72767d)">Using global defaults</span>'}
                        &ensp;${s.member_count ?? '?'} members &ensp;via ${_esc(s.account)}
                    </div>
                </div>
                <div class="dc-server-actions">
                    <button class="dc-btn dc-btn-sm dc-srv-edit"
                        data-guild="${_esc(s.guild_id)}" data-name="${_esc(s.guild_name)}">
                        ${hasOverride ? 'Edit Override' : 'Add Override'}
                    </button>
                    ${hasOverride
                        ? `<button class="dc-btn dc-btn-sm dc-btn-danger dc-srv-reset"
                               data-guild="${_esc(s.guild_id)}" data-name="${_esc(s.guild_name)}">Reset</button>`
                        : ''}
                </div>
            </div>
            <div id="dc-sform-${_esc(s.guild_id)}" style="display:none"></div>
        `;
    }).join('');

    panel.querySelectorAll('.dc-srv-edit').forEach(btn => {
        btn.addEventListener('click', () => {
            const gid      = btn.dataset.guild;
            const gname    = btn.dataset.name;
            const override = overrides[gid] ?? {};
            const effective = _computeServerEffective(globalS, override);
            _showServerForm(container, panel, gid, gname, effective, override);
        });
    });

    panel.querySelectorAll('.dc-srv-reset').forEach(btn => {
        btn.addEventListener('click', async () => {
            const gid = btn.dataset.guild;
            if (!confirm(`Reset "${btn.dataset.name}" to global defaults?`)) return;
            btn.disabled = true;
            btn.textContent = 'Resetting…';
            try {
                await fetch(`/api/plugin/leona_discord/settings/servers/${gid}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRF-Token': CSRF() },
                });
                _loadServers(container);
            } catch (_) {
                btn.disabled = false;
                btn.textContent = 'Reset';
            }
        });
    });
}


function _showServerForm(container, panel, guildId, guildName, effective, rawOverride = {}) {
    panel.querySelectorAll('[id^="dc-sform-"]').forEach(f => {
        if (f.id !== `dc-sform-${guildId}`) { f.style.display = 'none'; f.innerHTML = ''; }
    });

    const formEl = panel.querySelector(`#dc-sform-${guildId}`);
    if (!formEl) return;

    const prefix = `dc-sv-${guildId}`;

    formEl.style.display = 'block';
    formEl.innerHTML = `
        <div class="dc-subform" style="margin-top:4px">
            <div class="dc-subform-title">${_esc(guildName)} — Server Override</div>
            <div class="dc-subform-hint">
                Values shown are current effective settings (global + existing override).
                Adjust and save, or hit Reset to remove the override entirely.
            </div>
            <div id="${prefix}-fields"></div>
            <div class="dc-card" style="margin-top:6px">
                <div class="dc-subform-title">Channel Override</div>
                <div class="dc-row-help" style="margin-bottom:8px">Set reply mode for a specific channel (ID or name, e.g. memes).</div>
                <div class="dc-row">
                    <input type="text" id="${prefix}-ch-key" class="dc-input" placeholder="channel id or name">
                    <select id="${prefix}-ch-mode" class="dc-input dc-input-sm">
                        <option value="default">Default</option>
                        <option value="mentions_only">Mentions only</option>
                        <option value="reactions_only">Reactions only</option>
                        <option value="never">Never</option>
                    </select>
                </div>
                <div id="${prefix}-ch-list" class="dc-row-help"></div>
            </div>
            <div class="dc-subform-footer">
                <button class="dc-btn dc-btn-primary dc-btn-sm" id="${prefix}-save">Save Override</button>
                <button class="dc-btn dc-btn-sm" id="${prefix}-cancel">Cancel</button>
                <span id="${prefix}-status" class="dc-status"></span>
            </div>
        </div>
    `;

    formEl.querySelector(`#${prefix}-fields`).innerHTML = _msgFieldsHTML(prefix);
    _wireSliders(formEl, prefix);
    _wireReactionToggle(formEl, prefix);
    _wireAutoTypoToggle(formEl, prefix);
    _wireAppendToggle(formEl, prefix);
    _wirePreset(formEl, prefix);
    _populateFields(formEl, prefix, effective);

    const chList = formEl.querySelector(`#${prefix}-ch-list`);
    const channels = rawOverride.channels || {};
    const chEntries = Object.entries(channels);
    if (chList && chEntries.length) {
        chList.innerHTML = 'Active: ' + chEntries.map(([k, v]) =>
            `<code>${_esc(k)}</code> → ${_esc(v.reply_mode || 'default')}`
        ).join(', ');
    }

    formEl.querySelector(`#${prefix}-cancel`)?.addEventListener('click', () => {
        formEl.style.display = 'none';
        formEl.innerHTML = '';
    });

    formEl.querySelector(`#${prefix}-save`)?.addEventListener('click', async () => {
        const saveBtn = formEl.querySelector(`#${prefix}-save`);
        const status  = formEl.querySelector(`#${prefix}-status`);
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        try {
            const res = await fetch(`/api/plugin/leona_discord/settings/servers/${guildId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                body: JSON.stringify(_perServerFields(formEl, prefix)),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            formEl.style.display = 'none';
            formEl.innerHTML = '';
            _loadServers(container);
        } catch (e) {
            if (status) { status.textContent = e.message; status.className = 'dc-status dc-status-err'; }
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Override';
        }
    });
}


// ── Bot Accounts ───────────────────────────────────────────────────────────────

async function _loadAccounts(container) {
    const list = container.querySelector('#dc-accounts-list');
    if (!list) return;

    try {
        const res = await fetch('/api/plugin/leona_discord/accounts');
        if (!res.ok) throw new Error('Failed to fetch accounts');
        const data = await res.json();
        const accounts = data.accounts || [];

        if (accounts.length === 0) {
            list.innerHTML = '<p class="dc-empty">No bots configured. Add one to get started.</p>';
            return;
        }

        list.innerHTML = accounts.map(a => `
            <div class="dc-account-card" data-account="${_esc(a.name)}">
                <div class="dc-account-info">
                    <div class="dc-account-name">${_esc(a.bot_name || a.name)}</div>
                    <div class="dc-account-meta">
                        ${a.connected
                            ? '<span class="dc-badge dc-badge-online">Connected</span>'
                            : '<span class="dc-badge dc-badge-offline">Disconnected</span>'}
                        ${a.bot_id ? `<span>ID: ${_esc(a.bot_id)}</span>` : ''}
                    </div>
                </div>
                <div class="dc-account-actions">
                    <button class="dc-btn dc-btn-sm dc-test-account" data-name="${_esc(a.name)}">Test</button>
                    <button class="dc-btn dc-btn-sm dc-btn-danger dc-delete-account" data-name="${_esc(a.name)}">Remove</button>
                </div>
            </div>
        `).join('');

        list.querySelectorAll('.dc-test-account').forEach(btn => {
            btn.addEventListener('click', async () => {
                const name = btn.dataset.name;
                btn.disabled = true;
                btn.textContent = 'Testing…';
                try {
                    const res = await fetch(`/api/plugin/leona_discord/accounts/${name}/test`, {
                        method: 'POST',
                        headers: { 'X-CSRF-Token': CSRF() }
                    });
                    const data = await res.json();
                    if (data.success) {
                        btn.textContent = `✓ ${data.bot_name}`;
                        btn.classList.add('dc-btn-primary');
                        _loadAccounts(container);
                    } else {
                        btn.textContent = '✗ Failed';
                        btn.classList.add('dc-btn-danger');
                    }
                } catch (e) {
                    btn.textContent = 'Error';
                }
                setTimeout(() => {
                    btn.textContent = 'Test';
                    btn.className = 'dc-btn dc-btn-sm dc-test-account';
                    btn.disabled = false;
                }, 3000);
            });
        });

        list.querySelectorAll('.dc-delete-account').forEach(btn => {
            btn.addEventListener('click', async () => {
                const name = btn.dataset.name;
                if (!confirm(`Remove bot "${name}"?`)) return;
                btn.disabled = true;
                btn.textContent = 'Removing…';
                try {
                    await fetch(`/api/plugin/leona_discord/accounts/${name}`, {
                        method: 'DELETE',
                        headers: { 'X-CSRF-Token': CSRF() }
                    });
                    _loadAccounts(container);
                } catch (e) {
                    btn.disabled = false;
                    btn.textContent = 'Remove';
                }
            });
        });
    } catch (e) {
        list.innerHTML = `<p class="dc-error-text">Could not load accounts: ${_esc(e.message)}</p>`;
    }
}


function _showAddForm(container) {
    const form = container.querySelector('#dc-add-form');
    if (!form) return;
    form.style.display = 'block';

    form.innerHTML = `
        <div class="dc-subform" style="margin-top:10px">
            <div class="dc-subform-title">Add Discord Bot</div>
            <div class="dc-subform-hint">Get your token from discord.com/developers → Bot → Reset Token</div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Account Name</label>
                    <div class="dc-row-help">A short label like "sapphire" or "modbot"</div>
                </div>
                <div class="dc-row-control">
                    <input type="text" id="dc-add-name" placeholder="sapphire" class="dc-input dc-input-md">
                </div>
            </div>
            <div class="dc-row">
                <div class="dc-row-label">
                    <label>Bot Token</label>
                    <div class="dc-row-help">Paste from the Discord developer portal</div>
                </div>
                <div class="dc-row-control">
                    <input type="password" id="dc-add-token" placeholder="paste bot token" class="dc-input dc-input-lg">
                </div>
            </div>
            <div class="dc-subform-footer">
                <button class="dc-btn dc-btn-primary dc-btn-sm" id="dc-add-save">Add Bot</button>
                <button class="dc-btn dc-btn-sm" id="dc-add-cancel">Cancel</button>
                <span id="dc-add-status" class="dc-status"></span>
            </div>
        </div>
    `;

    form.querySelector('#dc-add-cancel')?.addEventListener('click', () => {
        form.style.display = 'none';
        form.innerHTML = '';
    });

    form.querySelector('#dc-add-save')?.addEventListener('click', async () => {
        const name   = form.querySelector('#dc-add-name')?.value?.trim();
        const token  = form.querySelector('#dc-add-token')?.value?.trim();
        const status = form.querySelector('#dc-add-status');

        if (!name || !token) {
            if (status) { status.textContent = 'Name and token required.'; status.className = 'dc-status dc-status-err'; }
            return;
        }

        const btn = form.querySelector('#dc-add-save');
        btn.disabled = true;
        btn.textContent = 'Adding…';

        try {
            const res = await fetch('/api/plugin/leona_discord/accounts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF() },
                body: JSON.stringify({ account_name: name, token })
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            if (status) { status.textContent = `Added ${name}. Bot connecting…`; status.className = 'dc-status dc-status-ok'; }
            setTimeout(() => {
                form.style.display = 'none';
                form.innerHTML = '';
                _loadAccounts(container);
            }, 1500);
        } catch (e) {
            if (status) { status.textContent = e.message; status.className = 'dc-status dc-status-err'; }
            btn.disabled = false;
            btn.textContent = 'Add Bot';
        }
    });
}


function _esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

export default { init() {} };
