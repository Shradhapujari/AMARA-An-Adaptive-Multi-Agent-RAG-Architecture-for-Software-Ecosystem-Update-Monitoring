# Grounding: before and after

Live pool, 2026-09-01. `before` is the question sent to `/api/v/` as typed; `after` is the same pool retrieved through `grounding.ground`, vendor-filtered, and record-type filtered when the question is not a security question.

## What is the latest Linux version?

*answered with an NVD affected-version string instead of a kernel release*

- rewritten: `What is the latest Linux kernel version on Sep 1, 2026 (2026-09-01)?`
- vendors: `['linux']` · intent: `release` · citable: `release, community`
- **before** (0 rows): — nothing retrieved —
- **after** (157 rows, 449 advisories excluded): linux v7.1.0 (20260719) [release] https://github.com/torvalds/linux

## Any critical Linux updates today?

*answered with advisories only; no shipped release was distinguished*

- rewritten: `Any critical Linux kernel updates on Sep 1, 2026 (2026-09-01)?`
- vendors: `['linux']` · intent: `security` · citable: `cve, release, community`
- **before** (0 rows): — nothing retrieved —
- **after** (606 rows): CVE-2026-80688 (affects Linux 25.642087.0) (20260828) [advisory] https://nvd.nist.gov/vuln/detail/CVE-2026-80688

## What bugs were fixed in Chrome recently?

*sentence-shaped query returns zero release rows*

- rewritten: `What bugs were fixed in Google Chrome between Aug 25, 2026 and Sep 1, 2026 (2026-08-25 to 2026-09-01)?`
- vendors: `['chrome']` · intent: `release` · citable: `release, community`
- **before** (0 rows): — nothing retrieved —
- **after** (559 rows, 22 advisories excluded): Chrome v154.0.8029 (20260828) [release] 

## Any security vulnerabilities in Python?

*advisories are the right pool here — the grounded path should agree*

- rewritten: `Any security vulnerabilities in Python?`
- vendors: `['python']` · intent: `security` · citable: `cve, release, community`
- **before** (0 rows): — nothing retrieved —
- **after** (23 rows): CVE-2026-66003 (affects Python 15.115.0) (20260826) [advisory] https://nvd.nist.gov/vuln/detail/CVE-2026-66003
