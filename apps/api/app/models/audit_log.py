from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, nullable=False)
    acao = Column(String, nullable=False)
    tabela_afetada = Column(String, nullable=False)
    registro_id = Column(Integer, nullable=False)
    timestamp_servidor = Column(DateTime(timezone=True), server_default=func.now())
    ip_origem = Column(String, nullable=True)