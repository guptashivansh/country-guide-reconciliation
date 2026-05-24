# Sync Pipeline

The sync pipeline is the core workflow that keeps employment guides up to date with official government sources.

## Pipeline Stages

### 1. Source Discovery

The system reads a registry of official government URLs organized by country and section (e.g., India → Leave Policies → ministry URL). The registry is maintained externally so URLs can be updated without redeployment.

### 2. Ingestion

HTML is fetched from each official source, cleaned, and stored as a snapshot in the database. Each snapshot is timestamped and linked to its source URL for traceability.

### 3. Extraction

The HTML content is chunked (to fit LLM context windows) and sent to Groq's LLaMA 3.3 70B for structured extraction. The LLM returns `EmploymentRule` objects with fields like section, description, and effective dates. Multi-key rotation handles rate limits transparently.

### 4. Reconciliation

![Ops Dashboard — Review Queue](assets/screenshots/ops_dashboard.png)

Extracted rules are compared against the current live guide using semantic reconciliation:

- **Change types**: Added, Modified, Clarification, Deprecated, Removed, Unverified
- **Materiality levels**: Critical, Moderate, Low, Informational
- **Diff method**: Regex-based + string similarity with word-level highlighting

### 5. Review

Changes land in a review queue where compliance reviewers can:

- View before/after diffs with semantic highlighting
- See source evidence and extraction confidence
- Approve or reject each change individually
- Bulk-approve low-risk changes

### 6. Publication

Approved changes are written to both the active `country_guide` table and the immutable `country_guide_versions` table, with a full audit log entry recording who approved, when, and why.

### 7. Drift Detection

After publication, the drift detector monitors for unexpected rule changes and sends Slack alerts when compliance drift is detected.
