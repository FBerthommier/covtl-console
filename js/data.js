// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* data.js — engine constants mirrored from covtl-pipeline (vtl_synth v1.1.0)
 * Source of truth: vtl_synth/core/constants.py, utils/setlang.py,
 * core/speaker_registry.py, core/sampa_guard.py. In LIVE mode these tables
 * are refreshed from GET /api/status; they are duplicated here only so the
 * console can run its offline DEMO mode and lay out controls before the
 * Python backend answers.
 * COVTL Console — GPL-3.0-or-later (matches the engine license).
 */

export const ENGINE = {
  name: 'vtl-synth',
  package: 'vtl_synth',
  version: '1.1.0',
  license: 'GPL-3.0-or-later',
  tractRateHz: 400,
  gestureRateHz: 100,
  audioRateHz: 44100,
  videoFps: 25,
  breathPauseMs: 130,          // ExpressivityProfile.pause_breath_ms ('%' marker)
};

/* ── Speakers (data/speakers/registry.json) ─────────────────────────── */
export const SPEAKERS = [
  { id: 'jd3', name: 'JD3', origin: 'Reference (SynthVTL24b original)', f0: 102.216 },
  { id: 's1',  name: 'S1',  origin: 'DVTD MRI subject 1 (male), calibrated v3', f0: 114.908 },
  { id: 's2',  name: 'S2',  origin: 'DVTD MRI subject 2 (female), calibrated v3', f0: 181.008 },
  { id: 'm01', name: 'M01', origin: 'Official VTL 2.4 ZIP (male), option A', f0: 120.0 },
  { id: 'w02', name: 'W02', origin: 'Official VTL 2.4 ZIP (female), option A', f0: 232.5 },
];
export const speakerById = (id) => SPEAKERS.find((s) => s.id === id) || SPEAKERS[0];

/* ── Language profiles (utils/setlang.py) ───────────────────────────── */
export const LANGUAGES = {
  en: {
    code: 'en', display: 'English', flag: 'EN',
    g2p: 'CMUdict (ARPAbet → engine SAMPA)',
    lexicon: 'cmudict',                                  // as reported live
    timings: { tcons: 100, tvoy: 80, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.06, final: 0.85, ref: 'ToBI (Beckman & Ayers 1997)' },
    alias: null,
    expressive: true,
  },
  fr: {
    code: 'fr', display: 'Français', flag: 'FR',
    g2p: 'Rule-based + exceptions dictionary',
    lexicon: 'rules + exceptions',
    timings: { tcons: 140, tvoy: 120, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.03, final: 0.85, ref: 'Jun & Fougeron (2002)' },
    alias: { 'œ': '9', 'æ': 'a' },
    expressive: true,
  },
  es: {
    code: 'es', display: 'Español', flag: 'ES',
    g2p: 'Wikipron lexicon + rules',
    lexicon: 'Wikipron TSV',
    timings: { tcons: 120, tvoy: 100, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.08, final: 0.85, ref: 'Face (2003)' },
    alias: { 'ñ': 'J', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u' },
    expressive: true,
  },
  de: {
    code: 'de', display: 'Deutsch', flag: 'DE',
    g2p: 'Wikipron lexicon + rules',
    lexicon: 'Wikipron TSV',
    timings: { tcons: 100, tvoy: 90, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.03, final: 0.80, ref: 'Grice et al. (2005)' },
    alias: { 'ß': 's', 'ä': 'E', 'ö': '2', 'ü': 'y' },
    expressive: true,
  },
  it: {
    code: 'it', display: 'Italiano', flag: 'IT',
    g2p: 'Wikipron lexicon + rules',
    lexicon: 'Wikipron TSV',
    timings: { tcons: 120, tvoy: 100, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.06, final: 0.85, ref: 'Avesani (1995)' },
    alias: { 'é': 'e', 'è': 'E', 'à': 'a', 'ì': 'i', 'ò': 'O', 'ó': 'o', 'ù': 'u' },
    expressive: true,
  },
  pt: {
    code: 'pt', display: 'Português', flag: 'PT',
    g2p: 'Wikipron lexicon + rules',
    lexicon: 'Wikipron TSV',
    timings: { tcons: 110, tvoy: 100, tpause: 200, tpauseLong: 320 },
    f0: { onset: 1.04, final: 0.80, ref: 'Frota (2000)' },
    alias: { 'ã': '@~', 'õ': 'o~', 'ç': 's', 'â': '@', 'ê': 'e', 'ô': 'o' },
    expressive: true,
  },
};

/* ── Engine SAMPA inventory (core/constants.py ALL_PHONEME_KEYS) ────── */
export const VOWELS = ['a', 'e', 'i', 'o', 'u', 'y', 'E', 'O', '@', '2', '6', '9'];
export const CONSONANTS = [
  'p', 'b', 't', 'd', 'k', 'g', 'f', 'v', 's', 'z', 'S', 'Z', 'T', 'D',
  'tS', 'dZ', 'm', 'n', 'J', 'l', 'R', 'j', 'w', 'h', 'ɥ',
];
export const NASALIZED = VOWELS.map((v) => v + '~');      // vowel + nasality marker
export const DIPHTHONGS = ['tS', 'dZ'];
/* Markers the guard tolerates (never reported as rejected) — sampa_guard.py */
export const TOLERATED_MARKERS = {
  ' ':  { label: 'Short pause',   kind: 'pause',  cli: '--tpause' },
  '.':  { label: 'Syllable link', kind: 'link',   cli: null },
  '-':  { label: 'Syllable',      kind: 'link',   cli: null },
  '|':  { label: 'Long pause',    kind: 'pause',  cli: '--tpause-long' },
  '~':  { label: 'Nasality',      kind: 'feature', cli: null },
  ',':  { label: 'Comma pause',   kind: 'pause',  cli: '--tpause' },
  '%':  { label: 'Breath pause',  kind: 'pause',  cli: 'ExpressivityProfile.pause_breath_ms (130 ms)' },
};

export const INVENTORY_KEYS = new Set([...VOWELS, ...CONSONANTS, ...NASALIZED]);
export function isVowel(sym)  { return VOWELS.includes(sym) || NASALIZED.includes(sym); }
export function isMarker(sym) { return Object.prototype.hasOwnProperty.call(TOLERATED_MARKERS, sym); }

/* ── Longest-match tokenizer — mirrors sampa_guard.unknown_symbols() ──
 * Walks the string exactly like the engine: tolerated markers first,
 * then diphthong keys, then the phoneme inventory (longest match first).
 * Anything unmatched is a symbol the engine parser would silently drop. */
export function tokenizeSampa(text) {
  const tokens = [];
  let i = 0;
  const push = (sym, kind) => tokens.push({ sym, kind, position: i });
  while (i < text.length) {
    const ch = text[i];
    if (isMarker(ch)) { push(ch, TOLERATED_MARKERS[ch].kind); i += 1; continue; }
    // diphthongs (longest match first)
    if (text.startsWith('tS', i)) { push('tS', 'consonant'); i += 2; continue; }
    if (text.startsWith('dZ', i)) { push('dZ', 'consonant'); i += 2; continue; }
    // vowel + nasality '~'
    if (INVENTORY_KEYS.has(ch) && text[i + 1] === '~') {
      push(ch + '~', 'vowel'); i += 2; continue;
    }
    if (INVENTORY_KEYS.has(ch)) { push(ch, isVowel(ch) ? 'vowel' : 'consonant'); i += 1; continue; }
    push(ch, 'rejected'); i += 1;
  }
  return tokens;
}

export function unknownSymbols(text) {
  return tokenizeSampa(text)
    .filter((t) => t.kind === 'rejected')
    .map((t) => ({ symbol: t.sym, position: t.position }));
}

/* ── Rejected-symbol aid — suggestions mirroring the bridge's SUGGESTIONS ──
 * Purely presentational: the authoritative rejection list always comes
 * from the engine (live) or this tokenizer (demo). These hints just help
 * the user fix a red symbol fast (IPA → engine SAMPA, uppercase ASCII,
 * ASCII approximations). Kept in sync with server.py SUGGESTIONS. */
export const REJECT_REASON = 'not in the engine inventory (ALL_PHONEME_KEYS) — the longest-match tokenizer would silently drop it before synthesis';

export const SAMPA_SUGGESTIONS = {
  c: ['k', 's'], x: ['k', 's'], q: ['k'],
  'ʃ': ['S'], 'ʒ': ['Z'], 'ŋ': ['J'], 'ɲ': ['J'], 'θ': ['T'], 'ð': ['D'],
  'ə': ['@'], 'ɛ': ['E'], 'ɔ': ['O'], 'ɪ': ['i'], 'ʊ': ['u'], 'ʌ': ['6'],
  'ɑ': ['a'], 'æ': ['a'], 'ø': ['2'], 'œ': ['9', '2'], 'ʏ': ['y'],
  'ã': ['a~'], 'õ': ['o~'], 'ĩ': ['i~'], 'ẽ': ['e~'], 'ũ': ['u~'],
  'ɐ': ['@', '6'], 'ɜ': ['@'], 'ɡ': ['g'], 'ɾ': ['R', 't'], 'ʀ': ['R'],
  'ʁ': ['R'], 'ʎ': ['j'], 'ʝ': ['j'], 'ç': ['s'], 'tʃ': ['tS'], 'dʒ': ['dZ'],
  A: ['a'], B: ['b'], C: ['k'], F: ['f'], G: ['g'], H: ['h'],
  I: ['i'], K: ['k'], L: ['l'], M: ['m'], N: ['n'], P: ['p'],
  Q: ['k'], U: ['u'], V: ['v'], W: ['w'], X: ['k', 's'], Y: ['y'],
};

export function suggestFor(sym) {
  const out = [...(SAMPA_SUGGESTIONS[sym] || [])];
  const low = sym.toLowerCase(), up = sym.toUpperCase();
  if (low !== sym && INVENTORY_KEYS.has(low) && !out.includes(low)) out.push(low);
  if (up !== sym && INVENTORY_KEYS.has(up) && !out.includes(up)) out.push(up);
  return [...new Set(out)].filter((s) => INVENTORY_KEYS.has(s) || isMarker(s)).slice(0, 3);
}

/* Enrich raw {symbol, position} pairs (demo path) to the same shape the
 * live bridge returns: reason + suggestions on every rejected symbol. */
export function enrichRejected(rejected) {
  return rejected.map((r) => ({ ...r, reason: REJECT_REASON, suggestions: suggestFor(r.symbol) }));
}

export function isSampaToken(word) {
  // Mirrors phonemes.is_sampa_token: every symbol of the word must be
  // in the inventory (markers not allowed inside a bare word).
  return word.length > 0 && [...word].every((c) => INVENTORY_KEYS.has(c));
}

/* ── Demo lexicons (DEMO mode only — the live mode calls the Python g2p) */
/* English: ARPAbet→SAMPA results for common words, syllable dots included. */
export const DEMO_LEXICON_EN = {
  a: '@', the: 'D@', this: 'Dis', is: 'iz', easy: 'i.zi', for: 'fOR', us: '@s',
  hello: 'h@.lo', world: 'wORld', good: 'gud', morning: 'mOR.nin', yes: 'jEs',
  no: 'no', one: 'w2n', two: 'tu', three: 'TRi', four: 'fOR', five: 'faiv',
  six: 'siks', seven: 'sE.v@n', eight: 'eit', nine: 'nain', ten: 'tEn',
  cat: 'kat', dog: 'dOg', house: 'haus', water: 'wO.tR', book: 'buk',
  speech: 'spitS', synthesis: 'sin.T@.sis', voice: 'vOis', tract: 'tRakt',
  vocal: 'vo.k@l', model: 'ma.d@l', articulatory: 'aR.ti.kj@.l@.tOR.i',
  text: 'tEkst', phoneme: 'fo.nim', phrase: 'fReiz', syllable: 'si.l@.b@l',
  pause: 'pOz', long: 'lO~', short: 'SORt', sound: 'saund', listen: 'li.s@n',
  speak: 'spik', slow: 'slo', fast: 'fast', again: '@.gEn', stop: 'stap',
  play: 'plei', quick: 'kwik', brown: 'bRaun', fox: 'faks', jumps: 'dZ2mps',
  over: 'o.vR', lazy: 'lei.zi', now: 'nau', say: 'sei',
  what: 'w2t', how: 'hau', why: 'wai', who: 'hu', we: 'wi', you: 'ju',
  they: 'Dei', them: 'DEm', our: 'auR', your: 'jOR', new: 'nu',
  york: 'jORk', time: 'taim', work: 'wORk', test: 'tEst', demo: 'dE.mo',
  guard: 'gaRd', error: 'ER', warning: 'waR.nin', red: 'REd', blue: 'blu',
  consonant: 'kan.s@.n@nt', vowel: 'vau.@l', polar: 'po.lR',
  plane: 'plein', target: 'taR.g@t', projection: 'pR@.dZEk.S@n',
};
/* French: rule-engine-style results for common words. */
export const DEMO_LEXICON_FR = {
  bonjour: 'bO~.ZuR', comment: 'kO.ma~', allez: 'a.le', vous: 'vu',
  merci: 'mER.si', ça: 'sa', va: 'va', bien: 'bjE~', monsieur: 'm@.sj2',
  madame: 'ma.dam', oui: 'wi', non: 'nO~', un: '9~', deux: 'd2',
  trois: 'tRwa', quatre: 'katR', cinq: 'sE~k', six: 'sis', sept: 'sEt',
  huit: 'ɥit', neuf: 'n9f', dix: 'dis', chat: 'Sa', chien: 'SJE~',
  eau: 'o', vie: 'vi', monde: 'mO~d', parole: 'pa.ROl', voix: 'vwa',
  tract: 'tRakt', synthèse: 'sE~.tEz', articulatoire: 'aR.ti.ky.la.twaR',
  bon: 'bO~', jour: 'ZuR', facile: 'fa.sil', pour: 'puR', nous: 'nu',
  les: 'le', des: 'de', une: 'yn', femme: 'fam', homme: 'Om',
  petit: 'p@.ti', grand: 'gRa~', temps: 'ta~', longue: 'lO~g',
  courte: 'kuRt', pause: 'poz', respiration: 'REs.pi.Ra.sjO~',
};

/* Function words used by the demo breath-group chunker (utils/chunking.py). */
export const FUNCTION_WORDS = {
  en: ['the','a','an','of','to','in','is','are','was','and','or','but','for','with','on','at','by','from','that','this','it','as','not','be','have','has','we','you','they','i','he','she','my','your','our','their','us','me','him','her'],
  fr: ['le','la','les','un','une','des','du','de','et','ou','mais','pour','avec','sur','en','dans','par','que','qui','ce','cet','cette','il','elle','nous','vous','je','tu','on','ne','pas','plus','est','sont','a','au','aux'],
};

/* ── Polar targets — demonstrative geometry for DEMO mode ──────────────
 * Vowels inside the unit circle (a 180°, i 300°, u 60° — engine anchors),
 * consonant closures beyond it (ρ 1.0–1.45). Live mode replays the real
 * .polar (format v4) trajectories instead. */
export const POLAR_TARGETS = {
  a:  { rho: 0.75, theta: 180 }, e:  { rho: 0.62, theta: 240 }, i:  { rho: 0.50, theta: 300 },
  E:  { rho: 0.62, theta: 252 }, '@': { rho: 0.58, theta: 220 }, 2: { rho: 0.50, theta: 336 },
  9:  { rho: 0.54, theta: 348 }, o:  { rho: 0.68, theta: 120 },  O:  { rho: 0.76, theta: 100 },
  u:  { rho: 0.50, theta: 60 },  y:  { rho: 0.46, theta: 340 },  6:  { rho: 0.70, theta: 196 },
  h:  { rho: 1.42, theta: 176 },
  p:  { rho: 1.36, theta: 330 }, b: { rho: 1.36, theta: 330 },  m: { rho: 1.28, theta: 330 },
  f:  { rho: 1.22, theta: 345 }, v: { rho: 1.22, theta: 345 },
  T:  { rho: 1.18, theta: 302 }, D: { rho: 1.18, theta: 302 },
  t:  { rho: 1.30, theta: 286 }, d: { rho: 1.30, theta: 286 },  n: { rho: 1.22, theta: 286 },
  s:  { rho: 1.12, theta: 284 }, z: { rho: 1.12, theta: 284 },  l: { rho: 1.04, theta: 278 },
  S:  { rho: 1.14, theta: 262 }, Z: { rho: 1.14, theta: 262 },
  tS: { rho: 1.26, theta: 260 }, dZ:{ rho: 1.26, theta: 260 },  J: { rho: 1.20, theta: 242 },
  j:  { rho: 0.92, theta: 250 }, k: { rho: 1.34, theta: 212 },  g: { rho: 1.34, theta: 212 },
  R:  { rho: 1.28, theta: 196 }, w: { rho: 0.98, theta: 32 },   ɥ: { rho: 0.92, theta: 350 },
};

/* ── Acoustic sketch table (DEMO audio only — formant approximation) ── */
export const ACOUSTICS = {
  a: { f: [800, 1200, 2600], voiced: 1 }, e: { f: [500, 1900, 2550], voiced: 1 },
  i: { f: [300, 2300, 3000], voiced: 1 }, o: { f: [500, 900, 2500], voiced: 1 },
  u: { f: [320, 800, 2450], voiced: 1 },  y: { f: [300, 1750, 2250], voiced: 1 },
  E: { f: [610, 1780, 2600], voiced: 1 }, O: { f: [560, 900, 2500], voiced: 1 },
  '@': { f: [550, 1400, 2500], voiced: 1 }, 2: { f: [320, 1500, 2200], voiced: 1 },
  6: { f: [620, 1250, 2500], voiced: 1 }, 9: { f: [420, 1500, 2250], voiced: 1 },
  p: { stop: 1, place: 'labial', voiced: 0, burst: [900, 1800] },
  b: { stop: 1, place: 'labial', voiced: 1, burst: [800, 1600] },
  t: { stop: 1, place: 'alveolar', voiced: 0, burst: [3500, 5200] },
  d: { stop: 1, place: 'alveolar', voiced: 1, burst: [3200, 4800] },
  k: { stop: 1, place: 'velar', voiced: 0, burst: [1800, 2400] },
  g: { stop: 1, place: 'velar', voiced: 1, burst: [1700, 2300] },
  f: { fric: [1200, 4200], voiced: 0 }, v: { fric: [1100, 4000], voiced: 1 },
  s: { fric: [5000, 8500], voiced: 0 }, z: { fric: [4800, 8000], voiced: 1 },
  S: { fric: [2600, 5200], voiced: 0 }, Z: { fric: [2500, 5000], voiced: 1 },
  T: { fric: [4200, 6800], voiced: 0 }, D: { fric: [4000, 6500], voiced: 1 },
  tS: { affr: [2400, 4600], voiced: 0 }, dZ: { affr: [2300, 4400], voiced: 1 },
  m: { nasal: 1, f: [280, 1100, 2200], voiced: 1 }, n: { nasal: 1, f: [280, 1500, 2500], voiced: 1 },
  J: { nasal: 1, f: [280, 2000, 2700], voiced: 1 }, l: { f: [360, 950, 2600], voiced: 1 },
  R: { f: [420, 1150, 2400], voiced: 1 }, j: { glide: [300, 2200, 2950], voiced: 1 },
  w: { glide: [320, 800, 2400], voiced: 1 }, ɥ: { glide: [310, 1700, 2250], voiced: 1 },
  h: { fric: [800, 3200], voiced: 0 },
};
/* Nasalized vowels: copy of the oral target with a nasal resonance added. */
for (const v of VOWELS) {
  const nasal = v + '~';
  if (!ACOUSTICS[nasal] && ACOUSTICS[v]) {
    ACOUSTICS[nasal] = { ...ACOUSTICS[v], nasal: 1, f: [Math.max(250, ACOUSTICS[v].f[0] - 140), ACOUSTICS[v].f[1], ACOUSTICS[v].f[2]] };
  }
}

/* ── Examples shown as chips under the input textarea ─────────────────
 * One ready-to-run sentence per language of the menu: pickExample sets the
 * language, the input mode and previews immediately (brief §3.2 — the
 * exploration loop must be reachable in one click). */
export const EXAMPLES = [
  { label: 'EN · this is easy for us', text: 'this is easy for us', mode: 'ortho', lang: 'en' },
  { label: 'FR · bonjour, comment allez-vous', text: 'bonjour, comment allez-vous', mode: 'ortho', lang: 'fr' },
  { label: 'ES · buenos días, ¿cómo está usted', text: 'buenos días, ¿cómo está usted', mode: 'ortho', lang: 'es' },
  { label: 'DE · guten morgen, wie geht es dir', text: 'guten morgen, wie geht es dir', mode: 'ortho', lang: 'de' },
  { label: 'IT · buongiorno, come va oggi', text: 'buongiorno, come va oggi', mode: 'ortho', lang: 'it' },
  { label: 'PT · bom dia, como vai você', text: 'bom dia, como vai você', mode: 'ortho', lang: 'pt' },
  { label: 'Phonetic · ba da ga | iowa a g', text: 'ba da ga | iowa a g', mode: 'phonetic', lang: 'en' },
  { label: 'Phonetic · pta.kli.pra', text: 'pta.kli.pra', mode: 'phonetic', lang: 'en' },
  { label: 'Guard demo · cleanpan', text: 'cleanpan', mode: 'phonetic', lang: 'en' },
];

export const KEYBOARD_SHORTCUTS = [
  { keys: ['Space', 'K'], action: 'Play / Pause (outside text fields)' },
  { keys: ['Shift', 'S'], action: 'Stop playback (back to start)' },
  { keys: ['[', ']'], action: 'Previous / next anchor' },
  { keys: ['L'], action: 'Loop the current block' },
  { keys: ['0', '1', '2', '3'], action: 'Speed 0.25× / 0.5× / 1× / 2×' },
  { keys: ['P'], action: 'Preview — G2P + enrichment + guard (never synthesizes)' },
  { keys: ['S'], action: 'Synthesize from the current source' },
  { keys: ['E'], action: 'Synthesize from the edited SAMPA' },
  { keys: ['C'], action: 'Focus the syllable compiler (Enter compiles)' },
  { keys: ['D'], action: 'Downloads menu' },
  { keys: ['R'], action: 'Reset the input — clears both panes and the whole preview chain' },
  { keys: ['Esc'], action: 'Cancel synthesis · stop playback · close help' },
  { keys: ['?'], action: 'Show this shortcut reference' },
];
