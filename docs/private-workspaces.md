# Accounts and private workspaces

Users sign in with individual accounts. Only administrators can create accounts,
change their roles, disable access, reset passwords, or delete accounts. There is
no public registration. Application branding settings also require an administrator.

## First production deployment

`scripts/deploy-production.sh` backs up SQLite and the thermal nginx snippet,
runs the account migration, and bootstraps `nasser` only when no accounts exist.
Existing inspections and the reference library are assigned to this account.
New accounts start with an empty workspace.

The generated temporary login is written with mode 600 to
`/data/initial-admin-login.txt` in the API's persistent storage. Retrieve this file
through the trusted server console, share it privately with the administrator,
and remove the file after the administrator has chosen a new password. Never
commit this file. `.private/` is ignored for local credential handoffs.

The deployment replaces the shared HTTP Basic password on `/thermal/` with the
application sign-in screen only after confirming the API rejects anonymous access.
The main website's routes and containers are not redeployed.

For a new local installation, run `alembic upgrade head`, then
`python -m app.bootstrap_admin --username nasser --credential-file ../.private/initial-admin-login.txt`
from the backend directory. The command refuses to run if accounts already exist.

## Day-to-day use

1. Administrator: open **Users → Add user**, enter a name, username, role, and a
   temporary password of at least 12 characters. Share the login privately.
2. User: sign in, replace the temporary password, then upload images. Save draft
   preserves editable work; **Inspections** lists all your saved images.
3. Administrator: **Edit** can change details, reset a password, or disable access.
   Changes to another account revoke its sessions. Reset passwords must be changed.
4. **Delete** removes account access and revokes sessions. Inspection records are
   retained under that deleted account, available for read-only administrator review.
   This is archival deletion, not permanent erasure. Usernames remain reserved.
5. **Change password** changes your own password and revokes other sessions.
   **Sign out** clears the current session. Administrators cannot disable, demote,
   or delete themselves.

## Privacy boundaries

The API checks ownership of inspections, images, analyses, regions, exports,
supporting images, annotations, and saved workspaces. Library documents and search
use a separate directory per account. Administrators can browse all saved inspections and images through the explicit
read-only All user work routes. They cannot modify another user's workspace through
the ordinary editing routes. Library documents remain owner-only. People with direct server or backup access remain trusted operators.

Passwords are salted PBKDF2 hashes. Session tokens are random, stored as hashes,
and sent in HttpOnly, SameSite=Strict cookies (Secure on production HTTPS). Sessions
expire after 12 hours. Requests that change data require the application's custom
header and reject untrusted browser origins. API responses are not browser cached.

SQLite remains the database. Keep backups protected: they contain private work.
Migration rollback requires a reviewed database backup restore; the migration
does not attempt to merge multiple private workspaces back into a shared database.

## Administrator review

Use **All user work**, or **Users → View work**, to browse saved inspections.
Filter by owner, search by tower/circuit/username/image name, and open an image.
Saved work renders the persisted enhancements, measurements, notes, labels and
supporting images; Original preview displays the source preview. Unsaved browser
changes are not available. Disabled and deleted users remain visible for archival
review. The normal personal Inspections page still lists only your own work.
