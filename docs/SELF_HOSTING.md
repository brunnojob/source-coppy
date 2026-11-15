# Run the business server

The public studio and `operations.html` run on GitHub Pages. Business records are private and live on **your server**, outside the repository and the Pages artifact. No hosted database, paid account, or third-party resource is created by this project.

## What the business application implements

- Owner, manager, cashier and member accounts; expiring server-side sessions; revocation on password or permission changes.
- Single-use team invitations with a 24-hour lifetime. Invitations are shown to the owner, not automatically emailed.
- Customers with editable contact details and archival status.
- Assigned tasks, deadlines and three workflow stages.
- Products, prices in integer cents, stock movements and product archival.
- One open cash register per operator, opening balance, counted cash, expected balance and discrepancy.
- Server-priced sales with atomic inventory reduction, idempotent retries and immutable sale line snapshots.
- Full returns that restore tracked stock once and enter the current register's refund ledger.
- Daily UTC sales/return reports, low-stock reports, CSV exports and audit records.
- Private shared website-project storage with version checks to prevent overwriting a teammate's changes.

These are common business workflows. The 13 SaaS template niches are **not 13 complete vertical products**: no AI inference service, medical record system, payroll engine, campaign delivery platform, or legal/fiscal invoice engine is included. Card/Pix options record payments received through an external provider; they do not initiate charges, validate settlement, or send monetary refunds. The donation Payment Link remains separate from the operational ledger.

## Local Python installation

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r server/requirements.txt
python -m server.manage bootstrap --business "Your business" --email "you@example.com" --name "Owner"
uvicorn server.app:app --host 127.0.0.1 --port 9000
```

The bootstrap command asks for a password without displaying it. It does not ship a default account. Use at least 12 characters. A second bootstrap creates a separate business with a separate owner; the API isolates their data.

In another terminal:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/operations.html`. Set the API URL to `http://localhost:9000`, enter the owner email/password, and sign in. The public Pages frontend may be subject to browser local-network permissions when connecting to localhost; the local frontend avoids that issue during development.

The default database is `server/data/business.sqlite3`. Override it with `BS_DATABASE` pointing to persistent storage. Never put it in a public web directory.

## Docker on your server

```bash
docker compose build
docker compose run --rm api python -m server.manage bootstrap --business "Your business" --email "you@example.com" --name "Owner"
docker compose up -d
```

The API listens on the host's **loopback** port 9000. Data stays in the named `business-data` volume across container recreation. Do not run `docker compose down -v` unless you intentionally want to remove that volume.

Put a reverse proxy with a valid TLS certificate in front of `127.0.0.1:9000`. For example, an Nginx HTTPS virtual host can forward requests with:

```nginx
location / {
    client_max_body_size 25m;
    proxy_pass http://127.0.0.1:9000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Configure the TLS certificate and firewall through your normal server administration workflow. Only expose the proxy's HTTPS port. Set request-size, connection and login rate limits at the proxy too. The application login throttle is database-backed; behind a reverse proxy, all requests may share the proxy's address unless trusted proxy handling is configured appropriately. Never trust arbitrary forwarded headers from the internet.

Set `BS_CORS_ORIGINS` to a comma-separated list of frontend origins, e.g. `https://brunnojob.github.io,https://your-site.example`. Include origins, not URL paths. Restart the API after changing this setting. The client accepts HTTPS endpoints, with HTTP allowed only for loopback development.

Open [Business management](https://brunnojob.github.io/source-coppy/operations.html), enter your HTTPS API URL, and sign in. The URL is stored in local browser preferences; the bearer token stays in session storage and expires after eight hours. No server secret or database password belongs in the browser.

## First operational check

1. Create a tracked product with SKU, price and opening stock. Use an untracked product for services.
2. Open your register with its starting cash balance.
3. Add the product to a sale. Confirm external payment before recording card/Pix sales.
4. Check the receipt and updated inventory.
5. Register a full return if necessary; it restores inventory once and records the return in the open register.
6. Close the register with counted cash and review the discrepancy.
7. Create a cashier/member invitation, deliver the token privately, and have that person accept it with their own password.

Sales are stored with an idempotency key. If a network request times out, the frontend keeps the exact pending request in session storage and offers a retry. Retrying that same request returns the original sale. Do not clear browser session data or start a second order to resolve an uncertain first request; review the sale history with the manager if needed.

## Roles

| Workflow | Owner | Manager | Cashier | Member |
|---|---|---|---|---|
| Read product catalog | Yes | Yes | Yes | Yes |
| Manage products and stock | Yes | Yes | No | No |
| Register sales and manage own register | Yes | Yes | Yes | No |
| Apply discounts / full returns | Yes | Yes | No | No |
| Read customers | Yes | Yes | Yes, for checkout | Yes |
| Manage customers, tasks and shared site projects | Yes | Yes | No | Yes |
| Reports, stock movements and audit | Yes | Yes | No | No |
| Invite/deactivate users | Yes | No | No | No |

An owner cannot be deactivated or demoted through the HTTP API. User permission changes revoke that user's existing sessions. An active request already authorized before revocation can still finish; strict financial deployments should place access controls at the proxy and review audit records.

## Backups, recovery and upgrades

Create a consistent snapshot with SQLite's backup API:

```bash
python -m server.manage backup /private/backups/business-2026-11-15.sqlite3
# Docker example: write a fresh filename inside /data, then copy it off the server.
docker compose exec api python -m server.manage backup /data/business-backup.sqlite3
```

Protect backups, copy them to separate storage, and test restoration periodically. A backup stored only on the same server is not disaster recovery. Backup files contain sensitive business records and password hashes.

To restore: stop the API, preserve the current database, replace the database with a tested backup, remove the stopped database's `-wal` and `-shm` sidecars, correct file permissions, and restart. Do not copy a live SQLite file directly. For a trial restore, set `BS_DATABASE` to a copy in a private test directory and check it before touching the live database.

Reset a user's password locally (all their sessions are revoked):

```bash
python -m server.manage reset-password --email "you@example.com"
```

The schema version is tracked in `schema_version`. This release creates version 1 and refuses an unsupported version. Back up the database before updating the application. Future schema changes require an explicit migration; do not hand-edit the tables while the server is running.

SQLite with WAL and transactional writes is intended for a single self-hosted API instance with durable local disk. Do not share it through NFS or run independently copied databases behind multiple instances. Higher write volume, high availability and multi-region operation require a PostgreSQL deployment and a separate capacity/recovery plan.

## Validation

```bash
npm ci
npm test
pip install -r server/requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

The backend tests use disposable temporary databases. They cover cross-business isolation, permissions, token revocation, invitation reuse, server-controlled prices, invalid quantities, concurrent stock depletion, idempotent retries, returns, cross-register reconciliation, optimistic edits and backup restoration. Operational suitability still depends on your host, HTTPS, backups, monitoring, and the integrations required by your business.
