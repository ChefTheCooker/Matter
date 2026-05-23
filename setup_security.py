# ============================================================
#  MATTER — setup_security.py
#  Run this ONCE to encrypt your .env file.
#  After this, your plain .env is deleted and only the
#  encrypted version remains on disk.
#
#  Usage:
#    python setup_security.py
# ============================================================

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from security.env_guard import setup

print("=" * 50)
print("  MATTER — Security Setup")
print("=" * 50)
print()
print("This will encrypt your .env file.")
print("Choose a strong password — there is no recovery without it.")
print()

password  = input("Enter master password: ").strip()
password2 = input("Confirm master password: ").strip()

if password != password2:
    print("Passwords do not match. Aborting.")
    sys.exit(1)

if len(password) < 8:
    print("Password too short. Use at least 8 characters.")
    sys.exit(1)

success = setup(password)

if success:
    print()
    print("Done. Your .env is now encrypted.")
    print("Matter will ask for this password on startup.")
else:
    print("Setup failed. Check the error above.")