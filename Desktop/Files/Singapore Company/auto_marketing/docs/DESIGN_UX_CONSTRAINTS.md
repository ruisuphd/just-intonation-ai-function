# Design and UI/UX Constraints

This document defines the non‑negotiable design and UI/UX constraints for AutoMark. All frontend work for F1, F3, F4, F9, F10, and F7 must comply.

## Constraint (Non-Negotiable)

**Do not change the existing UI/UX style or design.** The product must keep its current **Apple.com-style** look and feel: **minimalist** and **extremely user-friendly**.

Any UI work may **only**:

- Add or adjust elements **to support new features** (e.g. Connect LinkedIn/X, Enrich lead, newsletter schedule).
- Improve **clarity and maturity** of existing flows (copy, feedback, loading states) without altering the visual language.

**Do not**:

- Introduce new design systems, colour palettes, or typography that conflict with the current theme.
- Change layout structure, spacing philosophy, or component styling for purely aesthetic reasons.
- Replace or redesign existing sections unless required for a new feature and done in a way that matches current style.

---

## Current Design System (Preserve)

The app uses a defined system; all new and changed UI must stay within it:

| Token / pattern | Usage |
|-----------------|--------|
| **Colors** | `text-apple-text` (#1d1d1f), `text-apple-secondary` (#86868b), `bg-apple-bg` (#f5f5f7), `bg-apple-card` (#ffffff), `border-apple-border`, `text-apple-blue` / `apple-blue-hover` for links and primary actions |
| **Typography** | SF Pro stack: `-apple-system`, `BlinkMacSystemFont`, `SF Pro Display`, `SF Pro Text` (see `frontend/tailwind.config.ts`) |
| **Surfaces** | `rounded-apple` (12px), `rounded-apple-sm` (8px), `shadow-apple`, `shadow-apple-lg` |
| **Patterns** | Cards: `bg-apple-card rounded-apple shadow-apple`; sections: `bg-apple-bg`; secondary text: `text-apple-secondary` |

Reference implementation: `frontend/src/app/agency/page.tsx` and other dashboard sections.

---

## Application by Feature

| Feature | Constraint |
|---------|------------|
| **F1 (OAuth / Connect)** | Add "Connect LinkedIn" and "Connect X" (and status) using existing buttons and cards. Use `apple-blue` for primary actions, same card and spacing as Settings/Onboarding. No new global styles or layout paradigm. |
| **F3 (Brand Voice)** | No UI redesign. Any new controls (e.g. ingestion status) use current cards, badges, and `apple-*` tokens. |
| **F4 (Analytics)** | Keep current dashboard layout and chart styling. Only add or refine data presentation and copy; do not change the overall look. |
| **F9 (Lead enrichment)** | Add an "Enrich" action on lead cards using existing button style. Reuse current lead card layout and typography. |
| **F10 (Newsletter)** | Schedule/review UI follows existing calendar/draft patterns and the same design tokens. |
| **F7 (Agency placeholder)** | Keep current preview layout and styling; only update copy/banner as needed. |

---

## Verification Checklist (Pre-Release)

- [ ] New and modified components use only `apple-*` (and existing Tailwind) tokens; no new colour/font/shadow systems.
- [ ] No removal or redesign of existing sections except where required for a new feature and done in the same style.
- [ ] Copy and feedback (errors, success, loading) improve clarity without changing the minimalist, user-friendly tone.
- [ ] Design review: compare new screens to current dashboard/settings/agency; confirm they feel like the same product.
