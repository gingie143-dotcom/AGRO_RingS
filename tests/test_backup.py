import pytest
from cryptography.fernet import Fernet, InvalidToken
from app.backups import encrypt_dump, decrypt_dump, restore_to_empty


def test_backup_authentication_and_roundtrip():
    key = Fernet.generate_key().decode()
    source = b"PostgreSQL dump data"
    encrypted = encrypt_dump(source, key)
    assert source not in encrypted
    assert decrypt_dump(encrypted, key) == source
    with pytest.raises(InvalidToken):
        decrypt_dump(encrypted, Fernet.generate_key().decode())
    with pytest.raises(InvalidToken):
        decrypt_dump(encrypted[:-20] + b"tampered", key)


def test_restore_refuses_live_database():
    with pytest.raises(ValueError):
        restore_to_empty("file", "production")
