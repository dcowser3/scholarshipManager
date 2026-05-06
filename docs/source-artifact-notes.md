# Source Artifact Notes

This file captures what the current local source artifacts actually did during Phase 1 verification.

## Verified Against Local Files

- CSV path: `/Users/deriancowser/Downloads/Athletic Aid Amounts (1).csv`
- Adjustment template path: `/Users/deriancowser/Downloads/Adjustment of Aid Template 25-26.xlsx`
- Legacy converter path: `/Users/deriancowser/Downloads/scholarship_converter.html`
- Tender example path: `/Users/deriancowser/Downloads/R01647930 Corey Smith.pdf`

## Confirmed Behaviors

- The CSV must be read with `utf-8-sig`.
- The CSV still contains 28 duplicate Rocket IDs, and last-row-wins deduping works.
- `SPRING_ATHLETICS_GENERAL_FEE1` is redundant and matches `SPRING_ATHLETICS_GENERAL_FEE`.
- The converter still contains the older sport naming set such as `Spirit`, `Women's Volleyball`, `Women's Swimming & Diving`, and `Women's Track & Field`.
- The Tender example is a real mid-year case with a zeroed fall column and populated spring column.

## Real-File Differences From The Brief

- The importable CSV row count is currently `425` data rows after ignoring the trailing blank line.
- The CSV includes blank `COHORT` values.
- The CSV includes many `TGN` rows, which cannot be placed into a concrete `terms` record without a stakeholder rule.

## Current Import Outcome

After seeding terms through `26-27` and importing the real CSV:

- `397` athletes imported
- `580` roster memberships imported
- `580` aid records imported
- `21` athletes skipped because `COHORT` was blank
- `88` athletes skipped because `COHORT = TGN`

## Manual Recovery Rule

- Blank and `TGN` cohorts now create rows in `import_cohort_issues`, grouped by sport.
- A coach or admin can assign an academic year manually.
- The chosen academic year is saved on the athlete as a cohort override.
- Future imports reuse that override automatically whenever the source cohort is still blank or `TGN`.
