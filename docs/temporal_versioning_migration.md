# Temporal Compliance Versioning Migration Plan

## Goal

Preserve `country_guide` as the current active rule table while adding an immutable historical snapshot table, `country_guide_versions`, for time-based rule lookup and audit reconstruction.

## Schema Changes

- Add active-rule metadata columns to `country_guide`:
  - `effective_date`
  - `created_at`
  - `version_number`
  - `approval_reference`
- Add `effective_date` to `review_queue` so reviewer approvals can publish a specific effective date.
- Add `country_guide_versions`:
  - `country`
  - `section`
  - `value`
  - `source_url`
  - `source_hash`
  - `effective_date`
  - `created_at`
  - `superseded_at`
  - `version_number`
  - `approval_reference`
  - `metadata`

## Incremental Rollout

1. Deploy schema migration through `CountryGuideRepository.initialize_schema()`.
2. Backfill each existing active rule into `country_guide_versions` with `version_number = 1`.
3. Continue serving current guide reads from `country_guide`.
4. Route new approvals and direct upserts through the version publisher.
5. Expose temporal reads through:
   - `GET /api/guide/<country>/<section>/history`
   - `GET /api/guide/<country>/<section>/at?date=YYYY-MM-DD`

## Operational Notes

- Rule content snapshots are append-only. When a new version is published, the previous active snapshot receives `superseded_at` to close its effective interval.
- `country_guide` remains the denormalized active read model for low-latency UI and API reads.
- Version rows are keyed by `(country, section, version_number)`, which scales cleanly across multi-country rule catalogs.
- The temporal query path uses `effective_date <= date X` and `superseded_at > date X OR superseded_at IS NULL`.
