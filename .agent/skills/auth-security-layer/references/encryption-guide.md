---
name: encryption-guide
description: Key management with AWS KMS and GCP KMS, field-level encryption patterns, envelope encryption, key rotation procedures, and secret management with Vault and AWS Secrets Manager.
---

# Encryption Guide Reference

---

## Envelope Encryption Pattern

Never encrypt data directly with a master key. Use envelope encryption.

```
MASTER KEY (KMS — never leaves KMS)
    ↓ generates
DATA ENCRYPTION KEY (DEK — ephemeral, per-record or per-session)
    ↓ encrypts
CANDIDATE PII (stored in database)

Store alongside data:
  - Encrypted DEK (wrapped by master key)
  - IV / nonce
  - Key version (for rotation)
```

```python
import boto3, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64, json

kms = boto3.client("kms", region_name="us-east-1")
KMS_KEY_ID = os.environ["KMS_KEY_ARN"]

def encrypt_pii_field(plaintext: str) -> str:
    """Envelope-encrypt a single PII field. Returns JSON string for storage."""
    # Generate a data key via KMS
    resp = kms.generate_data_key(KeyId=KMS_KEY_ID, KeySpec="AES_256")
    plaintext_key = resp["Plaintext"]       # Use for encryption
    encrypted_key = resp["CiphertextBlob"]  # Store alongside data

    # Encrypt with AES-256-GCM
    aesgcm = AESGCM(plaintext_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

    return json.dumps({
        "v":   1,
        "kid": KMS_KEY_ID[-8:],    # Last 8 chars of key ID for rotation tracking
        "key": base64.b64encode(encrypted_key).decode(),
        "iv":  base64.b64encode(nonce).decode(),
        "ct":  base64.b64encode(ciphertext).decode(),
    })


def decrypt_pii_field(encrypted_json: str) -> str:
    data = json.loads(encrypted_json)
    encrypted_key = base64.b64decode(data["key"])
    nonce = base64.b64decode(data["iv"])
    ciphertext = base64.b64decode(data["ct"])

    # Decrypt the data key via KMS
    resp = kms.decrypt(CiphertextBlob=encrypted_key)
    plaintext_key = resp["Plaintext"]

    aesgcm = AESGCM(plaintext_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

---

## AWS Secrets Manager — API Keys

```python
import boto3, json
from functools import lru_cache

secrets_client = boto3.client("secretsmanager", region_name="us-east-1")

@lru_cache(maxsize=None)
def get_secret(secret_name: str) -> dict:
    """
    Fetch secret from AWS Secrets Manager.
    Cached in memory — restart required to pick up rotated secrets.
    For rotation-aware loading, remove cache and fetch on each use.
    """
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


# Usage — never hardcode keys
def get_anthropic_key() -> str:
    return get_secret("interview/prod/anthropic")["api_key"]

def get_deepgram_key() -> str:
    return get_secret("interview/prod/deepgram")["api_key"]
```

---

## Key Rotation Procedure

```
ROTATION SCHEDULE
  KMS master keys:       Annual (AWS managed automatic rotation)
  Data encryption keys:  Per-record (generated fresh for each encryption)
  API keys (LLM/STT):   Every 90 days
  JWT signing keys:      Every 30 days
  Service account keys:  Every 90 days
  Database credentials:  Every 90 days via Secrets Manager rotation

ROTATION PROCESS FOR JWT SIGNING KEY
  1. Generate new RS256 key pair
  2. Add new public key to JWKS endpoint (keep old key for validation)
  3. Begin signing new tokens with new private key
  4. Wait for old tokens to expire (max ACCESS_TOKEN_TTL = 15 min)
  5. Remove old public key from JWKS endpoint
  6. Delete old private key from Secrets Manager
```

---

## TLS Configuration

```python
# FastAPI — enforce TLS in production
import ssl

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2   # TLS 1.2 minimum
ssl_context.set_ciphers("ECDH+AESGCM:ECDH+CHACHA20:!aNULL:!MD5:!DSS")
ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

# In production, terminate TLS at the load balancer (ALB/NLB)
# and use internal plaintext between ALB and pods within VPC
```
