# BackEnd/app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# --- Esquemas de Permisos ---
class PermissionResponseSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas de Roles / Perfiles ---
class RoleResponseSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    permissions: List[PermissionResponseSchema] = []
    
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas de Usuarios ---
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Nombre de usuario único")
    email: EmailStr = Field(..., description="Correo electrónico válido")
    password: str = Field(..., min_length=6, description="Contraseña limpia (se hashará en el backend)")
    role_id: int = Field(..., description="ID del rol/perfil asignado")

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role_id: Optional[int] = None

class UserResponseSchema(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    role: RoleResponseSchema
    
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas para Token JWT (Login) ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None