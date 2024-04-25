import secrets

def generate_jwt_secret_key(length=64):
    # Generate a random hexadecimal string of the specified length
    return secrets.token_hex(length // 2)

# Generate a JWT secret key of default length (64 characters)
jwt_secret_key = generate_jwt_secret_key()
print("Generated JWT Secret Key:", jwt_secret_key)
