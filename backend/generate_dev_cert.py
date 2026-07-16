"""Generates a self-signed TLS certificate for local/LAN development so
start-server.ps1 can serve the app over HTTPS instead of plain HTTP - without
this, every request (including the temporary passwords an HOA relays to new
members) travels the network unencrypted.

Not for production use: this is a self-signed cert (browsers will show a
one-time trust warning), not one from a real CA. A real deployment should
sit behind a reverse proxy with a certificate from a real CA instead.

Usage: python generate_dev_cert.py [extra-host-or-ip ...]
"""

import ipaddress
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = Path(__file__).resolve().parent / "certs"
KEY_PATH = CERT_DIR / "dev-key.pem"
CERT_PATH = CERT_DIR / "dev-cert.pem"


def _san_entry(host: str):
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        return x509.DNSName(host)


def generate(extra_hosts: list[str]) -> None:
    # Skip regeneration if a cert already exists - delete backend/certs/ to
    # force a fresh one (e.g. after the LAN IP changes and it's no longer in
    # the existing cert's SAN list).
    if KEY_PATH.exists() and CERT_PATH.exists():
        return

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Tit4Tat Local Dev")])

    san_entries = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    for host in extra_hosts:
        entry = _san_entry(host)
        if entry not in san_entries:
            san_entries.append(entry)

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


if __name__ == "__main__":
    generate(sys.argv[1:])
    print(CERT_PATH)
    print(KEY_PATH)
