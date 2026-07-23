import requests

BASE_URL = "http://localhost:8000/api/v1/auth/signup"

PASSWORD = "Password123!"

SUCCESS = 0
FAILED = 0

for i in range(1, 201):
    payload = {
        "organization_name": f"Test Organization {i}",
        "email": f"user{i}@test.com",
        "password": PASSWORD,
        "full_name": f"Test User {i}"
    }

    try:
        response = requests.post(BASE_URL, json=payload)

        if response.status_code == 201:
            SUCCESS += 1
            print(f"✅ user{i}@test.com created")
        else:
            FAILED += 1
            print(
                f"❌ user{i}@test.com",
                response.status_code,
                response.text
            )

    except Exception as e:
        FAILED += 1
        print(e)

print("\n---------------------")
print(f"Created : {SUCCESS}")
print(f"Failed  : {FAILED}")