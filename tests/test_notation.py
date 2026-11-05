"""Tile-notation tests (covtl-console v3.1).

Each tile is exactly ONE anchor-to-anchor segment, written
FROM · CONSONANTS · TO ("·" is a field separator, not an anchor).
Muted anchors (vowel onset / word end) carry the key of the vowel their
point derives from plus '*' — e.g. "i*" — which disambiguates an
intervocalic onset from a coda before a muted anchor:
  /i.bi/ → "i·b·i"   (real vowels on both sides)
  /ib.bi/ → "i·b·i*" then "i*·b·i"
Background V1V2 arcs keep the arrival vowel in their TO field.

Engine-required: skipped when covtl-pipeline is not importable.
Expected strings were hand-traced against syltraj's anchor walk; if the
engine gives something else, DO NOT adjust silently — dump the
anchors/blocks JSON and report the difference.
"""
import pytest

pytest.importorskip("vtl_synth")

from covtl_console import server  # noqa: E402


def _tiles(seq):
    r = server.compile_blocks(server.CompileRequest(text=seq, lang='en'))
    return [x['notation'] for x in r['segments_preview']]


def test_iba_tiles():
    assert _tiles('iba') == ['▸·i', 'i·b·a', 'a·␣', '␣·◂']


def test_ibbi_muted_anchor_disambiguation():
    assert _tiles('ib.bi') == ['▸·i', 'i·b·i*', 'i*·b·i', 'i·␣', '␣·◂']


def test_ibii_no_muted_anchor():
    """In /i.bi/ the b tile has a real vowel on both sides — no '*'."""
    tiles = _tiles('i.bi')
    assert 'i·b·i' in tiles
    assert not any('*' in t for t in tiles)


def test_ia_vv_tile():
    assert _tiles('ia') == ['▸·i', 'i·a', 'a·␣', '␣·◂']


def test_compile_and_polar_notations_equal():
    """Compile and job-polar payloads give identical notation per segment."""
    seq = 'iba'
    r = server.compile_blocks(server.CompileRequest(text=seq, lang='en'))
    c = [x['notation'] for x in r['segments_preview']]
    p = [x['notation'] for x in r['polar']['segments']]
    assert c == p


def test_segment_chain_contiguity():
    """Every segment's FROM equals the previous segment's TO."""
    for seq in ('iba', 'ib.bi', 'i.bi', 'ia'):
        r = server.compile_blocks(server.CompileRequest(text=seq, lang='en'))
        notations = [x['notation'] for x in r['segments_preview']]
        for prev, cur in zip(notations, notations[1:]):
            frm = cur.split('·')[0]
            to = prev.split('·')[-1]
            assert frm == to, f'{seq!r}: {prev!r} → {cur!r} breaks the chain'


def test_no_ligature_token():
    """'‿' is gone from the notation."""
    for seq in ('iba', 'ib.bi', 'i.bi', 'ia'):
        for t in _tiles(seq):
            assert '‿' not in t, f'{seq!r}: tile {t!r} contains ‿'
