# Certificate of Conformity COVCONF-3SRC-3706f0c0

Three-source comparison audit — arXiv:2307.02299 · covtl-pipeline · covtl-console.
Issued 2026-10-29. Formal PDF edition: [COVCONF-3SRC-3706f0c0.pdf](COVCONF-3SRC-3706f0c0.pdf).

*Repository edition note: this edition replaces the ceremonial cover of the
issued PDF with a plain header; the certified content below is unchanged.*

| Field | Value |
|---|---|
| **Reference** | COVCONF-3SRC-3706f0c0 |
| **Date of issue** | 2026-10-29 |
| **Object** | Conformity of the three-source comparison executed by the independent audit — scientific article *arXiv:2307.02299*, engine **covtl-pipeline**, console **covtl-console** — by re-execution of the complete audit chain at the frozen versions |
| **Issued by** | Independent comparative audit *big.bi / COVTL* (audit report V1.0 / V1.0-EN / V1.1-EN) |
| **Depository** | covtl-console documentation (`docs/certificates/`, console @ `3706f0c0` or later) |
| **Relation** | Completes and complements certificate **COVCONF-D11-511cf2e** (D-11 remediation) |
| **Result** | **CONFORMITY ESTABLISHED** — 37 verification checks, all CONFORM, 0 divergent; one verification-history note (N1, Section 7) |

---

## 1. Purpose, Scope, and Self-Containment

This certificate establishes the conformity of the **three-source comparison** that constitutes the scientific core of the independent audit *big.bi / COVTL*. Its predecessor, COVCONF-D11-511cf2e, certified the cross-source consistency of the **remediation** of registry divergence D-11 — the report, the evidence bundle, and the fix commit. The present certificate closes the remaining half of the chain: it certifies that the **comparison itself** — article versus reference implementation versus engine versus console — is reproducible and internally consistent, and that every measured divergence it records is either quantified within its documented bound or, in the single error case D-11, corrected and attested.

The comparison certified here rests on three sources, with a fourth object serving as the executable form of the first. The **scientific reference** is the article *arXiv:2307.02299v1* (2023-07-05), which defines the big.bi syllable model: a gestural account of syllable structure in which vowel and consonant targets are represented as anchor points in a **polar formant plane** — each target is the pair (ρ, θ), radius and angle, in articulatory units calibrated on the Maeda/VocalTractLab parameterization. The **reference implementation** is `synthSYL`, the Python package of the repository *big.bi-supplement* that implements the article's equations and anchors; the audit treats it as the executable form of the article. The **engine** is *covtl-pipeline*, whose module `vtl_synth/core/syltraj.py` implements the same model for production synthesis, with documented implementation choices of its own. The **console** is *covtl-console*, a JavaScript application that consumes engine data and renders polar trajectories and spectrograms; it is the reference consumer of the engine's output and the documentation hub of the COVTL family, which is why this certificate is deposited in its documentation.

The certificate is **self-contained by design**: the audit report PDF is *not* part of the deposit, so every quantity, bound, identifier, and technical term used below is defined and valued inline, and can be recomputed from the reproduction commands of Annex A together with the machine record `covconf-3src-verification.json` delivered alongside this document. Readers need no other document to verify or to cite the certified results.

## 2. Certified Objects and Frozen Versions

Every conformity statement in this certificate refers to the following exact objects, frozen to the commit and, where a file is cited, to the byte.

| Object | Role | Exact identification |
|---|---|---|
| **O1** — Scientific article | Normative reference of the model | arXiv:2307.02299v1, submitted 2023-07-05 |
| **O2** — Reference implementation | Executable form of O1 | *big.bi-supplement* @ `c83ace3a261792889ccb880e03c64dd796ab2df4` — package `synthSYL` |
| **O3** — Engine (audited baseline) | Implementation under audit | *covtl-pipeline* @ `48442aa904315d1d8452531da91a14a19c68afd6` |
| **O3′** — Engine (remediated) | Baseline + D-11 fix | *covtl-pipeline* @ `511cf2ed62d1a11aa3876c172bda2b3d6494d351` (branch `main`, 2026-10-29) |
| **O4** — Console | Reference consumer; depository of this certificate | *covtl-console* @ `3706f0c0dbc8cc07b1309954ba172f4c49535e38` |

**Attestation basis for O3′.** The certification environment holds the audited baseline O3 as the local *covtl-pipeline* clone; the fix commit O3′ is attested by the evidence bundle `d11_fix_evidence_511cf2e.json` (SHA-256 in Annex B) and by audit report V1.1-EN — the same attestation basis already accepted by the predecessor certificate COVCONF-D11-511cf2e, whose own verification record is cross-checked in Section 6 (checks C21–C24). All D-11-dependent values in this certificate are recomputed from that evidence bundle and from the frozen audit data, not merely restated.

## 3. Terminology Used by the Comparison

For self-containment, the audit's working vocabulary is summarized here. The **corpus** is the 107 structural sequences of the big.bi notation (e.g. `big.bi → bi.gbi`, `ib ib → bi bi`, `bi |`, `bi | ba`), covering simple and polymorphemic syllable structures (CV, CVC, CCV, CV.CV, VC.CV, sequences with the word boundary " |"). **Anchor points** are the (ρ, θ) targets from which trajectories are built; the audit distinguishes the roles *terminal* (phrase start/end), *base_V* (base vowel of a syllable), *vo_word* / *ve_word* (vowel onset/offset anchors at word level), *vo_syl* (syllable-level vowel onset), and *pause*. A **block schedule** is the sequence of per-gesture step counts that determines the timing of a phrase. The **divergence registry** is the audit's catalogue of 17 quantified differences D-01…D-17 between the reference implementation and the engine, each classified either as a documented model difference (parameter choice, convention, selection rule) or as a probable software error. **D-11** is the unique error-class entry: at a *double pause* — the GAP + PAUSE construct produced by the engine's own segmentation of the " |" notation in direct engine calls — `syltraj` overwrote the pending anchor point, so the terminal pause arc departed from the neutral [0, 0] instead of the preceding vowel, producing a discontinuity of 0.908 units on the Hy articulatory parameter at the decay-to-terminal junction of `bi |`.

## 4. Method of Certification

The certificate was produced by a certifier program (`scripts/covconf3_verify.py`, re-issued with this certificate) executing six phases, whose full machine record is `covconf-3src-verification.json`:

1. **Freeze.** SHA-256 of the 21 delivered artifacts backing the certificate (the 16 data files of the audit bundle, the corrected report V1.1-EN in PDF and LaTeX, the D-11 evidence bundle, and the two predecessor-certificate files) is recorded before anything is touched.
2. **Backup.** The delivered audit bundle — data, figures, and working artifacts — is copied to a quarantine directory.
3. **Re-execution.** The complete audit chain is re-executed at the frozen versions of O2, O3, O4: `run_audit.py` (corpus → oracle → anchors → aggregate metrics), `inventory.py` (engine inventories and reference geometry), `experiments.py` (the five sensitivity experiments E1–E5), `figures.py` (the ten figures), `tables_registry.py` (tables A–G and the registry), `console_audit.py` (console display reversibility and conventions), then the audit's 30-test non-regression suite.
4. **Diff.** Every regenerated artifact is compared with the delivered one — byte-level comparison throughout, except `runs_complete.json`, compared semantically with the single volatile field `meta.duration_s` (wall-clock duration of the original run) stripped.
5. **Restore.** The delivered bundle is restored **byte-for-byte** from the quarantine copy, and the restoration is verified against the frozen digests of phase 1. The re-execution is evidence; the delivered record is never replaced by it.
6. **Checks.** Thirty-seven conformity checks are recomputed from the frozen data and evidence: R01–R13 (re-execution reproduction) and C01–C24 (arithmetic, identity, registry, commit, and cross-certificate coherence).

## 5. Re-Execution Conformity (R01–R13)

The re-executed chain reproduces the delivered audit record completely. All seven programs exited 0; the non-regression suite passed 30/30 at the frozen baseline — including the D-11 discontinuity pin test, which *asserts* the 0.908 jump because the audited baseline O3 still contains the defect; this is the expected state, and the post-fix expectation flip is attested by the evidence bundle (Section 6, checks C12–C14).

| Id | Verified reproduction | Method | Verdict |
|---|---|---|---|
| R01 | `runs_complete.json` (1.5 MB run record, 107 sequences) | semantic (volatile `meta.duration_s` stripped) | CONFORM — identical |
| R02 | `data/summary_stats.json` | byte | CONFORM — identical |
| R03 | `data/anchors_all.csv` (all anchor pairs, both engines) | byte | CONFORM — identical |
| R04 | `work/experiments.json` (working copy of E1–E5) | byte | CONFORM — identical (history note N1, Section 7) |
| R05 | `work/continuity_stats.json` | byte | CONFORM — identical |
| R06 | `work/console_audit.json` | byte | CONFORM — identical |
| R07 | `data/registre_divergences.csv` | byte | CONFORM — identical |
| R08 | `data/registre_divergences.json` | byte | CONFORM — identical |
| R09 | Tables A–G (7 CSV: inventory, anchor correspondence, numeric errors, per-structure, documented divergences, evidence status, reproducibility) | byte | CONFORM — identical |
| R10 | The 10 figures (PNG) | byte | CONFORM — all 10 identical |
| R11 | Delivered bundle restored byte-for-byte after re-execution | digest | CONFORM — identical |
| R12 | All re-executed audit programs exited 0 | exit codes | CONFORM |
| R13 | Audit non-regression suite at the frozen baseline | pytest | CONFORM — 30 passed |

## 6. Conformity Checks (C01–C24)

### 6.1 Equations and structures (C01–C03)

**C01 — machine precision, reference side.** Over the 107-sequence corpus, `synthSYL` reproduces the article's block and anchor equations with a maximum deviation of **8.88 × 10⁻¹⁶** — the IEEE-754 double-precision rounding floor (the next representable value above 0) — against a tolerance of 10⁻⁹. The reference implementation is thus arithmetically faithful to the article it implements. **C02 — machine precision, engine side.** The engine's `syltraj` reproduces *its own* documented scheme — K = 1000 arc discretization, cos² velocity profile, scoped endpoints — with the same maximum deviation of 8.88 × 10⁻¹⁶. The scheme itself differs from the article's (K = 10/30, half-cosine profile); that difference is a *documented model divergence* (registry D-08, D-09), not an arithmetic defect: what C02 certifies is that the engine computes exactly what it documents. **C03 — structural identity.** Of the 106 corpus sequences run through both engines, **98 have byte-identical anchor structures** (same kinds, roles, and order); the 8 divergences are the structural consequences of three documented model differences — schwa insertion for vowelless words (D-13), the three-consonant cap with its schwa boundary point (D-14), and the double-pause segmentation (D-12).

### 6.2 Anchor-level bounds (C04–C07)

| Id | Verified claim | Measured | Bound / expectation | Verdict |
|---|---|---|---|---|
| C04 | Vowel anchor angles identical between engines (`base_V`) | Δθ max = 0 | 0 | CONFORM |
| C05 | `base_V` radius deviation equals the documented calibration bound (D-03: reference 0.9 / 0.8 / 1.0 vs engine 0.60 / 1.00 / 0.55 for /i a u/) | 0.45 | ≤ 0.45 | CONFORM |
| C06 | `vo_word` radius deviation within the frozen-Vo bound (D-05: engine freezes [0.5, θ_V] where the article uses δ_o·ρ_V) | 0.40 | ≤ 0.40 | CONFORM |
| C07 | The only angular deviation is 2π/3, on vowelless words (D-13: the engines choose different fallback vowels) | 2.0943951 = 2π/3 | 2π/3, explained | CONFORM |

These four checks certify the audit's central quantitative finding: every anchor-level divergence between the reference implementation and the engine is *bounded and explained* — angular conformity is exact wherever the article defines the target, and radial deviations are exactly the documented calibration choices of the engine, never unexplained drift.

### 6.3 Console fidelity (C08–C11)

The console was audited on four reference sequences (`big.bi`, `bi ba`, `idi` at t = 16/16, `big.bi` at t = 10/8; 126–188 steps). Its display transformations are **reversible**: the polar trajectory shown on screen, passed back through the display convention, recovers the engine values to within the documented rounding bounds. The console's angular convention is the *documented mirror* of the engine's — the engine uses the trigonometric convention (θ = 0 East, counter-clockwise), the screen shows θ = 0 up and clockwise, conversion θ_disp = (90 − θ) mod 360 — and its radial normalization is the documented constant ρ_max = 1.45, the VTL-calibrated inventory ceiling.

| Id | Verified claim | Measured | Bound / expectation | Verdict |
|---|---|---|---|---|
| C08 | Display transformations reversible — angular | 0.004952° max | ≤ 0.005° (documented rounding) | CONFORM |
| C09 | Display transformations reversible — radial | 7.19 × 10⁻⁵ max | ≤ 1.45 × 10⁻⁴ (= 10⁻⁴ × ρ_max) | CONFORM |
| C10 | Angular convention is the documented mirror (θ = 0 → up; θ = 90° → right; clockwise) | verified on rendered coordinates | mirror of engine convention | CONFORM |
| C11 | Radial normalization documented and constant | ρ_max = 1.45 on all audited sequences | 1.45 | CONFORM |

### 6.4 D-11 remediation evidence (C12–C16)

These checks recompute, from the evidence bundle and the frozen audit data, the values that the remediation claimed for itself.

| Id | Verified claim | Measured | Expectation | Verdict |
|---|---|---|---|---|
| C12 | Pre-fix discontinuity at the audited baseline equals the registry value | 0.9082 (Hy units) | 0.9082 = corpus boundary max of `continuity_stats.json` | CONFORM |
| C13 | Post-fix jump, `bi \|` | 0.1062 | ≤ 0.3086 (corpus in-block maximum class) < 0.5 (flipped test bound) | CONFORM |
| C14 | Post-fix jump, `bi \| ba` | 0.1137 | ≤ 0.3086 | CONFORM |
| C15 | Terminal pause arc departs from the preceding vowel | [0.6, 5π/3] = `VOWEL_TARGETS['i']` | restores the article's pause-diphthong V<sub>e</sub> → V<sub>o</sub> semantics | CONFORM |
| C16 | Block schedule preserved by the fix (no timing side effect) | [20, 32, 16, 16, 32], pre = post | identical | CONFORM |

The remediation is thereby shown to be *surgical*: the defect signature (0.908) collapses into the corpus's normal in-block continuity class, the pause arc recovers exactly the departure point required by the article's pause-diphthong semantics, and the block schedule — the timing of every gesture in the phrase — is untouched. One additional notation outside the corpus is documented by the evidence bundle (`ba da ga | iowa a g`, where a space before " |" also produces the GAP+PAUSE construct): departure-only change, schedule preserved (556 steps), maximum |Δ| 1.2167 — consistent with the same semantics restoration.

### 6.5 Identity, registry, and cross-certificate coherence (C17–C24)

**C17 — commit identities.** The fix commit is the 40-hex `511cf2ed62d1a11aa3876c172bda2b3d6494d351` (prefix consistent with the cited short form `511cf2e`), and the audited baseline `48442aa9…` equals the local engine clone's HEAD — the clone is the baseline the audit ran on. **C18 — affected set.** The corpus entries modified by the fix are exactly the two " |"-notation sequences `bi |` and `bi | ba`; the evidence bundle measures 90/92 corpus notations byte-identical after the fix. **C19 — registry integrity.** The divergence registry holds 17 entries, D-01 through D-17, every one quantified, with exactly one entry in the probable-software-error class — D-11 — now fixed at `511cf2e`. **C20 — frozen versions.** The three audited repositories were verified live at the exact commits of Section 2 during certification. **C21–C23 — cross-certificate coherence.** The corrected report V1.1-EN and the evidence bundle are byte-identical to the copies annexed to the predecessor certificate COVCONF-D11-511cf2e (SHA-256 in Annex B), and the report compiles to 17 pages with no undefined references. **C24 — predecessor verdict.** COVCONF-D11-511cf2e's own machine record shows 31 checks — 27 conform, 4 conform with non-blocking note, 0 divergent — so the two certificates are mutually consistent and rest on the same byte-verified evidence.

## 7. Verification History and Reconciliation Note N1

For completeness of the audit trail, this section documents the single anomaly encountered during certification. The *first* execution of the certifier flagged check R04 as DIVERGENT: the working copy `work/experiments.json` did not match, byte for byte, the copy regenerated by the re-executed chain. Investigation established three facts. **First**, the delivered bundle was never implicated: a pre-flight digest verification confirmed all 21 backing artifacts (Section 2 and Annex B) byte-intact throughout, and the delivered `data/experiments.json` — the exported form — was byte-identical at every pass. **Second**, the flagged difference concerned only the *volatile working copy* in the `work/` scratch directory, which held a stale intermediate predating the final delivered state rather than the canonical chain output. **Third**, the canonical content is fully reproducible: re-running the complete chain in certifier order reproduces the working copy byte-for-byte (semantic difference: zero fields), which was confirmed again immediately before the final certification pass.

The certifier was then executed a second time with the working directory in its canonical state; the refreshed machine record reports **37 checks, 37 conform, 0 divergent**, with all 21 backing-artifact digests unchanged across the refresh (zero drift). The delivered bundle was restored and verified byte-for-byte after every pass. Note N1 therefore concerns verification *process hygiene* — the provenance of a scratch artifact — and not any certified object, measurement, or conclusion; it is recorded here so that the certificate's own history is as auditable as the software it certifies.

## 8. Test Conformity Summary

| Stratum | Suite | Result at certification | Status |
|---|---|---|---|
| (a) Audit non-regression suite (frozen with the audit) | 30 tests incl. the D-11 discontinuity pin asserting the 0.908 jump | **30/30 passed** at the audited baseline — the pin passes *because* the baseline contains the defect, as expected | CONFORM |
| (b) Engine tests added by the D-11 fix (`tests/test_syltraj_double_pause.py`) | 5 tests: pending-point preservation, continuity, pause arity unchanged, single-pause paths unchanged (×2) | **5/5 passed** (attested by the evidence bundle) | CONFORM |
| (c) Audit suite at the remediated engine | same 30 tests, one documented flipped expectation (`test_covtl_double_pause_fixed_continuity`, bound < 0.5; measured 0.1062) | 30 passed | CONFORM |
| (d) Engine repository suite | full covtl-pipeline test suite | 210 passed, 1 failed — pre-existing and unrelated (speaker-registry hash test, verified failing on the base engine), out of scope | CONFORM (noted) |

The **pin-then-flip** structure visible across strata (a) and (c) is itself a conformity signal: the pre-fix suite pinned the defect by asserting its exact signature, the fix flipped exactly that one expectation, and every other invariant held — demonstrating that the remediation changed precisely the behavior it claimed to change and nothing else.

## 9. Console Impact and Deposit Statement

The console **covtl-console** (frozen at `3706f0c0` in the audit) is modified neither by the D-11 remediation nor by this certificate, and no console change is required. The audit established that the console's nominal path — the server splits phrases on " |" before invoking the engine — never constructs the GAP+PAUSE double pause that triggered D-11, so no console display, transformation, or synchronization was ever affected by the defect. The console's own fidelity findings (reversibility within 0.005° and 1.45 × 10⁻⁴; documented mirror convention; constant ρ_max = 1.45) are certified conforming in Section 6.3. What the remediation restores is conformity for **direct engine invocations** — scripts, API calls, `polar_video`, and any future console feature that may pass " |" notations through to the engine — which now inherit the corrected pause-diphthong semantics.

**Deposit.** This certificate is deposited in the covtl-console documentation as the conformity record of the three-source comparison underlying its data source. Placement and integration:

- Files: `docs/certificates/COVCONF-3SRC-3706f0c0.md` (this document), the formal PDF edition `COVCONF-3SRC-3706f0c0.pdf`, and the machine record `covconf-3src-verification.json`; the predecessor certificate COVCONF-D11-511cf2e (`.md`, `.pdf`, and its machine record) is deposited alongside so that all cross-references resolve within the repository.
- Documentation pointer (console README): *"Three-source conformity certificate COVCONF-3SRC-3706f0c0 — re-executed audit chain (arXiv:2307.02299 / covtl-pipeline / covtl-console), 37/37 checks conform (2026-10-29); complements COVCONF-D11-511cf2e."*
- Suggested commit message: `docs(console): deposit conformity certificates COVCONF-3SRC-3706f0c0 and COVCONF-D11-511cf2e (37/37 + 31/31 checks conform)`.

## 10. Validity, Limitations, Verdict, and Sign-Off

**Validity.** This certificate is bound to the exact byte content of the artifacts whose SHA-256 digests are recorded in Annex B and to the commit identifiers of Section 2. Any subsequent modification of any certified object invalidates this certificate with respect to that object; a revised certificate must then be issued.

**Limitations.** (1) The re-execution ran in the certifier's environment, on the frozen commits, with the frozen audit harness; portability to a different environment is supported — not proven — by the byte-level reproduction reported in Section 5. (2) The D-11 fix commit `511cf2e` is attested through the evidence bundle and the corrected report V1.1-EN rather than present in the local engine clone, which remains at the audited baseline `48442aa9`; this is the same attestation basis accepted by the predecessor certificate, whose byte-identity is verified here (checks C21–C24). (3) The verification-history note N1 is part of the record and does not alter any measurement or conclusion.

**Verdict.** On the basis of the re-execution conformity (Section 5, R01–R13), the conformity checks (Section 6, C01–C24), and the test conformity summary (Section 8): **CONFORMITY ESTABLISHED** — the three-source comparison is reproducible byte-for-byte at the frozen versions, and every cross-source divergence it records is quantified within its documented bound, explained, or corrected and attested.

| Sign-off | |
|---|---|
| **Reference** | COVCONF-3SRC-3706f0c0 |
| **Object** | Three-source comparison audit — arXiv:2307.02299 / covtl-pipeline / covtl-console |
| **Issued by** | Independent comparative audit *big.bi / COVTL* — audit report V1.0 (FR) / V1.0-EN / V1.1-EN |
| **Date** | 2026-10-29 |
| **Depository** | covtl-console documentation (@ `3706f0c0` or later) |
| **Result** | **CONFORMITY ESTABLISHED** (37 checks: 37 conform, 0 divergent; note N1 recorded) |
| **Complements** | COVCONF-D11-511cf2e (2026-10-29): 31 checks, 0 divergent |

---

## Annex A — Reproduction Commands

```bash
# 0. Frozen working copies (see Section 2 for the exact commits)
#    big.bi-supplement @ c83ace3a ; covtl-pipeline @ 48442aa9 ; covtl-console @ 3706f0c0

# 1. Verify the byte content of the backing artifacts (digests in Annex B)
sha256sum download/bigbi-audit/data/*.csv download/bigbi-audit/data/*.json \
          upload/d11_fix_evidence_511cf2e.json

# 2. Re-execute the audit chain at the frozen commits (each exits 0)
python3 scripts/audit/run_audit.py        # corpus -> oracle -> anchors -> metrics
python3 scripts/audit/inventory.py        # inventories + reference geometry
python3 scripts/audit/experiments.py      # E1-E5 sensitivity experiments
python3 scripts/audit/figures.py          # the ten figures
python3 scripts/audit/tables_registry.py  # tables A-G + divergence registry
python3 scripts/audit/console_audit.py    # console reversibility + conventions
python3 -m pytest scripts/audit/tests_non_regression.py -q   # 30 passed

# 3. Re-run the certifier (six phases, Section 4) -> machine record
python3 scripts/covconf3_verify.py       # 37 checks, 37 conform, 0 divergent
```

## Annex B — SHA-256 of the Backing Artifacts

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `data/anchors_all.csv` | 78,467 | `0931a51953be550800499aeecb6682e38e2842a07f8350f23dca6f5d3e486987` |
| `data/console_audit.json` | 3,336 | `767cc93151ecb6ff9ba2423a05b5b06d87c7f3e85412aec9d91157881ed98d3c` |
| `data/continuity_stats.json` | 314 | `1c7291e1a6d1ce4cceb5cb77862d847af80ef0b7ccbf42d1bfcca2fe063f8650` |
| `data/experiments.json` | 35,071 | `76af735c3cb60565f57510ce6c07e9ee7ac257ebb34701f1755ee010b3250859` |
| `data/inventories.json` | 12,086 | `157f6c13e2858cf8d44747c8252c9bf43bd1c37891dfad82779bab71841920b7` |
| `data/registre_divergences.csv` | 5,395 | `2ca5827b16ce07411c27dc98f2a83966d25fd8f3bb7fc43a90f4476f7c97a465` |
| `data/registre_divergences.json` | 10,302 | `758077951fc1132f6ceff69e0175f9f95d4e7e89fca78e1c3dcc2bf72bc8ea34` |
| `data/runs_complete.json` | 1,500,824 | `4145f799b537b38987bb68d037678056af691ad09126cc513767a6a27d089f9a` |
| `data/summary_stats.json` | 1,105 | `4e749435b5d579f45cf2e9a8a665cb36b4f89fc5adf7496dc766c6ea4807aaf9` |
| `data/tableau_A_inventaire.csv` | 1,052 | `21dfeff510d8e4277d76b4178caf173e9d3b0a64836e271065f74a24d30d7356` |
| `data/tableau_B_correspondance_ancres.csv` | 469 | `db77f47962c19b1af61722820008d1485cc33efb2a67d477f46951d1a113d64a` |
| `data/tableau_C_erreurs_numeriques.csv` | 883 | `76d14aed7cb7a569f7ee256bec526e70637c5570d79ea9102afd5bc135f864e3` |
| `data/tableau_D_par_structure.csv` | 289 | `f9c78fb1c05addca521a5580588a96cfa3027051d6ef4268058533d06a7da11d` |
| `data/tableau_E_divergences_documentees.csv` | 1,408 | `5545610e7b4ff631238295b683d35137234c19768f1e71e462490c31ba3de176` |
| `data/tableau_F_etat_preuves.csv` | 2,065 | `f62c22510c1281813330eaff3d560217e6da4f75dd9acf8a7e59628c2519a24b` |
| `data/tableau_G_reproducibilite.csv` | 1,145 | `071218e727ff9bdcfcd7787ca57612c26103a399eedaf22d2527cb8f339eefe1` |
| `upload/d11_fix_evidence_511cf2e.json` | 3,636 | `34b25c4aaa36b54cb8c271dbcb172586a689a4aa0c192cc33d74761adb446363` |
| `upload/audit_report_bigbi_covtl_en_FIXED_511cf2e.pdf` | 2,356,675 | `1956e45336870c9aeda2f6ca0d8d4246b3b4c30d7cd1aa14461cdd91091fb549` |
| `upload/audit_report_bigbi_covtl_en_FIXED_511cf2e.tex` | 65,185 | `9a4229175b62f622c6c8d3bc72b2839deab8de245fa8a46a0649590f0242448f` |
| `download/covconf-d11-511cf2e/COVCONF-D11-511cf2e.pdf` | 231,264 | `aca3ed9d261a56067a04903c29eaa22d166b97f1ceb2b35ffc8a74695dfaa3b9` |
| `download/covconf-d11-511cf2e/covconf-d11-verification.json` | 7,551 | `be475b6200cc8a2b21b47e5de1b1d8e079fb10f0e7adbfe4b1537eef7336e2b9` |

*Artifacts are named relative to the audit workspace root (`download/bigbi-audit/`) or the project root (`upload/`, `download/covconf-d11-511cf2e/`), matching the paths recorded in the machine record.*

**Commit identifiers.** Paper: arXiv:2307.02299v1 (2023-07-05). Reference implementation: big.bi-supplement @ `c83ace3a`. Engine audited baseline: `48442aa904315d1d8452531da91a14a19c68afd6` (`48442aa9`). Engine remediated: `511cf2ed62d1a11aa3876c172bda2b3d6494d351` (`511cf2e`, branch `main`, 2026-10-29). Console (depository): `3706f0c0dbc8cc07b1309954ba172f4c49535e38` (`3706f0c0`).

**Cross-references.** COVCONF-D11-511cf2e (2026-10-29) — D-11 remediation certificate, 31 checks, 0 divergent; evidence bundle — `d11_fix_evidence_511cf2e.json`; engine module — `vtl_synth/core/syltraj.py` @ covtl-pipeline; certifier — `scripts/covconf3_verify.py`; machine record — `covconf-3src-verification.json` (delivered with this certificate).
