import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class LayerMetadata(Base):
    __tablename__ = "layers_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(512), nullable=False)
    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(64), nullable=True)
    tabela_postgis: Mapped[str] = mapped_column(String(128), nullable=True)
    workspace: Mapped[str] = mapped_column(String(128), nullable=True)
    datastore: Mapped[str] = mapped_column(String(128), nullable=True)
    wms_url: Mapped[str] = mapped_column(Text, nullable=True)
    wfs_url: Mapped[str] = mapped_column(Text, nullable=True)
    bbox: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
