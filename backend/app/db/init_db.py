"""Database Initialization and Seed Data Provider."""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import (
    DatabaseConnection,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

logger = logging.getLogger("askyourdata.init_db")

SYSTEM_ROLES = [
    ("Admin", "Full administrative access to the platform", True),
    ("Editor", "Can create and edit charts, dashboards, and datasets", True),
    ("Viewer", "Can view published charts and dashboards", True),
    ("SQL Lab user", "Access to SQL Lab query editor", True),
]

CORE_PERMISSIONS = [
    # Resources: databases, datasets, charts, dashboards, sqllab, uploads, admin, ai
    ("databases:read", "View database connections", "databases"),
    ("databases:write", "Create and edit database connections", "databases"),
    ("datasets:read", "View datasets and metadata", "datasets"),
    ("datasets:write", "Create, edit and manage datasets", "datasets"),
    ("charts:read", "View charts", "charts"),
    ("charts:write", "Create and edit charts", "charts"),
    ("dashboards:read", "View dashboards", "dashboards"),
    ("dashboards:write", "Create and edit dashboards", "dashboards"),
    ("sqllab:use", "Execute queries in SQL Lab", "sqllab"),
    ("uploads:use", "Upload files into DuckDB", "uploads"),
    ("admin:access", "Access admin control panels and audit logs", "admin"),
    ("ai:use", "Query data using the AI assistant", "ai"),
]


async def init_system_data(session: AsyncSession) -> None:
    """Initialize system roles, permissions, default DuckDB connection, and seed admin user."""
    logger.info("Initializing system permissions and roles...")

    # 1. Seed Permissions
    permission_map: dict[str, Permission] = {}
    for code, name, resource in CORE_PERMISSIONS:
        perm_stmt = select(Permission).where(Permission.code == code)
        perm_result = await session.execute(perm_stmt)
        perm = perm_result.scalar_one_or_none()
        if not perm:
            perm = Permission(code=code, name=name, resource=resource)
            session.add(perm)
            await session.flush()
        permission_map[code] = perm

    # 2. Seed Roles
    role_map: dict[str, Role] = {}
    for name, desc, is_sys in SYSTEM_ROLES:
        role_stmt = select(Role).where(Role.name == name)
        role_result = await session.execute(role_stmt)
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name=name, description=desc, is_system=is_sys)
            session.add(role)
            await session.flush()
        role_map[name] = role

    # 3. Associate Permissions to Roles
    # Admin gets all
    admin_role = role_map["Admin"]
    for p_obj in permission_map.values():
        assoc = await session.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == p_obj.id,
            )
        )
        if not assoc.scalar_one_or_none():
            session.add(RolePermission(role_id=admin_role.id, permission_id=p_obj.id))

    # Editor gets editing rights
    editor_role = role_map["Editor"]
    editor_perms = [
        "databases:read", "datasets:read", "datasets:write",
        "charts:read", "charts:write", "dashboards:read", "dashboards:write",
        "sqllab:use", "uploads:use", "ai:use",
    ]
    for code in editor_perms:
        perm_item = permission_map.get(code)
        if perm_item:
            assoc = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == editor_role.id,
                    RolePermission.permission_id == perm_item.id,
                )
            )
            if not assoc.scalar_one_or_none():
                session.add(RolePermission(role_id=editor_role.id, permission_id=perm_item.id))

    # Viewer gets read rights
    viewer_role = role_map["Viewer"]
    for code in ["charts:read", "dashboards:read"]:
        viewer_perm = permission_map.get(code)
        if viewer_perm:
            assoc = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == viewer_role.id,
                    RolePermission.permission_id == viewer_perm.id,
                )
            )
            if not assoc.scalar_one_or_none():
                session.add(RolePermission(role_id=viewer_role.id, permission_id=viewer_perm.id))

    # SQL Lab user
    sqllab_role = role_map["SQL Lab user"]
    for code in ["sqllab:use", "databases:read", "datasets:read"]:
        sqllab_perm = permission_map.get(code)
        if sqllab_perm:
            assoc = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == sqllab_role.id,
                    RolePermission.permission_id == sqllab_perm.id,
                )
            )
            if not assoc.scalar_one_or_none():
                session.add(RolePermission(role_id=sqllab_role.id, permission_id=sqllab_perm.id))

    # 4. Seed Admin User
    admin_stmt = select(User).where(User.email == settings.ADMIN_EMAIL)
    admin_result = await session.execute(admin_stmt)
    admin_user = admin_result.scalar_one_or_none()

    if not admin_user:
        logger.info(f"Creating default admin user: {settings.ADMIN_EMAIL}")
        admin_user = User(
            email=settings.ADMIN_EMAIL,
            full_name="System Administrator",
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            is_active=True,
            is_superuser=True,
        )
        session.add(admin_user)
        await session.flush()

        # Assign Admin role
        session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

    # 5. Seed Built-in DuckDB 'Uploads' Connection
    uploads_stmt = select(DatabaseConnection).where(DatabaseConnection.name == "Uploads")
    uploads_result = await session.execute(uploads_stmt)
    uploads_conn = uploads_result.scalar_one_or_none()

    if not uploads_conn:
        logger.info("Registering built-in DuckDB 'Uploads' connection...")
        uploads_conn = DatabaseConnection(
            name="Uploads",
            description="Internal DuckDB analytical columnar store for uploaded files",
            dialect="duckdb",
            is_system=True,
            allow_dml=False,
            allow_file_uploads=True,
            allow_sqllab=True,
            row_limit=settings.DEFAULT_ROW_LIMIT,
            statement_timeout_seconds=settings.STATEMENT_TIMEOUT_SECONDS,
            ai_allowed_schemas=["main"],
            created_by_id=admin_user.id if admin_user else None,
        )
        session.add(uploads_conn)

    await session.commit()
    logger.info("System data initialization complete.")

