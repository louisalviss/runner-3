#!/usr/bin/env python3
"""No-network encrypted-bookmark escrow regression suite."""
import datetime as dt
import json
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import cloudflare_d1_bookmark_encrypted_escrow as make
import cloudflare_d1_bookmark_install_vps_only as install


class EncryptedEscrow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.public_pem = cls.k.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.private_pem = cls.k.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        cls.moment = dt.datetime.now(dt.timezone.utc).isoformat()

    def test_sealed_roundtrip_private_key_only(self):
        pub = serialization.load_pem_public_key(self.public_pem)
        envelope = make.seal("00000085-abcdef0123456789-THIS_IS_TEST", pub, self.moment)
        self.assertEqual(envelope["plaintext_exposed"], False)
        self.assertEqual(envelope["d1_write_count"], 0)
        self.assertNotIn("THIS_IS_TEST", json.dumps(envelope))
        restored = install.reveal(envelope, self.private_pem)
        self.assertEqual(restored, "00000085-abcdef0123456789-THIS_IS_TEST")

    def test_escrow_wrong_account_blocked(self):
        pub = serialization.load_pem_public_key(self.public_pem)
        e = make.seal("bookmark-for-test", pub, self.moment)
        e["account_id"] = "different"
        with self.assertRaises(make.Blocked):
            install.reveal(e, self.private_pem)

    def test_tampering_cannot_decrypt(self):
        pub = serialization.load_pem_public_key(self.public_pem)
        e = make.seal("bookmark-for-test", pub, self.moment)
        e["ciphertext_aes256gcm_b64"] = "AA" + e["ciphertext_aes256gcm_b64"][2:]
        with self.assertRaises(make.Blocked):
            install.reveal(e, self.private_pem)

    def test_stale_bookmark_rejected(self):
        pub = serialization.load_pem_public_key(self.public_pem)
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        e = make.seal("bookmark-for-test", pub, old)
        with self.assertRaises(make.Blocked):
            install.reveal(e, self.private_pem)

    def test_bad_bookmark_blocked(self):
        pub = serialization.load_pem_public_key(self.public_pem)
        for b in ("", "short", "line\nbreak", "bad\x00value"):
            with self.subTest(bookmark=b), self.assertRaises(make.Blocked):
                make.seal(b, pub, self.moment)

    def test_cloudflare_url_allowlist(self):
        self.assertEqual(len(make.ALLOWED), 2)
        self.assertTrue(all(x.startswith("https://api.cloudflare.com/") for x in make.ALLOWED))
        with self.assertRaises(make.Blocked):
            make.get("X" * 32, "https://api.cloudflare.com/client/v4/other")

    def test_no_dangerous_operation_in_escrow_source(self):
        from pathlib import Path
        s = Path(make.__file__).read_text()
        self.assertNotIn('method="POST"', s)
        self.assertNotIn('method="DELETE"', s)
        self.assertNotIn("time_travel/restore", s)
        self.assertNotIn("/query", s)
        self.assertNotIn("print(bookmark)", s)


if __name__ == "__main__":
    unittest.main()
