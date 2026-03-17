#!/usr/bin/env python3
"""One-off script to update a tenant's daily_digest_email in Firestore.

Usage:
    # From the functions/ directory (so shared.firestore_client is importable):
    cd functions
    python -m scripts.update_digest_email              # uses defaults below
    python -m scripts.update_digest_email --tenant-id YOUR_TENANT_ID --email new@example.com

    # Or set GOOGLE_APPLICATION_CREDENTIALS / run inside a GCP environment.
"""

from __future__ import annotations

import argparse
import sys
import os

# Allow running from project root by adding functions/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from shared.firestore_client import query_docs, update_tenant  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Update tenant digest email")
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant ID to update. If omitted, lists all tenants so you can pick one.",
    )
    parser.add_argument(
        "--email",
        default="yoryouyoi@gmail.com",
        help="New daily_digest_email value",
    )
    args = parser.parse_args()

    if args.tenant_id is None:
        print("No --tenant-id provided. Listing all tenants:\n")
        tenants = query_docs("tenants")
        for t in tenants:
            tid = t.get("tenant_id") or t.get("id", "???")
            company = t.get("company_name", "")
            current_email = t.get("daily_digest_email", "(not set)")
            print(f"  {tid}  |  {company}  |  digest_email: {current_email}")
        print(f"\nRe-run with: --tenant-id <ID> --email {args.email}")
        return

    print(f"Updating tenant '{args.tenant_id}' → daily_digest_email = '{args.email}'")
    update_tenant(args.tenant_id, {"daily_digest_email": args.email})
    print("Done.")


if __name__ == "__main__":
    main()
