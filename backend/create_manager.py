
import sys
from datetime import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.auth.hashing import hash_password
from app.database import SessionLocal, migrate_head_user_role
from app.models.branch import Branch  # Register the users.branch_id foreign-key target.
from app.models.user import User, UserRole


def create_manager(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    branch_id: int,
) -> User:
    if db.query(User).filter(User.email == email.lower()).first():
        raise ValueError("An account with that email already exists.")
    if not db.query(Branch).filter(Branch.id == branch_id).first():
        raise ValueError("The selected branch does not exist.")

    manager = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.MANAGER,
        is_active=True,
        branch_id=branch_id,
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)
    return manager


def create_head_account(
    db: Session,
    email: str,
    full_name: str,
    password: str,
) -> User:
    if db.query(User).filter(User.email == email.lower()).first():
        raise ValueError("An account with that email already exists.")

    head_account = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.HEAD,
        is_active=True,
    )
    db.add(head_account)
    db.commit()
    db.refresh(head_account)
    return head_account


def assign_existing_manager(db: Session, email: str, branch_id: int) -> User:
    manager = db.query(User).filter(
        User.email == email.lower(),
        User.role == UserRole.MANAGER,
    ).first()
    if manager is None:
        raise ValueError("No manager account with that email exists.")
    if manager.branch_id is not None:
        raise ValueError("This manager is already assigned to a branch.")
    if not db.query(Branch).filter(Branch.id == branch_id).first():
        raise ValueError("The selected branch does not exist.")

    manager.branch_id = branch_id
    db.commit()
    db.refresh(manager)
    return manager


def reset_head_password(db: Session, email: str, new_password: str) -> User:
    head = db.query(User).filter(
        User.email == email.lower(),
        User.role == UserRole.HEAD,
    ).first()
    if head is None:
        raise ValueError("No Head account with that email exists.")
    head.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(head)
    return head


def assign_existing_crew(db: Session, email: str, branch_id: int) -> User:
    crew_member = db.query(User).filter(
        User.email == email.lower(),
        User.role == UserRole.EMPLOYEE,
    ).first()
    if crew_member is None:
        raise ValueError("No crew account with that email exists.")
    if crew_member.branch_id is not None:
        raise ValueError("This crew account is already assigned to a branch.")
    if not db.query(Branch).filter(Branch.id == branch_id).first():
        raise ValueError("The selected branch does not exist.")

    crew_member.branch_id = branch_id
    db.commit()
    db.refresh(crew_member)
    return crew_member


def prompt_for_branch(db: Session) -> Branch:
    branches = db.query(Branch).order_by(Branch.name).all()
    print("\nAvailable branches:")
    for branch in branches:
        print(f"  {branch.id}. {branch.name}")
    print("  N. Create a new branch")
    choice = input("Choose a branch ID or N: ").strip()

    if choice.lower() == "n":
        name = input("Branch name: ").strip()
        if not name or len(name) > 255:
            raise ValueError("Branch name must be between 1 and 255 characters.")
        opening = time.fromisoformat(input("Store opening time (HH:MM): ").strip())
        closing = time.fromisoformat(input("Store closing time (HH:MM): ").strip())
        if closing <= opening:
            raise ValueError("Closing time must be later than opening time.")
        prep_minutes = _prompt_nonnegative_int("Prep time in minutes [30]: ", 30)
        closing_minutes = _prompt_nonnegative_int("Closing time in minutes [30]: ", 30)
        branch = Branch(
            name=name,
            opening_time=opening,
            closing_time=closing,
            prep_time_minutes=prep_minutes,
            closing_time_minutes=closing_minutes,
        )
        db.add(branch)
        db.flush()
        return branch

    try:
        branch_id = int(choice)
    except ValueError as error:
        raise ValueError("Choose a listed branch ID or N.") from error
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if branch is None:
        raise ValueError("The selected branch does not exist.")
    return branch


def _prompt_nonnegative_int(prompt: str, default: int) -> int:
    value = input(prompt).strip()
    if not value:
        return default
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError("Enter a non-negative whole number.") from error
    if result < 0:
        raise ValueError("Enter a non-negative whole number.")
    return result


def prompt_for_account_details(role_label: str) -> tuple[str, str, str]:
    if not sys.stdin.isatty():
        raise ValueError("Run this command in an interactive terminal.")

    email_input = input(f"{role_label} email: ").strip()
    try:
        email = TypeAdapter(EmailStr).validate_python(email_input).lower()
    except ValidationError:
        raise ValueError("Enter a valid email address.")

    full_name = input(f"{role_label} full name: ").strip()
    if not full_name or len(full_name) > 255:
        raise ValueError("Full name must be between 1 and 255 characters.")

    print("Password will be visible while typing. Run this only in a trusted terminal.")
    password = input(f"{role_label} password (at least 8 characters): ")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be no more than 72 bytes.")

    confirmation = input(f"Confirm {role_label.lower()} password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")

    return email, full_name, password


def prompt_for_manager_details() -> tuple[str, str, str]:
    return prompt_for_account_details("Manager")


def main() -> int:
    migrate_head_user_role()
    db = SessionLocal()
    try:
        if not sys.stdin.isatty():
            raise ValueError("Run this command in an interactive terminal.")
        action = input(
            "Choose: [H]ead account setup, [C]reate manager, "
            "[A]ssign manager, [E]nroll crew, or [R]eset head password: "
        ).strip().lower()
        if action not in {"h", "c", "a", "e", "r"}:
            raise ValueError("Choose H, C, A, E, or R.")
        if action == "h":
            email, full_name, password = prompt_for_account_details("Head")
            account = create_head_account(db, email, full_name, password)
        elif action == "r":
            email_input = input("Head account email: ").strip()
            try:
                email = TypeAdapter(EmailStr).validate_python(email_input).lower()
            except ValidationError:
                raise ValueError("Enter a valid email address.")
            print("Password will be visible while typing. Run this only in a trusted terminal.")
            password = input("New password (at least 8 characters): ")
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters.")
            if len(password.encode("utf-8")) > 72:
                raise ValueError("Password must be no more than 72 bytes.")
            confirmation = input("Confirm new password: ")
            if password != confirmation:
                raise ValueError("Passwords do not match.")
            account = reset_head_password(db, email, password)
        else:
            branch = prompt_for_branch(db)
            branch_id = int(branch.id)
            if action == "c":
                email, full_name, password = prompt_for_manager_details()
                account = create_manager(db, email, full_name, password, branch_id)
            else:
                label = "manager" if action == "a" else "crew"
                email = input(f"Existing unassigned {label} email: ").strip()
                try:
                    email = TypeAdapter(EmailStr).validate_python(email).lower()
                except ValidationError as error:
                    raise ValueError("Enter a valid email address.") from error
                account = (
                    assign_existing_manager(db, email, branch_id)
                    if action == "a"
                    else assign_existing_crew(db, email, branch_id)
                )
    except (ValueError, IntegrityError) as error:
        db.rollback()
        print(f"Branch account setup failed: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(
        f"{account.role.value.title()} {account.email} is assigned "
        f"to branch {account.branch_id}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
