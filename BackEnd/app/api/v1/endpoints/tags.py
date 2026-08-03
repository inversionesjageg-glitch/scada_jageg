# BackEnd/app/api/v1/endpoints/tags.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import AsyncSessionLocal
from app.models.scada import TagModel
from app.schemas.scada import TagCreate, TagResponseSchema

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_tag(tag_data: TagCreate, db: AsyncSession = Depends(get_db)):
    """
    Registra un nuevo Tag de forma asíncrona optimizada.
    """
    result = await db.execute(select(TagModel).where(TagModel.tag_name == tag_data.tag_name))
    existing_tag = result.scalar_one_or_none()
    
    if existing_tag:
        raise HTTPException(
            status_code=400,
            detail=f"El Tag con el nombre '{tag_data.tag_name}' ya está registrado."
        )
    
    nuevo_tag = TagModel(**tag_data.model_dump())
    db.add(nuevo_tag)
    await db.commit()
    
    return {
        "message": "Tag creado exitosamente en V1",
        "tag_name": nuevo_tag.tag_name,
        "is_simulated": nuevo_tag.is_simulated
    }

@router.get("/", response_model= List[TagResponseSchema], # <-- Altamente recomendado para asegurar qué campos salen
    status_code=status.HTTP_200_OK )
async def get_tags(db: AsyncSession = Depends(get_db)):
    """
    Recupera todos los tags de forma asíncrona (Espejo en Tiempo Real).
    """
    result = await db.execute(select(TagModel))
    tags = result.scalars().all()
    return tags