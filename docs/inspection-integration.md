# Process inspection images in Tower Thermal

1. Upload an original image to a **TH Full** or **TH Close** card in a field visit.
2. Click **Process thermal image**. The editor opens in another tab and loads that image.
3. Sign in to the thermal application if needed, using an administrator-created thermal account.
   Existing inspection and thermal accounts remain separate; passwords are never shared.
4. Enhance the image, add measurements and annotations, then click **Save back to inspection**.
5. The open inspection page refreshes its evidence cards. **View inspection** also opens the visit.

The processed PNG occupies the existing annotation/edited-copy field for the exact image ID,
including supplementary images. Original image bytes, radiometric data, capture information,
position, TH Full/TH Close classification and other images are preserved. Generated reports use
the existing edited-copy behavior; previously generated PDF/DOCX files must be regenerated.
Tmax/Tref and screening judgments in the visit are not automatically changed by visual edits.

Reopening from the inspection resumes the same private thermal workspace for the same thermal
user, inspection user, source image ID and source digest. A replacement original opens a fresh
workspace. Draft save stays in Thermal; **Save back to inspection** explicitly publishes the
rendered result. Thermal exports remain available. A flattened source has no recoverable
radiometric temperatures; only original supported radiometric images can be measured.

## Access and conflicts

The inspection server verifies current account approval/active state, role, team and assigned
member scope. Customer/client accounts cannot launch the editor. The editor requires its existing
private-workspace session; another thermal user cannot access this imported workspace. The
inspection server repeats authorization when reading the source or accepting a result.

Launch tickets contain 256 bits of randomness, are stored hashed on the inspection server,
are single-use and expire after 10 minutes. They travel in a URL fragment (not server URLs).
Once claimed, saving is permitted for up to 12 hours, still subject to current permissions.
Expired sessions can be renewed with **Process thermal image**. Service communication requires
a separate shared secret, never returned to the browser. Source and return URLs are fixed by
server configuration, not accepted from clients. Tickets in thermal linkage rows are not
included in editable packages or ordinary image metadata/API responses.

If the inspection image changes during editing, saving returns a conflict rather than
silently overwriting it. Local editable work is saved first even if the transfer fails.
Repeated successful saves of identical output are idempotent. Outputs use fresh storage paths;
originals and previous edited files are retained. Launching alone does not alter evidence.

## Configuration and deployment

Set the same securely generated secret (at least 32 characters) as `THERMAL_BRIDGE_SECRET`
in the main backend environment and `INSPECTION_BRIDGE_SECRET` in Thermal's environment.
Thermal's `INSPECTION_ORIGIN` is the main application's fixed HTTPS origin. The feature fails
closed while unconfigured. Do not place keys in frontend variables or Git.

Thermal migration 0005 creates private image-link rows. The main app creates a new
`thermal_edit_grants` table through its existing metadata startup mechanism. Both additions
are separate from existing evidence tables. Expired grants are pruned when new links are
created. Back up both databases/environments before deploying. No original data is migrated
or rewritten, and no existing user permissions or credentials are changed.
