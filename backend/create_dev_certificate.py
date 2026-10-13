"""Create a self-signed localhost server certificate; never install a trusted CA."""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

folder = Path(__file__).resolve().parent.parent / 'frontend' / 'certificates'
cert_file = folder / 'localhost.pem'
key_file = folder / 'localhost-key.pem'
if cert_file.exists() and key_file.exists():
    cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
    if cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=1):
        print('Local HTTPS certificate is ready.')
        raise SystemExit(0)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
timestamp = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(timestamp - timedelta(minutes=5))
    .not_valid_after(timestamp + timedelta(days=30))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ip_address('127.0.0.1')), x509.IPAddress(ip_address('::1'))]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .sign(key, hashes.SHA256()))
folder.mkdir(parents=True, exist_ok=True)
key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
key_file.chmod(0o600)
cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print('Created self-signed localhost HTTPS certificate. No system trust settings changed.')
