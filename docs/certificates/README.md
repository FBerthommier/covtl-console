# Conformity certificates — covtl-console

Certificates deposited in this folder are the conformity records of the
independent comparative audit *big.bi / COVTL* covering the three sources of
this project: the scientific article (arXiv:2307.02299), the engine
(covtl-pipeline), and this console.

| Reference | Object | Result |
|---|---|---|
| [COVCONF-3SRC-3706f0c0](COVCONF-3SRC-3706f0c0.md) · [PDF](COVCONF-3SRC-3706f0c0.pdf) | Three-source comparison: the complete audit chain re-executed at the frozen versions of the three sources | 37/37 checks conform (2026-10-29) |
| COVCONF-D11-511cf2e | D-11 remediation — report, evidence bundle, and fix commit cross-source consistency | 31 checks, 0 divergent (2026-10-29) — issued by the certifier; file to be deposited when received |
| [Polar_Display_Equivalence_Certificate](Polar_Display_Equivalence_Certificate.pdf) | Equivalence attestation of the polar display: covtl-console (HTML) vs covtl-pipeline (reference polar plot) — parameter ν, its arc concavities, and absence of any inversion; code audit of the three repositories plus numerical simulations over six phrases, following the problem documented in big.bi-supplement | Equivalence attested: ν respected, zero inversion — max deviation 1.1×10⁻⁴ cm, concavities 100% identical, negative flip-ν control inverts 100% of the bows (2026-11-15) |

Both certificates are mutually consistent (cross-certificate coherence checks
C21–C24 of COVCONF-3SRC-3706f0c0). The machine verification record
(`covconf-3src-verification.json`) accompanies the issued documents.
