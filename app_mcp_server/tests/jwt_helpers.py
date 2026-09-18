"""测试用 RSA 钥对与 JWT。自生成密钥，不要用生产私钥。"""
import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_pair() -> tuple[str, str]:
    """返回 (private_pem, public_pem)。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def make_jwt(private_pem: str, *, alg: str = "RS256", drop=(), **claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "sunwill-mcp",
        "aud": "plm",
        "sub": "E001",
        "iat": now,
        "exp": now + timedelta(hours=1),
        **claims,
    }
    for key in drop:
        payload.pop(key, None)
    if alg == "RS256":
        key = private_pem
    else:
        key = "hs256-test-secret"
    return jwt.encode(payload, key, algorithm=alg)


def make_unsigned_token(**claims) -> str:
    """alg=none 的伪造 token（不走 PyJWT encode，2.x 默认禁止 none）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "sunwill-mcp",
        "aud": "plm",
        "sub": "E001",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        **claims,
    }
    header = {"alg": "none", "typ": "JWT"}

    def b64(data: dict) -> bytes:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    return (b64(header) + b"." + b64(payload) + b".").decode()
