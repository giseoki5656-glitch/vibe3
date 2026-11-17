import bcrypt


def hash_password(password: str) -> str:
    # bcrypt 는 72바이트까지만 사용하므로 잘라서 일관되게 처리한다.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except ValueError:
        return False


# 존재하지 않는 아이디로 로그인 시도할 때도 비슷한 시간이 걸리도록 하는 더미 해시
DUMMY_HASH = hash_password("dummy-password-for-timing")
