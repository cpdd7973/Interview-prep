---
name: compliance-controls
description: GDPR Article-by-Article implementation guide, SOC2 evidence collection templates, data mapping worksheet, consent management patterns, and sub-processor checklist for AI hiring platforms.
---

# Compliance Controls Reference

---

## GDPR Implementation by Article

| Article | Right | Implementation |
|---|---|---|
| Art. 13/14 | Privacy notice | Show at session start, store consent timestamp |
| Art. 15 | Right of access | `/api/candidate/data-export` endpoint |
| Art. 16 | Right to rectification | Allow profile edits, log changes |
| Art. 17 | Right to erasure | `GDPRService.handle_erasure_request()` |
| Art. 18 | Right to restriction | Flag account, pause processing |
| Art. 20 | Data portability | Export as machine-readable JSON |
| Art. 22 | Automated decisions | Disclose LLM scoring, allow human review |

---

## Data Mapping Worksheet

```
PERSONAL DATA INVENTORY
──────────────────────────────────────────────────────────────────
Data Element          | Category  | Legal Basis    | Retention | Processor
──────────────────────────────────────────────────────────────────
Full name             | Personal  | Contract       | 24 months | Postgres (AWS)
Email address         | Personal  | Contract       | 24 months | Postgres (AWS)
Phone number          | Personal  | Contract       | 24 months | Postgres (AWS)
Resume/CV             | Personal  | Contract       | 24 months | S3 (AWS)
Interview transcript  | Personal  | Legitimate int | 12 months | Postgres (AWS)
Audio recording       | Special   | Explicit consent| 90 days  | S3 (AWS)
Interview score       | Personal  | Legitimate int | 24 months | Postgres (AWS)
IP address            | Personal  | Legitimate int | 90 days   | Logs (Datadog)
──────────────────────────────────────────────────────────────────
Special category data requires explicit consent + DPA with all processors.
Audio recordings are potentially biometric — treat as special category.
```

---

## Sub-Processor Checklist

```
For each third-party service that processes candidate data:

  □ Data Processing Agreement (DPA) signed
  □ Standard Contractual Clauses (SCCs) if transferring outside EEA
  □ Verified: data NOT used for model training
  □ Data residency confirmed (EU data stays in EU if required)
  □ Breach notification SLA: 72 hours or less

REQUIRED DPAs:
  □ Anthropic (LLM — receives transcript content)
  □ Deepgram / AssemblyAI (STT — receives audio)
  □ ElevenLabs / OpenAI TTS (TTS — receives interview questions)
  □ AWS (infrastructure — hosts all data)
  □ Datadog (monitoring — may receive log data with IDs)
```

---

## Consent Management

```python
async def record_consent(
    candidate_id: str,
    consent_type: str,   # 'interview_recording', 'ai_evaluation', 'data_storage'
    consented: bool,
    ip_address: str,
    user_agent: str,
):
    """Record explicit consent with full audit trail."""
    await db.execute("""
        INSERT INTO consent_records
            (candidate_id, consent_type, consented, ip_address,
             user_agent, consented_at, consent_version)
        VALUES ($1, $2, $3, $4, $5, NOW(), $6)
    """, candidate_id, consent_type, consented,
        ip_address, user_agent, CURRENT_CONSENT_VERSION)

CURRENT_CONSENT_VERSION = "2025-01-01-v1"
# Bump version when privacy policy changes — re-consent required
```

---

## SOC2 Evidence Collection

```python
# Automate evidence gathering for SOC2 audits
class SOC2EvidenceCollector:

    async def collect_access_review_evidence(self) -> dict:
        """CC6.2 — User access reviews conducted quarterly."""
        users_with_access = await db.fetchall("""
            SELECT u.id, u.email, u.role, u.last_login_at,
                   u.created_at, u.deprovisioned_at
            FROM users u
            WHERE u.deprovisioned_at IS NULL
            ORDER BY u.role, u.email
        """)
        return {
            "evidence_type":  "user_access_review",
            "collected_at":   datetime.now(timezone.utc).isoformat(),
            "user_count":     len(users_with_access),
            "users":          users_with_access,
            "review_period":  "quarterly",
        }

    async def collect_encryption_evidence(self) -> dict:
        """CC6.7 — Data encrypted in transit and at rest."""
        return {
            "evidence_type": "encryption_controls",
            "at_rest": {
                "database":    "AWS RDS — AES-256, KMS-managed keys",
                "s3":          "SSE-KMS on all buckets",
                "pii_fields":  "Application-level AES-256-GCM, envelope encryption",
            },
            "in_transit": {
                "external":    "TLS 1.2+ enforced at ALB",
                "internal":    "mTLS between services via service mesh",
            },
        }
```
