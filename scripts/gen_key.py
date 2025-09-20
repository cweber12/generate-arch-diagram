import secrets, hashlib
key = secrets.token_urlsafe(32)
print("API_KEY to give users:\n", key)
print("API_KEY_SHA256 for server env:\n", hashlib.sha256(key.encode()).hexdigest())