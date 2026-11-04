// SPDX-FileCopyrightText: 2026 Frédéric Berthommier
// SPDX-License-Identifier: GPL-3.0-or-later
/* data.js — engine constants mirrored from covtl-pipeline (vtl_synth v1.1.0)
 * Source of truth: vtl_synth/core/constants.py, utils/setlang.py,
 * core/speaker_registry.py, core/sampa_guard.py. In LIVE mode these tables
 * are refreshed from GET /api/status; they are duplicated here only so the
 * console can lay out controls before the
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
 * from the engine (live). These hints just help
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

/* Enrich raw {symbol, position} pairs to the same shape the
 * live bridge returns: reason + suggestions on every rejected symbol. */
export function enrichRejected(rejected) {
  return rejected.map((r) => ({ ...r, reason: REJECT_REASON, suggestions: suggestFor(r.symbol) }));
}

export function isSampaToken(word) {
  // Mirrors phonemes.is_sampa_token: every symbol of the word must be
  // in the inventory (markers not allowed inside a bare word).
  return word.length > 0 && [...word].every((c) => INVENTORY_KEYS.has(c));
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
  { label: 'Guard · cleanpan', text: 'cleanpan', mode: 'phonetic', lang: 'en' },
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
  { keys: ['R'], action: 'Reset the input — clears both panes, the preview chain, the compiler panel and the synthesis results' },
  { keys: ['Esc'], action: 'Cancel synthesis · stop playback · close help' },
  { keys: ['?'], action: 'Show this shortcut reference' },
];
