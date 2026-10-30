/* Apple Music card: search Apple Music and play it on Sonos speakers. */

const STRINGS = {
  en: {
    search: "Search songs, albums, artists and playlists",
    assist: "Ask Assist",
    group: "Group speakers",
    volume_down: "Volume down",
    volume_up: "Volume up",
    playlists: "Playlists",
    no_playlists: "There are no Apple Music playlists in your Sonos favorites. Add them in the Sonos app.",
    top_songs: "Top songs",
    top_albums: "Top albums",
    songs: "Songs",
    albums: "Albums",
    artists: "Artists",
    play: "Play",
    play_top_songs: "Play top songs",
    show_list: "Show as a list",
    show_tiles: "Show as tiles",
    play_now: "Play now",
    play_next: "Play next",
    add: "Add to queue",
    replace: "Replace queue",
    more: "More",
    back: "Back",
    speaker: "Speaker",
    no_speakers: "No Sonos speakers found.",
    nothing: "Nothing found.",
    loading: "Loading…",
    nothing_playing: "Nothing playing",
    playing: "Playing on {speaker}",
    queued: "Added to the queue of {speaker}",
  },
  nl: {
    search: "Zoek nummers, albums, artiesten en afspeellijsten",
    assist: "Vraag het Assist",
    group: "Speakers groeperen",
    volume_down: "Zachter",
    volume_up: "Luider",
    playlists: "Afspeellijsten",
    no_playlists: "Er staan geen Apple Music-afspeellijsten in je Sonos-favorieten. Voeg ze toe in de Sonos-app.",
    top_songs: "Top nummers",
    top_albums: "Top albums",
    songs: "Nummers",
    albums: "Albums",
    artists: "Artiesten",
    play: "Afspelen",
    play_top_songs: "Speel top nummers",
    show_list: "Toon als lijst",
    show_tiles: "Toon als tegels",
    play_now: "Nu afspelen",
    play_next: "Hierna afspelen",
    add: "Achteraan toevoegen",
    replace: "Wachtrij vervangen",
    more: "Meer",
    back: "Terug",
    speaker: "Speaker",
    no_speakers: "Geen Sonos-speakers gevonden.",
    nothing: "Niets gevonden.",
    loading: "Laden…",
    nothing_playing: "Er speelt niets",
    playing: "Speelt op {speaker}",
    queued: "Toegevoegd aan de wachtrij van {speaker}",
  },
};

const SPEAKER_KEY = "apple-music-card:speaker";
const LAYOUT_KEY = "apple-music-card:playlist-layout";
// The catalog changes slowly, the charts once a day.
const CACHE_MS = 10 * 60 * 1000;
const SEARCH_DELAY_MS = 350;
const VOLUME_STEP = 0.05;
// How long a volume that was set counts, before the speaker reports it.
const VOLUME_PENDING_MS = 2000;

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

// Names compare without case and accents, so "cafe" finds "Café".
const fold = (text) => String(text ?? "").normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
const matches = (name, query) =>
  fold(query)
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => fold(name).includes(word));
const sameSpeakers = (a, b) => a.length === b.length && a.every((id) => b.includes(id));

// Apple serves the artwork in any size, the catalog hands out 600x600.
const artwork = (url, size) => (url ? url.replace("600x600", `${size}x${size}`) : "");

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; padding: 0; }
  input, select { font: inherit; color: var(--primary-text-color); }
  .player { border-bottom: 1px solid var(--divider-color); }
  .now { display: flex; align-items: center; gap: 12px; padding: 12px 16px 4px; }
  .now .art { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; flex: none; background: var(--secondary-background-color); display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .now .meta { flex: 1; min-width: 0; }
  .now .controls { display: flex; align-items: center; gap: 4px; flex: none; }
  .bar { display: flex; align-items: center; gap: 2px; padding: 0 8px 8px; }
  .speaker { flex: 1; min-width: 0; height: 36px; border: none; background: none; padding: 0 4px; color: var(--secondary-text-color); font-size: 0.9em; text-overflow: ellipsis; cursor: pointer; }
  .volume { width: 96px; accent-color: var(--primary-color); }
  .icon { width: 40px; height: 40px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; flex: none; color: var(--secondary-text-color); }
  .icon:hover, .icon:focus-visible { background: var(--secondary-background-color); color: var(--primary-text-color); outline: none; }
  .icon.accent, .icon[aria-expanded="true"] { color: var(--primary-color); }
  .groups { display: flex; flex-direction: column; gap: 8px; padding: 4px 16px 12px; border-bottom: 1px solid var(--divider-color); }
  .groups[hidden] { display: none; }
  .presets { display: flex; flex-wrap: wrap; gap: 8px; }
  .members { display: flex; flex-wrap: wrap; gap: 0 16px; }
  .member { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; cursor: pointer; }
  .member input { width: 18px; height: 18px; margin: 0; accent-color: var(--primary-color); cursor: pointer; }
  .field .icon { margin-right: -8px; }
  .title { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { color: var(--secondary-text-color); font-size: 0.875em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .field { display: flex; align-items: center; gap: 8px; margin: 12px 16px 0; padding: 0 12px; height: 44px; border-radius: 22px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .field input { flex: 1; min-width: 0; border: none; background: none; outline: none; height: 100%; }
  .content { max-height: var(--apple-music-height, 520px); overflow-y: auto; padding: 8px 0 12px; }
  .status { padding: 24px 16px; text-align: center; color: var(--secondary-text-color); }
  .tabs { display: flex; gap: 8px; padding: 4px 16px 8px; overflow-x: auto; }
  .tab { flex: none; padding: 6px 14px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: 0.9em; white-space: nowrap; }
  .tab[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  h3 { margin: 12px 16px 4px; font-size: 1em; font-weight: 600; }
  .row { display: flex; align-items: center; gap: 12px; padding: 4px 8px 4px 16px; }
  .row:hover { background: var(--secondary-background-color); }
  .row .thumb { width: 44px; height: 44px; border-radius: 4px; object-fit: cover; flex: none; background: var(--secondary-background-color); }
  .placeholder { display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .tabs .layout { width: 32px; height: 32px; margin-left: auto; }
  .row .meta { flex: 1; min-width: 0; text-align: start; }
  .row .meta span { display: block; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 16px 8px 72px; }
  .actions[hidden] { display: none; }
  .chip { padding: 6px 12px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: 0.875em; display: inline-flex; align-items: center; gap: 4px; }
  .chip.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip:hover { border-color: var(--primary-color); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 16px 12px; padding: 4px 16px 8px; }
  .tile { display: flex; flex-direction: column; gap: 4px; min-width: 0; text-align: start; }
  .tile .art { width: 100%; aspect-ratio: 1; border-radius: 6px; object-fit: cover; background: var(--secondary-background-color); }
  .artists { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 16px 8px; }
  .detail { display: flex; gap: 16px; align-items: center; padding: 4px 16px 8px; }
  .detail .cover { width: 112px; height: 112px; border-radius: 8px; object-fit: cover; flex: none; background: var(--secondary-background-color); }
  .detail .meta { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .detail .name { font-size: 1.25em; font-weight: 600; }
  .detail .buttons { display: flex; flex-wrap: wrap; gap: 8px; }
  .back { display: inline-flex; align-items: center; gap: 4px; margin: 0 8px; padding: 6px 8px; border-radius: 16px; color: var(--secondary-text-color); }
  .back:hover { color: var(--primary-text-color); }
  @media (max-width: 420px) {
    .volume { display: none; }
    .detail .cover { width: 80px; height: 80px; }
  }
`;

class AppleMusicCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._stack = [];
    this._query = "";
    this._tab = "playlist";
    this._layout = "grid";
    try {
      this._layout = localStorage.getItem(LAYOUT_KEY) ?? "grid";
    } catch (_err) {
      // Private windows can refuse storage, tiles will do.
    }
    this._items = new Map();
    this._cache = new Map();
    this._levels = new Map();
    this._presetList = [];
    this._renderId = 0;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (config.entities !== undefined && !Array.isArray(config.entities)) {
      throw new Error("entities must be a list of Sonos media players");
    }
    const groups = config.groups ?? [];
    if (!Array.isArray(groups) || groups.some((group) => !group?.name || !Array.isArray(group.entities))) {
      throw new Error("groups must be a list of groups, each with a name and entities");
    }
    this._config = config;
    if (this._hass) {
      this._build();
    }
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._build();
    } else {
      this._updateSpeakers();
      this._updatePlayer();
    }
  }

  get _t() {
    const language = this._hass?.locale?.language ?? this._hass?.language ?? "en";
    return STRINGS[language.split("-")[0]] ?? STRINGS.en;
  }

  _build() {
    const t = this._t;
    this.style.setProperty("--apple-music-height", this._config.height ?? "520px");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="player"></div>
        <div class="groups" hidden></div>
        <label class="field">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input class="search" type="search" placeholder="${esc(t.search)}" aria-label="${esc(t.search)}">
          <button class="icon assist" title="${esc(t.assist)}"><ha-icon icon="mdi:microphone"></ha-icon></button>
        </label>
        <div class="content"></div>
      </ha-card>`;
    const root = this.shadowRoot;
    root.querySelector(".search").addEventListener("input", (ev) => this._onSearch(ev.target.value));
    root.querySelector(".assist").addEventListener("click", () => this._assist());
    root.querySelector(".content").addEventListener("click", (ev) => this._onClick(ev));
    const player = root.querySelector(".player");
    player.addEventListener("click", (ev) => this._onPlayerClick(ev));
    player.addEventListener("change", (ev) => this._onPlayerChange(ev));
    const groups = root.querySelector(".groups");
    groups.addEventListener("click", (ev) => this._onGroupsClick(ev));
    groups.addEventListener("change", (ev) => this._onGroupsChange(ev));
    this._speakerList = undefined;
    this._playerStates = undefined;
    this._updateSpeakers();
    this._updatePlayer();
    this._render();
  }

  // Home Assistant opens Assist for a hass-action event, and listens right away
  // when the pipeline understands speech and the browser may use the microphone.
  _assist() {
    this.dispatchEvent(
      new CustomEvent("hass-action", {
        detail: { config: { tap_action: { action: "assist", start_listening: true } }, action: "tap" },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Speakers

  _speakers() {
    const states = this._hass.states;
    if (this._config.entities) {
      return this._config.entities.filter((id) => states[id]);
    }
    return Object.values(this._hass.entities ?? {})
      .filter((e) => e.platform === "sonos" && e.entity_id.startsWith("media_player.") && !e.hidden)
      .map((e) => e.entity_id)
      .filter((id) => states[id])
      .sort((a, b) => this._name(a).localeCompare(this._name(b)));
  }

  _name(entityId) {
    return this._hass.states[entityId]?.attributes.friendly_name ?? entityId;
  }

  // Grouped speakers play one queue, so a Sonos group is one choice. It plays on
  // its coordinator, the first member, when the card lists it. A group made of
  // the speakers of a preset group carries its name.
  _targets() {
    const speakers = this._speakers();
    const presets = this._presets();
    const grouped = new Set();
    const targets = [];
    for (const id of speakers) {
      if (grouped.has(id)) {
        continue;
      }
      const members = this._hass.states[id].attributes.group_members ?? [id];
      members.forEach((member) => grouped.add(member));
      const present = members.filter((member) => this._hass.states[member]);
      const preset = presets.find((group) => sameSpeakers(group.members, present));
      targets.push({
        id: speakers.includes(members[0]) ? members[0] : id,
        members: present,
        name: preset?.name ?? members.map((member) => this._name(member)).join(" + "),
      });
    }
    return targets;
  }

  _target() {
    return this._targets().find((target) => target.id === this._speaker);
  }

  _updateSpeakers() {
    const targets = this._targets();
    const key = targets.map((target) => `${target.id}=${target.name}`).join();
    if (key === this._speakerList) {
      return;
    }
    this._speakerList = key;
    let saved = null;
    try {
      saved = localStorage.getItem(SPEAKER_KEY);
    } catch (_err) {
      // Private windows can refuse storage, the first speaker will do.
    }
    // A speaker that joined a group is chosen through its group. The card follows
    // the speaker that was chosen, also while its new group still has to show up.
    const find = (id) => targets.find((target) => target.members.includes(id))?.id;
    this._speaker = find(this._chosen) ?? find(this._speaker) ?? find(saved) ?? targets[0]?.id;
    this._playerStates = undefined;
    this._updateGroups();
  }

  _choose(speaker) {
    this._chosen = speaker;
    this._speaker = speaker;
    try {
      localStorage.setItem(SPEAKER_KEY, speaker);
    } catch (_err) {
      // Remembering the speaker is a convenience.
    }
    this._speakerList = undefined;
    this._updateSpeakers();
    this._updatePlayer();
  }

  _updatePlayer() {
    const player = this.shadowRoot.querySelector(".player");
    // The volume of a group follows all its speakers.
    const states = this._members().map((id) => this._hass.states[id]);
    const known = this._playerStates;
    if (!player || (known?.length === states.length && states.every((state, i) => state === known[i]))) {
      return;
    }
    // Leave the volume alone while it is being dragged.
    if (this.shadowRoot.activeElement?.classList.contains("volume")) {
      return;
    }
    this._playerStates = states;
    const t = this._t;
    const state = this._hass.states[this._speaker];
    if (!state) {
      player.innerHTML = `<div class="status">${esc(t.no_speakers)}</div>`;
      return;
    }
    const a = state.attributes;
    const playing = state.state === "playing";
    const art = a.entity_picture
      ? `<img class="art" src="${esc(a.entity_picture)}" alt="">`
      : `<div class="art"><ha-icon icon="mdi:music"></ha-icon></div>`;
    const options = this._targets()
      .map((target) => {
        const speakers = target.members.map((id) => this._name(id)).join(", ");
        return `<option value="${esc(target.id)}" title="${esc(speakers)}" ${target.id === this._speaker ? "selected" : ""}>${esc(target.name)}</option>`;
      })
      .join("");
    const grouping = !this.shadowRoot.querySelector(".groups").hidden;
    player.innerHTML = `
      <div class="now">
        ${art}
        <div class="meta">
          <div class="title">${esc(a.media_title || t.nothing_playing)}</div>
          <div class="sub">${esc(a.media_artist ?? "")}</div>
        </div>
        <div class="controls">
          <button class="icon" data-service="media_play_pause" title="${esc(t.play)}">
            <ha-icon icon="${playing ? "mdi:pause" : "mdi:play"}"></ha-icon>
          </button>
          <button class="icon" data-service="media_next_track"><ha-icon icon="mdi:skip-next"></ha-icon></button>
        </div>
      </div>
      <div class="bar">
        <button class="icon" data-action="groups" title="${esc(t.group)}" aria-expanded="${grouping}">
          <ha-icon icon="mdi:speaker-multiple"></ha-icon>
        </button>
        <select class="speaker" aria-label="${esc(t.speaker)}">${options}</select>
        <button class="icon" data-volume="-1" title="${esc(t.volume_down)}"><ha-icon icon="mdi:volume-minus"></ha-icon></button>
        <input class="volume" type="range" min="0" max="100" value="${Math.round(this._volume() * 100)}" aria-label="Volume">
        <button class="icon" data-volume="1" title="${esc(t.volume_up)}"><ha-icon icon="mdi:volume-plus"></ha-icon></button>
      </div>`;
  }

  _onPlayerClick(ev) {
    const button = ev.target.closest("button");
    if (button?.dataset.service) {
      this._hass.callService("media_player", button.dataset.service, {}, { entity_id: this._speaker });
    } else if (button?.dataset.volume) {
      this._setVolume(this._volume() + Number(button.dataset.volume) * VOLUME_STEP);
    } else if (button?.dataset.action === "groups") {
      const panel = this.shadowRoot.querySelector(".groups");
      panel.hidden = !panel.hidden;
      button.setAttribute("aria-expanded", String(!panel.hidden));
      this._updateGroups();
    }
  }

  _onPlayerChange(ev) {
    if (ev.target.classList.contains("speaker")) {
      this._choose(ev.target.value);
    } else if (ev.target.classList.contains("volume")) {
      this._setVolume(Number(ev.target.value) / 100);
      ev.target.blur();
    }
  }

  _members() {
    return this._target()?.members ?? [this._speaker];
  }

  // A speaker takes a moment to report a new volume, so quick changes build on
  // the volume that was asked for.
  _level(id) {
    const pending = this._levels.get(id);
    if (pending && Date.now() - pending.time < VOLUME_PENDING_MS) {
      return pending.level;
    }
    return this._hass.states[id]?.attributes.volume_level ?? 0;
  }

  // A group's volume is the average of its speakers, like in the Sonos app.
  _volume() {
    const volumes = this._members().map((id) => this._level(id));
    return volumes.reduce((sum, volume) => sum + volume, 0) / volumes.length;
  }

  // Moving a group's volume moves every speaker by as much, which keeps their balance.
  _setVolume(volume) {
    const members = this._members();
    const change = volume - this._volume();
    for (const id of members) {
      const level = members.length > 1 ? this._level(id) + change : volume;
      const rounded = Math.round(Math.min(1, Math.max(0, level)) * 100) / 100;
      this._levels.set(id, { level: rounded, time: Date.now() });
      this._hass.callService("media_player", "volume_set", { volume_level: rounded }, { entity_id: id });
    }
  }

  // Grouping

  // Preset groups are the card's own, then the media player groups of Home
  // Assistant, as long as the card lists all their speakers. Speakers grouped
  // the same way show once, under the first name.
  _presets() {
    const speakers = this._speakers();
    const helpers = Object.values(this._hass.entities ?? {})
      .filter((e) => e.platform === "group" && e.entity_id.startsWith("media_player.") && !e.hidden)
      .map((e) => ({ name: this._name(e.entity_id), members: this._hass.states[e.entity_id]?.attributes.entity_id ?? [] }));
    const presets = [];
    for (const preset of [...(this._config.groups ?? []).map((group) => ({ name: group.name, members: group.entities })), ...helpers]) {
      const shown = preset.members.length > 1 && preset.members.every((id) => speakers.includes(id));
      if (shown && !presets.some((other) => sameSpeakers(other.members, preset.members))) {
        presets.push(preset);
      }
    }
    return presets;
  }

  _updateGroups() {
    const panel = this.shadowRoot.querySelector(".groups");
    if (!panel || panel.hidden) {
      return;
    }
    const members = this._members();
    this._presetList = this._presets();
    const presets = this._presetList
      .map((preset, index) => {
        const active = sameSpeakers(preset.members, members);
        const names = preset.members.map((id) => this._name(id)).join(", ");
        return `<button class="chip ${active ? "primary" : ""}" data-preset="${index}" title="${esc(names)}">
          <ha-icon icon="mdi:speaker-multiple" style="--mdc-icon-size: 18px"></ha-icon>${esc(preset.name)}</button>`;
      })
      .join("");
    const speakers = this._speakers()
      .map((id) => {
        const checked = members.includes(id);
        // A speaker on its own has no group to leave.
        const alone = checked && members.length === 1;
        return `<label class="member">
          <input type="checkbox" data-member="${esc(id)}" ${checked ? "checked" : ""} ${alone ? "disabled" : ""}>${esc(this._name(id))}
        </label>`;
      })
      .join("");
    panel.innerHTML = `${presets ? `<div class="presets">${presets}</div>` : ""}<div class="members">${speakers}</div>`;
  }

  // Sonos groups always have a coordinator, which Home Assistant lists first.
  _leader(id) {
    return this._hass.states[id]?.attributes.group_members?.[0] ?? id;
  }

  async _onGroupsChange(ev) {
    const id = ev.target.dataset.member;
    if (!id) {
      return;
    }
    let done;
    if (ev.target.checked) {
      done = await this._group("join", this._leader(this._speaker), { group_members: [id] });
    } else {
      if (id === (this._chosen ?? this._speaker)) {
        // The group plays on without the speaker, and the card stays with the group.
        this._chosen = this._members().find((member) => member !== id);
      }
      done = await this._group("unjoin", id);
    }
    if (!done) {
      this._updateGroups();
    }
  }

  async _onGroupsClick(ev) {
    const chip = ev.target.closest("[data-preset]");
    if (!chip) {
      return;
    }
    const { members } = this._presetList[Number(chip.dataset.preset)];
    // The music plays on when the chosen speaker is in the preset.
    const leader = members.includes(this._speaker) ? this._speaker : members[0];
    const current = this._hass.states[leader]?.attributes.group_members ?? [leader];
    // Home Assistant first takes a speaker out of a group it does not lead.
    const leads = current[0] === leader;
    const leave = leads ? current.filter((id) => !members.includes(id)) : [];
    const join = members.filter((id) => id !== leader && !(leads && current.includes(id)));
    if (leave.length && !(await this._group("unjoin", leave))) {
      return;
    }
    if (join.length && !(await this._group("join", leader, { group_members: join }))) {
      return;
    }
    this._choose(leader);
  }

  async _group(service, entityId, data = {}) {
    try {
      await this._hass.callService("media_player", service, data, { entity_id: entityId });
      return true;
    } catch (_err) {
      // Home Assistant shows the error.
      return false;
    }
  }

  // Catalog

  _fetch(message, cache = true) {
    if (!cache) {
      return this._hass.callWS(message);
    }
    const key = JSON.stringify(message);
    const cached = this._cache.get(key);
    if (cached && Date.now() - cached.time < CACHE_MS) {
      return cached.promise;
    }
    const promise = this._hass.callWS(message);
    promise.catch(() => this._cache.delete(key));
    this._cache.set(key, { time: Date.now(), promise });
    return promise;
  }

  _keep(items) {
    for (const item of items) {
      this._items.set(`${item.media_type}/${item.id}`, item);
    }
    return items;
  }

  // The Sonos favorites belong to the household, any of its speakers has them.
  // They are read every time, so a new favorite shows right away.
  async _playlists() {
    if (!this._speaker) {
      return [];
    }
    const { items } = await this._fetch({ type: "apple_music/playlists", entity_id: this._speaker }, false);
    return items;
  }

  // Playing

  async _play(url, enqueue) {
    const t = this._t;
    if (!this._speaker) {
      this._toast(t.no_speakers);
      return;
    }
    try {
      await this._hass.callService("apple_music", "play", { url, enqueue }, { entity_id: this._speaker });
    } catch (_err) {
      // Home Assistant shows the error.
      return;
    }
    const message = enqueue === "next" || enqueue === "add" ? t.queued : t.playing;
    this._toast(message.replace("{speaker}", this._name(this._speaker)));
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // Navigation

  _onSearch(value) {
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      const query = value.trim();
      if (query === this._query) {
        return;
      }
      this._query = query.length > 1 ? query : "";
      this._stack = [];
      this._render();
    }, SEARCH_DELAY_MS);
  }

  _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el) {
      return;
    }
    const { action, url, enqueue, key, tab } = el.dataset;
    if (action === "play") {
      this._play(url, enqueue);
    } else if (action === "more") {
      const actions = el.closest(".row").nextElementSibling;
      actions.hidden = !actions.hidden;
      el.setAttribute("aria-expanded", String(!actions.hidden));
    } else if (action === "open") {
      this._stack.push(this._items.get(key));
      this._render();
    } else if (action === "back") {
      this._stack.pop();
      this._render();
    } else if (action === "tab") {
      this._tab = tab;
      this._render();
    } else if (action === "layout") {
      this._layout = this._layout === "list" ? "grid" : "list";
      try {
        localStorage.setItem(LAYOUT_KEY, this._layout);
      } catch (_err) {
        // Remembering the layout is a convenience.
      }
      this._render();
    }
  }

  async _render() {
    const id = ++this._renderId;
    const content = this.shadowRoot.querySelector(".content");
    const item = this._stack.at(-1);
    const header = this._header(item);
    content.innerHTML = `${header}<div class="status">${esc(this._t.loading)}</div>`;
    content.scrollTop = 0;
    let body;
    try {
      body = await this._body(item);
    } catch (err) {
      body = `<div class="status">${esc(err.message ?? err)}</div>`;
    }
    if (id === this._renderId) {
      content.innerHTML = header + body;
    }
  }

  _header(item) {
    const t = this._t;
    if (!item) {
      if (this._query) {
        return "";
      }
      const tabs = [
        ["playlist", t.playlists],
        ["song", t.top_songs],
        ["album", t.top_albums],
      ]
        .map(([tab, label]) => `<button class="tab" data-action="tab" data-tab="${tab}" aria-pressed="${tab === this._tab}">${esc(label)}</button>`)
        .join("");
      const list = this._layout === "list";
      const layout =
        this._tab === "playlist"
          ? `<button class="icon layout" data-action="layout" title="${esc(list ? t.show_tiles : t.show_list)}">
              <ha-icon icon="${list ? "mdi:view-grid-outline" : "mdi:view-list"}"></ha-icon></button>`
          : "";
      return `<div class="tabs">${tabs}${layout}</div>`;
    }
    const back = `<button class="back" data-action="back"><ha-icon icon="mdi:chevron-left"></ha-icon>${esc(t.back)}</button>`;
    const isArtist = item.media_type === "artist";
    const image = isArtist ? "" : this._art(item.artwork_url, 300, "cover");
    return `
      ${back}
      <div class="detail">
        ${image}
        <div class="meta">
          <div>
            <div class="name">${esc(item.name)}</div>
            <div class="sub">${esc(item.artist ?? "")}</div>
          </div>
          <div class="buttons">
            ${this._chip(item.url, "replace", isArtist ? t.play_top_songs : t.play, true)}
            ${this._chip(item.url, "next", t.play_next)}
            ${this._chip(item.url, "add", t.add)}
          </div>
        </div>
      </div>`;
  }

  async _body(item) {
    const t = this._t;
    if (item?.media_type === "playlist") {
      // Without an Apple Developer account the songs of a playlist are unknown.
      return "";
    }
    if (item?.media_type === "album") {
      const { songs } = await this._fetch({ type: "apple_music/album", album_id: item.id });
      return this._songs(songs, false);
    }
    if (item?.media_type === "artist") {
      const { songs, albums } = await this._fetch({ type: "apple_music/artist", artist_id: item.id });
      return this._section(t.songs, this._songs(songs), songs) + this._section(t.albums, this._albums(albums), albums);
    }
    if (this._query) {
      const query = this._query;
      // Apple's search knows no playlists, the Sonos favorites have them.
      const [{ songs, albums, artists }, playlists] = await Promise.all([
        this._fetch({ type: "apple_music/search", query }),
        this._playlists().then(
          (items) => items.filter((item) => matches(item.name, query)),
          () => [],
        ),
      ]);
      const body =
        this._section(t.playlists, this._playlistItems(playlists), playlists) +
        this._section(t.songs, this._songs(songs), songs) +
        this._section(t.albums, this._albums(albums), albums) +
        this._section(t.artists, this._artists(artists), artists);
      return body || `<div class="status">${esc(t.nothing)}</div>`;
    }
    if (this._tab === "playlist") {
      if (!this._speaker) {
        return `<div class="status">${esc(t.no_speakers)}</div>`;
      }
      const items = await this._playlists();
      return items.length ? this._playlistItems(items) : `<div class="status">${esc(t.no_playlists)}</div>`;
    }
    const { items } = await this._fetch({ type: "apple_music/charts", media_type: this._tab });
    return this._tab === "song" ? this._songs(items) : this._albums(items);
  }

  _section(title, html, items) {
    return items.length ? `<h3>${esc(title)}</h3>${html}` : "";
  }

  _chip(url, enqueue, label, primary = false) {
    const icon = { replace: "mdi:play", next: "mdi:playlist-play", add: "mdi:playlist-plus" }[enqueue];
    return `<button class="chip ${primary ? "primary" : ""}" data-action="play" data-url="${esc(url)}" data-enqueue="${enqueue}">
      <ha-icon icon="${icon}" style="--mdc-icon-size: 18px"></ha-icon>${esc(label)}</button>`;
  }

  _songs(songs, withArtwork = true) {
    const t = this._t;
    return songs
      .map((song) => {
        const sub = [song.artist, withArtwork ? song.album : null].filter(Boolean).join(" · ");
        const thumb = withArtwork ? `<img class="thumb" src="${esc(artwork(song.artwork_url, 120))}" loading="lazy" alt="">` : "";
        return `
          <div class="row">
            ${thumb}
            <button class="meta" data-action="play" data-url="${esc(song.url)}" data-enqueue="play">
              <span class="title">${esc(song.name)}</span>
              <span class="sub">${esc(sub)}</span>
            </button>
            <button class="icon accent" data-action="play" data-url="${esc(song.url)}" data-enqueue="play" title="${esc(t.play_now)}">
              <ha-icon icon="mdi:play"></ha-icon>
            </button>
            <button class="icon" data-action="more" title="${esc(t.more)}" aria-expanded="false">
              <ha-icon icon="mdi:dots-vertical"></ha-icon>
            </button>
          </div>
          <div class="actions" hidden>
            ${this._chip(song.url, "next", t.play_next)}
            ${this._chip(song.url, "add", t.add)}
            ${this._chip(song.url, "replace", t.replace)}
          </div>`;
      })
      .join("");
  }

  // Playlists can come without artwork.
  _art(url, size, className) {
    return url
      ? `<img class="${className}" src="${esc(artwork(url, size))}" loading="lazy" alt="">`
      : `<div class="${className} placeholder"><ha-icon icon="mdi:playlist-music"></ha-icon></div>`;
  }

  _albums(albums) {
    this._keep(albums);
    const tiles = albums
      .map(
        (album) => `
          <button class="tile" data-action="open" data-key="${esc(album.media_type)}/${esc(album.id)}">
            ${this._art(album.artwork_url, 300, "art")}
            <span class="title">${esc(album.name)}</span>
            <span class="sub">${esc(album.artist ?? "")}</span>
          </button>`,
      )
      .join("");
    return `<div class="grid">${tiles}</div>`;
  }

  _playlistItems(playlists) {
    return this._layout === "list" ? this._playlistList(playlists) : this._albums(playlists);
  }

  // A playlist row opens the playlist, like its tile, and plays it from the buttons.
  _playlistList(playlists) {
    this._keep(playlists);
    const t = this._t;
    return playlists
      .map(
        (playlist) => `
          <div class="row">
            ${this._art(playlist.artwork_url, 120, "thumb")}
            <button class="meta" data-action="open" data-key="${esc(playlist.media_type)}/${esc(playlist.id)}">
              <span class="title">${esc(playlist.name)}</span>
            </button>
            <button class="icon accent" data-action="play" data-url="${esc(playlist.url)}" data-enqueue="replace" title="${esc(t.play)}">
              <ha-icon icon="mdi:play"></ha-icon>
            </button>
            <button class="icon" data-action="more" title="${esc(t.more)}" aria-expanded="false">
              <ha-icon icon="mdi:dots-vertical"></ha-icon>
            </button>
          </div>
          <div class="actions" hidden>
            ${this._chip(playlist.url, "next", t.play_next)}
            ${this._chip(playlist.url, "add", t.add)}
          </div>`,
      )
      .join("");
  }

  _artists(artists) {
    this._keep(artists);
    const chips = artists
      .map(
        (artist) => `
          <button class="chip" data-action="open" data-key="artist/${esc(artist.id)}">
            <ha-icon icon="mdi:account-music" style="--mdc-icon-size: 18px"></ha-icon>${esc(artist.name)}
          </button>`,
      )
      .join("");
    return `<div class="artists">${chips}</div>`;
  }
}

if (!customElements.get("apple-music-card")) {
  customElements.define("apple-music-card", AppleMusicCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "apple-music-card",
    name: "Apple Music",
    description: "Search Apple Music and play it on your Sonos speakers.",
    documentationURL: "https://github.com/laurensdehoorne/homeassistant-apple",
  });
}
