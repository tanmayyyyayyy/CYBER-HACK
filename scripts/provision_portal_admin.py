from __future__ import annotations

import getpass
import uuid

from security_portal import store


def main() -> int:
    store.init_db()
    employee_id = input("Initial administrator employee ID: ").strip()
    email = input("Administrator email: ").strip().lower()
    display_name = input("Administrator name: ").strip()
    mobile = input("Administrator mobile: ").strip()
    password = getpass.getpass("Passphrase (at least 12 characters): ")
    if len(password) < 12 or password != getpass.getpass("Confirm passphrase: "):
        print("Passphrases must match and be at least 12 characters.")
        return 1
    if not employee_id or not email or not display_name or not mobile:
        print("Employee ID, email, name, and mobile are required.")
        return 1

    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM portal_users LIMIT 1").fetchone():
            print("Portal already has an account; ask an existing super admin to provision users.")
            return 1
        db.execute(
            """INSERT INTO portal_users(
                id, employee_id, email, display_name, mobile, role, password_hash,
                verification_status, status, created_at
            ) VALUES(?,?,?,?,?,'super_admin',?,'pending','active',?)""",
            (uuid.uuid4().hex, employee_id, email, display_name, mobile,
             store.hash_secret(password), store.now_iso()),
        )
    print("Initial portal super admin created. Sign in and provision the remaining accounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
