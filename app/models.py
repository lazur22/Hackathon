"""Modelo de dados. Genérico: nada aqui é específico de TI — setores, equipes, tipos e fluxos são dados."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def agora() -> datetime:
    """UTC naive (portável entre SQLite e PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- estrutura organizacional
class Setor(Base):
    __tablename__ = "setores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    sigla: Mapped[str] = mapped_column(String(20), default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Equipe(Base):
    __tablename__ = "equipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    setor_id: Mapped[int] = mapped_column(ForeignKey("setores.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    setor: Mapped[Setor] = relationship()
    __table_args__ = (UniqueConstraint("setor_id", "nome"),)


class TipoTarefa(Base):
    """Tipo de tarefa = fluxo configurável (exige evidência? exige validação do demandante? SLA? complexidade?)."""
    __tablename__ = "tipos_tarefa"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    setor_id: Mapped[int] = mapped_column(ForeignKey("setores.id"))
    equipe_padrao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipes.id"), nullable=True)
    complexidade: Mapped[str] = mapped_column(String(10), default="media")  # baixa|media|alta
    sla_inicio_min: Mapped[int] = mapped_column(Integer, default=240)       # minutos até iniciar
    exige_evidencia: Mapped[bool] = mapped_column(Boolean, default=False)
    exige_validacao: Mapped[bool] = mapped_column(Boolean, default=True)
    campos_obrigatorios: Mapped[list] = mapped_column(JSON, default=list)   # ex.: ["local","ramal"]
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    setor: Mapped[Setor] = relationship()
    equipe_padrao: Mapped[Optional[Equipe]] = relationship()
    __table_args__ = (UniqueConstraint("setor_id", "nome"),)


# ---------------------------------------------------------------- usuários e sessões
class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    login: Mapped[str] = mapped_column(String(60), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(200))
    perfis: Mapped[str] = mapped_column(String(120), default="executor")  # csv: admin,atendente,gestor,executor,demandante
    equipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipes.id"), nullable=True)
    setor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("setores.id"), nullable=True)
    avatar: Mapped[str] = mapped_column(String(8), default="🧭")
    contato: Mapped[str] = mapped_column(String(80), default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    equipe: Mapped[Optional[Equipe]] = relationship()
    setor: Mapped[Optional[Setor]] = relationship()

    @property
    def lista_perfis(self) -> list[str]:
        return [p.strip() for p in self.perfis.split(",") if p.strip()]


class Sessao(Base):
    __tablename__ = "sessoes"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime)


# ---------------------------------------------------------------- integração
class SistemaOrigem(Base):
    __tablename__ = "sistemas_origem"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(120))
    api_key: Mapped[str] = mapped_column(String(80))            # sistema -> plataforma
    webhook_url: Mapped[str] = mapped_column(String(300), default="")   # plataforma -> sistema
    webhook_key: Mapped[str] = mapped_column(String(80), default="")
    setor_padrao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("setores.id"), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Outbox(Base):
    """Fila de atualizações a devolver ao sistema de origem. Sobrevive a quedas; entrega ordenada e idempotente."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    sistema_id: Mapped[int] = mapped_column(ForeignKey("sistemas_origem.id"))
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"))
    chave: Mapped[str] = mapped_column(String(80), unique=True)   # idempotência no destino
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="pendente")  # pendente|enviado
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    proxima_tentativa: Mapped[datetime] = mapped_column(DateTime, default=agora)
    ultimo_erro: Mapped[str] = mapped_column(String(300), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    enviado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_outbox_status", "status", "proxima_tentativa"),)


# ---------------------------------------------------------------- tarefas
class Tarefa(Base):
    __tablename__ = "tarefas"
    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    tipo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tipos_tarefa.id"), nullable=True)
    setor_id: Mapped[int] = mapped_column(ForeignKey("setores.id"))            # setor que EXECUTA
    equipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipes.id"), nullable=True)
    local: Mapped[str] = mapped_column(String(250), default="")
    unidade_demandante: Mapped[str] = mapped_column(String(200), default="")   # ex.: UPA Afonso Pena
    solicitante_nome: Mapped[str] = mapped_column(String(120), default="")
    solicitante_contato: Mapped[str] = mapped_column(String(80), default="")
    demandante_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    atendente_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="NOVA", index=True)
    prioridade: Mapped[str] = mapped_column(String(10), default="normal")      # baixa|normal|alta|urgente
    complexidade: Mapped[str] = mapped_column(String(10), default="media")
    # vínculo com o registro de origem (Requisito 2)
    origem_sistema_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sistemas_origem.id"), nullable=True)
    origem_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atribuido_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    iniciado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    concluido_exec_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolvido_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bloqueada_min: Mapped[int] = mapped_column(Integer, default=0)             # tempo total bloqueada (SLA congelado)
    token_validacao: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    avaliacao: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comentario_avaliacao: Mapped[str] = mapped_column(Text, default="")
    reaberturas: Mapped[int] = mapped_column(Integer, default=0)
    ia_sugestao: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)                    # campos livres vindos do legado

    tipo: Mapped[Optional[TipoTarefa]] = relationship()
    setor: Mapped[Setor] = relationship()
    equipe: Mapped[Optional[Equipe]] = relationship()
    origem_sistema: Mapped[Optional[SistemaOrigem]] = relationship()
    participantes: Mapped[list["Participante"]] = relationship(back_populates="tarefa", cascade="all, delete-orphan")
    eventos: Mapped[list["Evento"]] = relationship(back_populates="tarefa", cascade="all, delete-orphan",
                                                   order_by="Evento.id")
    impedimentos: Mapped[list["Impedimento"]] = relationship(back_populates="tarefa", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("origem_sistema_id", "origem_id", name="uq_origem"),)  # sem duplicidade


class Participante(Base):
    __tablename__ = "participantes"
    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    papel: Mapped[str] = mapped_column(String(10), default="principal")   # principal|apoio
    desde: Mapped[datetime] = mapped_column(DateTime, default=agora)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    tarefa: Mapped[Tarefa] = relationship(back_populates="participantes")
    usuario: Mapped[Usuario] = relationship()
    __table_args__ = (UniqueConstraint("tarefa_id", "usuario_id"),)


class Evento(Base):
    """Trilha de auditoria: quem, quando, o quê. Nunca é editada nem apagada."""
    __tablename__ = "eventos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    ator: Mapped[str] = mapped_column(String(120), default="")      # nome no momento do evento (ou 'sistema'/'demandante')
    texto: Mapped[str] = mapped_column(Text, default="")
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    tarefa: Mapped[Tarefa] = relationship(back_populates="eventos")
    evidencias: Mapped[list["Evidencia"]] = relationship(back_populates="evento", cascade="all, delete-orphan")


class Evidencia(Base):
    __tablename__ = "evidencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"), index=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"))
    arquivo: Mapped[str] = mapped_column(String(200))
    nome_original: Mapped[str] = mapped_column(String(200), default="")
    mime: Mapped[str] = mapped_column(String(80), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    evento: Mapped[Evento] = relationship(back_populates="evidencias")


class Impedimento(Base):
    __tablename__ = "impedimentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))           # material|terceiro|acesso|apoio|divergencia|outro
    descricao: Mapped[str] = mapped_column(Text, default="")
    aberto_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    aberto_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    resolvido_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolvido_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    resolucao: Mapped[str] = mapped_column(Text, default="")
    tarefa: Mapped[Tarefa] = relationship(back_populates="impedimentos")


# ---------------------------------------------------------------- gamificação
class Config(Base):
    __tablename__ = "config"
    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSON)


class Periodo(Base):
    """Placar periódico. Reiniciar = fechar o período e abrir outro; o histórico (ledger) nunca é apagado."""
    __tablename__ = "periodos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    inicio: Mapped[datetime] = mapped_column(DateTime, default=agora)
    fim: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class PontoEvento(Base):
    __tablename__ = "pontos"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    equipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipes.id"), nullable=True)
    setor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("setores.id"), nullable=True)
    tarefa_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tarefas.id"), nullable=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    pontos: Mapped[float] = mapped_column(Float)
    explicacao: Mapped[str] = mapped_column(String(300), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class Conquista(Base):
    __tablename__ = "conquistas"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40))
    concedida_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    __table_args__ = (UniqueConstraint("usuario_id", "codigo"),)


# ---------------------------------------------------------------- notificações
class Notificacao(Base):
    __tablename__ = "notificacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    corpo: Mapped[str] = mapped_column(String(400), default="")
    tarefa_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tarefas.id"), nullable=True)
    lida: Mapped[bool] = mapped_column(Boolean, default=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class PushSub(Base):
    __tablename__ = "push_subs"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(600), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
