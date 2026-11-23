# Branch Provisioning and Data Isolation

SmartShift uses **one application and one database for multiple branches**. Each manager account is assigned to one branch. The browser does not choose the branch for operational changes: the API derives it from the authenticated manager account and scopes every read or write to that branch.

Multiple managers can be assigned to the same branch. A manager who is already assigned cannot change their own branch in the application or through the provisioning command.

A separate **Head** account can create branches, create manager accounts, assign managers to branches, and reassign them later. A reassignment changes only the manager's `branch_id`: crew, stations, and schedules stay with their original branch. Managers cannot create or select branches; their assigned branch is shown on their dashboard.

Each newly created manager must also be given the unique numeric Manager ID issued at hiring. It is stored as text to preserve leading zeroes, and serves as an identifier—not as a password or login credential. Existing legacy managers may not have a recorded Manager ID.

Crew sign in with their email, password, and company-issued Employee ID. A manager enters each crew member's Employee ID when creating the account, or assigns it in the crew list for an existing account in that branch. Employee IDs are unique, stored as text to preserve leading zeroes, and are not a replacement for a password. Existing crew without an Employee ID must have one assigned before they can use Crew login. Head accounts continue to sign in with email and password.

## Set up a branch and manager

Run provisioning from the backend directory on a trusted machine with the database configured in `.env`:

```powershell
cd C:\Users\user\OneDrive\Desktop\SchedulingSys\smartshift\backend
.\venv\Scripts\Activate.ps1
python create_manager.py
```

The command is interactive and operator-run. Choose one action:

- **H — Head account setup:** creates a Head account without a branch assignment. Keep these credentials restricted to the authorized operator.
- **C — Create manager:** creates a manager with the selected branch assigned in the same database transaction.
- **A — Assign unassigned manager:** assigns an existing manager account that has no branch. It cannot move an already-assigned manager.
- **E — Enroll unassigned crew:** assigns a legacy employee account that has no branch. It cannot move an already-assigned employee.

For **C**, **A**, and **E**, select an existing branch by ID or choose **N** to create one. New branches require a unique name, opening and closing times, and optional prep/closing minutes (30-minute defaults). When creating a Head or Manager, the command validates the email, asks for a password and confirmation, and stores only its password hash. Password input is visible in the terminal, so run this only in a trusted environment.

The command supports more than one manager in a branch. Keep the provisioning command restricted to trusted operators; it is not exposed as a web endpoint.

After creating a Head account, sign in through the normal login page by selecting **Head**. Head accounts are routed to `head-dashboard.html`, where they can create a branch by setting its name, operating hours, prep time, and closing time. The Head can then create a manager with the issued Manager ID, an initial password, and one of the existing branches. Use **Edit settings** on a manager row to correct the Manager ID, full name, email, or branch. A new password is optional; leaving it blank keeps the current password. The page asks for confirmation before reassigning and states that branch data will not move. Share initial or reset passwords securely.

Managers select **Manager** at login and provide their email, Manager ID, and password. Crew select **Crew** and provide their email, Employee ID, and password. Assign the hiring-issued Manager ID to every existing manager account using Head **Edit settings**, and assign an Employee ID to every existing crew account from that manager's branch before rollout; branchless legacy accounts must first be enrolled into their correct branch by an authorized operator.

Crew accounts created by a manager currently receive the same system-defined initial password. This is a known security risk that remains because the current account-creation behavior was explicitly retained. Managers should share it privately and instruct each crew member to change it immediately after signing in.

## Existing accounts and rollout

The database stores `branch_id` on users, stations, staffing requirements, and published assignments. Startup adds the `HEAD` label to the PostgreSQL user-role enum if it is missing, adds nullable, unique `manager_id` and `employee_number` columns for issued identifiers, and enforces unique branch names regardless of case or surrounding whitespace. Existing manager and crew rows remain in place; IDs are not guessed or generated for them, and existing branch assignments and records are not rewritten. If existing branch names collide after normalization, startup reports the condition and requires those names to be resolved before proceeding.

After deploying the new branch-scoped behavior:

1. Use the operator command to assign each existing manager whose `branch_id` is `NULL`.
2. Assign legacy crew with a `NULL` `branch_id` to the correct branch using action **E**.
3. Confirm each branch's manager and crew assignments before normal scheduling.

Unassigned managers receive an explicit API error and cannot list all branches or operate on branch data. Unassigned employees are excluded from branch crew lists and schedules until an operator assigns them. Existing non-null assignments are preserved. Do not assign legacy records until their real branch is confirmed.

## How isolation is enforced

- **Branch details:** `GET /branches/` returns only the authenticated manager's assigned branch. Branch creation and branch selection are not available through the manager API.
- **Head administration:** `/head/branches`, `POST /head/branches`, and `/head/managers` are Head-only. Head creates branches and manager accounts; `PUT /head/managers/{manager_id}` updates an active manager's profile and optionally resets their password; `PUT /head/managers/{manager_id}/branch` remains available for branch-only reassignment. Managers cannot create branches or reassign their own branch.
- **Login:** `/auth/login` checks the selected account type, email, password, and—for Crew or Manager—the matching assigned Employee ID or Manager ID. Head login remains email and password. The same generic invalid-login response is used for mismatched identifiers and passwords.
- **Crew identifiers:** managers can assign or update an Employee ID only for crew in their own branch. The unique nullable database index permits legacy accounts awaiting assignment while preventing duplicate IDs.
- **Stations:** listing, editing, and removing are filtered by the manager's branch. New stations inherit the branch from the authenticated manager; the request body cannot select a branch.
- **Crew:** listing and deletion are scoped to the manager's branch. New crew inherit that branch. Each requested station qualification must belong to it.
- **Staffing requirements:** managers can read and update required crew counts only for stations in their assigned branch. Counts are unique per branch, station, and shift; generation defaults to one crew member when no saved requirement exists.
- **Schedule export:** Excel, Word, and PDF exports are generated only for an authenticated manager's branch. The API resolves crew and station names from that branch and rejects foreign-branch, inactive, or unqualified crew assignments.
- **Schedules:** generation, publishing, and schedule listing use the manager's current branch, not a branch ID supplied by the browser. Employee, station, requirements, assignments, and saved schedule records are branch-filtered.
- **Statistics:** team counts are scoped to the assigned branch.
- **Availability:** crew availability is tied to the authenticated crew member's user ID; schedule generation loads availability only for employees in that branch.

The frontend displays the assigned branch as read-only and omits branch selectors from station, crew, and schedule forms. API authorization and filtering remain authoritative even if a client is modified or sends an extra branch field.

## Operational notes

- A manager without a branch must be assigned by an operator; there is no self-service branch selection.
- A Head account can create and assign managers only to existing branches. Creating branches and additional Head accounts remains an operator provisioning task.
- Deleting a station is still blocked when it is referenced by a published schedule, preserving schedule history.
- Staffing requirement counts range from 0 to 100. On startup, a unique index is added only when existing branch/station/shift entries are not duplicated; duplicate legacy rows stop startup with an explicit error and must be reconciled before rollout.
- Managers can download the generated schedule draft as an Excel workbook or compact PDF/Word schedules. All formats list crew, station, scheduled time, and hours in chronological order without shift-category labels or unrelated sales and labor figures.
- Branch and account assignment is deliberately not offered to ordinary managers. Future branch transfers should be handled by an authorized operator after reviewing schedules and historical records.
- To verify the implementation, run the backend test suite from this directory:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```
