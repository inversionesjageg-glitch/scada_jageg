# BackEnd/app/models/auth.py
import logging
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..database import Base

logger = logging.getLogger("SCADA_Jageg_AuthModels")

class RolePermissionModel(Base):
    """
    Tabla intermedia (Many-to-Many) que vincula los Roles con sus Permisos atómicos.
    """
    __tablename__ = "scada_role_permissions"

    role_id = Column(Integer, ForeignKey("scada_roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("scada_permissions.id", ondelete="CASCADE"), primary_key=True)


class PermissionModel(Base):
    """
    Define los permisos atómicos del SCADA. 
    Ejemplos: "tags:read", "tags:write_sp", "alarms:ack", "users:manage"
    """
    __tablename__ = "scada_permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)

    roles = relationship("RoleModel", secondary="scada_role_permissions", back_populates="permissions")


class RoleModel(Base):
    """
    Perfiles o Roles del sistema. Ejemplos: "ADMIN", "OPERATOR", "VIEWER".
    """
    __tablename__ = "scada_roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)

    permissions = relationship("PermissionModel", secondary="scada_role_permissions", back_populates="roles", lazy="selectin")
    users = relationship("UserModel", back_populates="role", lazy="raise_on_sql")


class UserModel(Base):
    """
    Usuarios del sistema con credenciales hashadas y vinculación a un perfil/role único.
    """
    __tablename__ = "scada_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    role_id = Column(Integer, ForeignKey("scada_roles.id", ondelete="RESTRICT"), nullable=False)
    
    role = relationship("RoleModel", back_populates="users", lazy="joined")