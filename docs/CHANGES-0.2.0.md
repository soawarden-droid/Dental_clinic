# Version 0.2.0 — 29 October 2026

- Registration needs only name and phone. Optional fields stay NULL, Afghan numbers normalize, and confirmed family numbers can be shared. Additional information starts collapsed.
- Versioned migrations preserve IDs, legacy records, relationships, documents and financial history. Existing missing phones do not block unrelated clinical updates.
- Shared ivory/blush/rose/lilac/mint and dark plum themes, bundled Dari UI fonts, original sidebar icons, rounded cards and saved appointment status badges.
- Dashboard with saved-record summaries, 7/30/90-day net collection trends, completed-treatment distribution, appointment status breakdown and record drilldowns. Empty states and reduced motion are supported.
- Separate patient overview, visit history, dental chart, billing, photos/documents and prescription tabs, with section editing.
- Add/Replace/Remove/Preview/Restore image controls, reference-aware managed-copy cleanup, restart persistence and background opacity.
- Null-safe printable documents, bundled default logo, matching print colours and corrected Latin phone direction in Dari receipts.
- Ubuntu 24.04 amd64 package rebuilt. Windows installer/workflow updated; Windows execution remains unverified.

See VERIFICATION.md, test-results.txt and BUILD_MANIFEST.json for evidence and limitations. Records remain in the user's separate application-data directory; back up before upgrading a real clinic installation.
