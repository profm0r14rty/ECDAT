# ECDAT — Demo Walkthrough Script

## The Hook (15 seconds)

> "NIST's CNSA 2.0 deadlines are 2030 for key establishment and 2031 for
> digital signatures — every RSA, ECC, and DH artefact in your codebase
> needs to migrate to post-quantum algorithms before then. ECDAT is a
> Cryptography Bill of Materials scanner that discovers these artefacts,
> scores their risk using Mosca's inequality, and recommends the right
> NIST PQC replacements — outputting a real CycloneDX 1.6 CBOM, not a
> proprietary format."

## The Click Path (2 minutes)

### 1. Warm the API (if needed)

Before any demo, hit the health endpoint once to wake the free-tier service:

```
https://ecdat-api.onrender.com/health
```

Wait for `{"status":"ok"}`. The API sleeps after 15 minutes of inactivity and
takes ~60 seconds to wake on the first request. If you skip this step, the
dashboard will show a brief loading state while the backend warms up — it
recovers on its own, but the pause is noticeable.

### 2. Open the Dashboard

```
https://ecdat-web.onrender.com
```

The landing page shows the threat context (2030/2031 CNSA deadlines) and a
feature overview. Click **"Open Dashboard"**.

### 3. Open the Showcase Scan

Open the pre-completed scan directly:

```
https://ecdat-web.onrender.com/app/scans/5b4033fd15e24dfbb599ea8ae593b5b2/overview
```

This is a scan of the
[ecdat-showcase](https://github.com/profm0r14rty/ecdat-showcase) repository —
8 source files across Python, JavaScript, Java, and Go, deliberately seeded
with 12 algorithm families for a rich demo.

### 4. Overview Tab — Point at the Pie Chart First

The numbers:

| Metric | Value |
|--------|-------|
| Total detections | **70** |
| Files scanned | **8** |
| Quantum-vulnerable | **17** (24.3%) |
| Classically broken | **15** |

The risk-distribution pie chart tells the story at a glance: **16 critical, 8
medium, 8 low, 38 quantum-safe**. The critical slice is almost entirely MD5
and SHA-1 — not because of quantum computers, but because those algorithms
are broken *today*.

### 5. The Differentiator Moment — Artefacts Tab, Filter by "Critical"

Open the **Artefacts** tab. Filter by risk level **Critical** (16 results).

**Click on the MD5 detection in `login.py:75`** (hashlib.md5 — password hashing).

Open the detail drawer. Point at:

- **Quantum vulnerable: No** / **Classically broken: Yes**
- Risk level: **Critical**, urgency ratio: **10.5**
- Recommendation: **SHA-256 / SHA-3**

> "This is the key insight most naive scanners miss. MD5 isn't broken by
> quantum computers — it's broken *right now*, by classical attacks. A scanner
> that only looks for 'quantum-vulnerable' algorithms would call this safe.
> ECDAT catches it because it tracks both threat models independently."

**Then click on the RSA detection in `login.py:24`** (RSA.generate — key generation).

- **Quantum vulnerable: Yes** / **Classically broken: No**
- Risk level: **Critical**, urgency ratio: **2.33**
- Recommendation: **ML-KEM (FIPS 203)**

> "RSA-1024 is the opposite: fine today, but broken by Shor's algorithm on a
> future quantum computer. The urgency ratio tells you how soon you need to
> act — migration time plus shelf life divided by the threat horizon."

### 6. Show a Quantum-Safe Artefact

Filter by **Quantum-safe**. Click on **AES-256 in `payment.py:4`**.

- Quantum vulnerable: **No** / Classically broken: **No**
- Risk level: **Quantum-safe**
- Recommendation: **AES-256** (already safe — no migration needed)

> "AES-256 is safe against both classical and quantum attacks. ECDAT
> recommends it as-is — no PQC migration required for symmetric ciphers at
> adequate key sizes."

### 7. CBOM Download — The Closing Beat

Open the **Exports** tab. Click **"Download CBOM (CycloneDX 1.6 JSON)"**.

Open the downloaded file. Show:

- `bomFormat: "CycloneDX"`, `specVersion: "1.6"` — the real standard
- `type: "cryptographic-asset"` on every component
- `cryptoProperties.assetType` in `["algorithm", "certificate", ...]`
- `ecdat:riskLevel`, `ecdat:quantumVulnerable`, `ecdat:classicallyBroken` — our
  extensions live under the `ecdat:` prefix, never as invented top-level fields

> "This isn't a custom format. It's a real CycloneDX 1.6 CBOM — the standard
> the Linux Foundation and OWASP maintain for software bills of materials.
> Your security team, your compliance tooling, your procurement pipeline can
> all consume it as-is."

## Anticipated Questions

### "How is this different from just grepping for RSA?"

Three things:

1. **Mosca's inequality risk scoring** — ECDAT doesn't just find crypto, it
   tells you *how urgent* migration is by computing `(migration_time +
   shelf_life) / threat_horizon`. A deprecated library with 20 years of shelf
   life is a different risk than an RSA key in a short-lived token.

2. **Classically broken vs. quantum-vulnerable** — most scanners either miss
   MD5/SHA-1/DES entirely (they're looking for quantum-vulnerable algorithms)
   or lump them together. ECDAT tracks both threat models independently, so
   you know which artefacts need migration *now* (classically broken) vs.
   which need migration *before 2030* (quantum-vulnerable).

3. **Per-artefact NIST PQC recommendations** — not generic "switch to PQC"
   advice, but specific FIPS 203/204/205 algorithm recommendations with
   migration notes and latency expectations, matched to each artefact's
   algorithm family.

### "What about the risk override feature?"

In the Artefacts tab, click any detection and adjust `shelf_life_years` or
`migration_time_years`. The Mosca urgency ratio recomputes in real time and
the risk level updates immediately. This lets a security team inject their
own institutional knowledge — "this RSA token is used in a short-lived
session, shelf life is 6 months, not 5 years" — and see the priority shift.

### "Does this work on real codebases, not just demo data?"

Yes — ECDAT scans any Git repository via URL or local path. The showcase scan
was cloned from GitHub and scanned in ~3 seconds. It covers Python,
JavaScript, Java, Go, and C/C++ with regex-based detection across the two
dominant crypto libraries in each language (e.g. `cryptography` hazmat and
PyCryptodome for Python).

### "Is the CBOM compatible with existing tooling?"

Yes. It's CycloneDX 1.6 — the OWASP/Linux Foundation standard for SBOMs.
Toolchains like Dependency-Track, Syft, Grype, and Sigstore can parse it.
The quantum-risk extensions (`ecdat:*`) live under the standard `properties`
array, so they don't break parsers that don't recognise them.
