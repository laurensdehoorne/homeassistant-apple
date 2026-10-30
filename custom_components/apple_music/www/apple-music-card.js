/* Apple Music card: search Apple Music and play it on Sonos speakers. */

const STRINGS = {
  en: {
    search: "Search songs, albums and artists",
    link: "Paste an Apple Music link",
    invalid_link: "That is not an Apple Music link.",
    playlists: "Playlists",
    no_playlists: "There are no Apple Music playlists in your Sonos favorites. Add them in the Sonos app.",
    top_songs: "Top songs",
    top_albums: "Top albums",
    songs: "Songs",
    albums: "Albums",
    artists: "Artists",
    play: "Play",
    play_top_songs: "Play top songs",
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
    search: "Zoek nummers, albums en artiesten",
    link: "Plak een Apple Music-link",
    invalid_link: "Dat is geen Apple Music-link.",
    playlists: "Afspeellijsten",
    no_playlists: "Er staan geen Apple Music-afspeellijsten in je Sonos-favorieten. Voeg ze toe in de Sonos-app.",
    top_songs: "Top nummers",
    top_albums: "Top albums",
    songs: "Nummers",
    albums: "Albums",
    artists: "Artiesten",
    play: "Afspelen",
    play_top_songs: "Speel top nummers",
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
// The catalog changes slowly, the charts once a day.
const CACHE_MS = 10 * 60 * 1000;
const SEARCH_DELAY_MS = 350;

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

// Apple serves the artwork in any size, the catalog hands out 600x600.
const artwork = (url, size) => (url ? url.replace("600x600", `${size}x${size}`) : "");

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; padding: 0; }
  input, select { font: inherit; color: var(--primary-text-color); }
  .player { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--divider-color); }
  .player .art { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; flex: none; background: var(--secondary-background-color); display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); }
  .player .meta { flex: 1; min-width: 0; }
  .speaker { max-width: 100%; border: none; background: none; padding: 0; color: var(--secondary-text-color); font-size: 0.85em; cursor: pointer; }
  .player .controls { display: flex; align-items: center; gap: 4px; flex: none; }
  .volume { width: 88px; accent-color: var(--primary-color); }
  .icon { width: 40px; height: 40px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; flex: none; color: var(--secondary-text-color); }
  .icon:hover, .icon:focus-visible { background: var(--secondary-background-color); color: var(--primary-text-color); outline: none; }
  .icon.accent { color: var(--primary-color); }
  .title { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { color: var(--secondary-text-color); font-size: 0.875em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .field { display: flex; align-items: center; gap: 8px; margin: 12px 16px 0; padding: 0 12px; height: 44px; border-radius: 22px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .field input { flex: 1; min-width: 0; border: none; background: none; outline: none; height: 100%; }
  .content { max-height: var(--apple-music-height, 520px); overflow-y: auto; padding: 8px 0 12px; }
  .status { padding: 24px 16px; text-align: center; color: var(--secondary-text-color); }
  .tabs { display: flex; gap: 8px; padding: 4px 16px 8px; }
  .tab { padding: 6px 14px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: 0.9em; }
  .tab[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  h3 { margin: 12px 16px 4px; font-size: 1em; font-weight: 600; }
  .row { display: flex; align-items: center; gap: 12px; padding: 4px 8px 4px 16px; }
  .row:hover { background: var(--secondary-background-color); }
  .row .thumb { width: 44px; height: 44px; border-radius: 4px; object-fit: cover; flex: none; background: var(--secondary-background-color); }
  .row .meta { flex: 1; min-width: 0; text-align: start; }
  .row .meta span { display: block; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 16px 8px 72px; }
  .actions[hidden] { display: none; }
  .chip { padding: 6px 12px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: 0.875em; display: inline-flex; align-items: center; gap: 4px; }
  .chip.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip:hover { border-color: var(--primary-color); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 16px 12px; padding: 4px 16px 8px; }
  .tile { display: flex; flex-direction: column; gap: 4px; min-width: 0; text-align: start; }
  .tile img { width: 100%; aspect-ratio: 1; border-radius: 6px; object-fit: cover; background: var(--secondary-background-color); }
  .artists { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 16px 8px; }
  .detail { display: flex; gap: 16px; align-items: center; padding: 4px 16px 8px; }
  .detail img { width: 112px; height: 112px; border-radius: 8px; object-fit: cover; flex: none; background: var(--secondary-background-color); }
  .detail .meta { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .detail .name { font-size: 1.25em; font-weight: 600; }
  .detail .buttons { display: flex; flex-wrap: wrap; gap: 8px; }
  .back { display: inline-flex; align-items: center; gap: 4px; margin: 0 8px; padding: 6px 8px; border-radius: 16px; color: var(--secondary-text-color); }
  .back:hover { color: var(--primary-text-color); }
  @media (max-width: 420px) {
    .volume { display: none; }
    .detail img { width: 80px; height: 80px; }
  }
`;

class AppleMusicCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._stack = [];
    this._query = "";
    this._tab = "playlist";
    this._items = new Map();
    this._cache = new Map();
    this._renderId = 0;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (config.entities !== undefined && !Array.isArray(config.entities)) {
      throw new Error("entities must be a list of Sonos media players");
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
        <label class="field">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input class="search" type="search" placeholder="${esc(t.search)}" aria-label="${esc(t.search)}">
        </label>
        <div class="content"></div>
      </ha-card>`;
    const root = this.shadowRoot;
    root.querySelector(".search").addEventListener("input", (ev) => this._onSearch(ev.target.value));
    root.querySelector(".content").addEventListener("click", (ev) => this._onClick(ev));
    root.querySelector(".content").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && ev.target.classList.contains("link")) {
        this._playLink();
      }
    });
    const player = root.querySelector(".player");
    player.addEventListener("click", (ev) => this._onPlayerClick(ev));
    player.addEventListener("change", (ev) => this._onPlayerChange(ev));
    this._speakerList = undefined;
    this._playerState = undefined;
    this._updateSpeakers();
    this._updatePlayer();
    this._render();
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
  // its coordinator, the first member, when the card lists it.
  _targets() {
    const speakers = this._speakers();
    const grouped = new Set();
    const targets = [];
    for (const id of speakers) {
      if (grouped.has(id)) {
        continue;
      }
      const members = this._hass.states[id].attributes.group_members ?? [id];
      members.forEach((member) => grouped.add(member));
      targets.push({
        id: speakers.includes(members[0]) ? members[0] : id,
        members: members.filter((member) => this._hass.states[member]),
        name: members.map((member) => this._name(member)).join(" + "),
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
    // A speaker that joined a group is chosen through its group.
    const find = (id) => targets.find((target) => target.members.includes(id))?.id;
    this._speaker = find(this._speaker) ?? find(saved) ?? targets[0]?.id;
    this._playerState = undefined;
  }

  _updatePlayer() {
    const player = this.shadowRoot.querySelector(".player");
    const state = this._hass.states[this._speaker];
    if (!player || state === this._playerState) {
      return;
    }
    // Leave the volume alone while it is being dragged.
    if (this.shadowRoot.activeElement?.classList.contains("volume")) {
      return;
    }
    this._playerState = state;
    const t = this._t;
    if (!state) {
      player.innerHTML = `<div class="sub">${esc(t.no_speakers)}</div>`;
      return;
    }
    const a = state.attributes;
    const playing = state.state === "playing";
    const art = a.entity_picture
      ? `<img class="art" src="${esc(a.entity_picture)}" alt="">`
      : `<div class="art"><ha-icon icon="mdi:music"></ha-icon></div>`;
    const options = this._targets()
      .map((target) => `<option value="${esc(target.id)}" ${target.id === this._speaker ? "selected" : ""}>${esc(target.name)}</option>`)
      .join("");
    player.innerHTML = `
      ${art}
      <div class="meta">
        <div class="title">${esc(a.media_title || t.nothing_playing)}</div>
        <div class="sub">${esc(a.media_artist ?? "")}</div>
        <select class="speaker" aria-label="${esc(t.speaker)}">${options}</select>
      </div>
      <div class="controls">
        <button class="icon" data-service="media_play_pause" title="${esc(t.play)}">
          <ha-icon icon="${playing ? "mdi:pause" : "mdi:play"}"></ha-icon>
        </button>
        <button class="icon" data-service="media_next_track"><ha-icon icon="mdi:skip-next"></ha-icon></button>
        <input class="volume" type="range" min="0" max="100" value="${Math.round(this._volume() * 100)}" aria-label="Volume">
      </div>`;
  }

  _onPlayerClick(ev) {
    const button = ev.target.closest("[data-service]");
    if (button) {
      this._hass.callService("media_player", button.dataset.service, {}, { entity_id: this._speaker });
    }
  }

  _onPlayerChange(ev) {
    if (ev.target.classList.contains("speaker")) {
      this._speaker = ev.target.value;
      try {
        localStorage.setItem(SPEAKER_KEY, this._speaker);
      } catch (_err) {
        // Remembering the speaker is a convenience.
      }
      this._playerState = undefined;
      this._updatePlayer();
    } else if (ev.target.classList.contains("volume")) {
      this._setVolume(Number(ev.target.value) / 100);
      ev.target.blur();
    }
  }

  _members() {
    return this._target()?.members ?? [this._speaker];
  }

  // A group's volume is the average of its speakers, like in the Sonos app.
  _volume() {
    const volumes = this._members().map((id) => this._hass.states[id]?.attributes.volume_level ?? 0);
    return volumes.reduce((sum, volume) => sum + volume, 0) / volumes.length;
  }

  // Moving a group's volume moves every speaker by as much, which keeps their balance.
  _setVolume(volume) {
    const change = volume - this._volume();
    for (const id of this._members()) {
      const current = this._hass.states[id]?.attributes.volume_level ?? 0;
      const level = this._members().length > 1 ? current + change : volume;
      this._hass.callService(
        "media_player",
        "volume_set",
        { volume_level: Math.round(Math.min(1, Math.max(0, level)) * 100) / 100 },
        { entity_id: id },
      );
    }
  }

  // Catalog

  _fetch(message) {
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

  _playLink() {
    const input = this.shadowRoot.querySelector(".link");
    const url = input.value.trim();
    if (!url.startsWith("https://music.apple.com/")) {
      this._toast(this._t.invalid_link);
      return;
    }
    input.value = "";
    this._play(url, "replace");
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
    } else if (action === "link") {
      this._playLink();
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
      return `
        <label class="field" style="margin-top: 4px; margin-bottom: 12px">
          <ha-icon icon="mdi:link-variant"></ha-icon>
          <input class="link" type="url" placeholder="${esc(t.link)}" aria-label="${esc(t.link)}">
          <button class="icon accent" data-action="link" title="${esc(t.play)}"><ha-icon icon="mdi:play"></ha-icon></button>
        </label>
        <div class="tabs">${tabs}</div>`;
    }
    const back = `<button class="back" data-action="back"><ha-icon icon="mdi:chevron-left"></ha-icon>${esc(t.back)}</button>`;
    const isArtist = item.media_type === "artist";
    const image = isArtist ? "" : `<img src="${esc(artwork(item.artwork_url, 300))}" alt="">`;
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
      const { songs, albums, artists } = await this._fetch({ type: "apple_music/search", query: this._query });
      const body =
        this._section(t.songs, this._songs(songs), songs) +
        this._section(t.albums, this._albums(albums), albums) +
        this._section(t.artists, this._artists(artists), artists);
      return body || `<div class="status">${esc(t.nothing)}</div>`;
    }
    if (this._tab === "playlist") {
      if (!this._speaker) {
        return `<div class="status">${esc(t.no_speakers)}</div>`;
      }
      // The Sonos favorites belong to the household, any of its speakers has them.
      const { items } = await this._fetch({ type: "apple_music/playlists", entity_id: this._speaker });
      return items.length ? this._albums(items) : `<div class="status">${esc(t.no_playlists)}</div>`;
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

  _albums(albums) {
    this._keep(albums);
    const tiles = albums
      .map(
        (album) => `
          <button class="tile" data-action="open" data-key="${esc(album.media_type)}/${esc(album.id)}">
            <img src="${esc(artwork(album.artwork_url, 300))}" loading="lazy" alt="">
            <span class="title">${esc(album.name)}</span>
            <span class="sub">${esc(album.artist ?? "")}</span>
          </button>`,
      )
      .join("");
    return `<div class="grid">${tiles}</div>`;
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
