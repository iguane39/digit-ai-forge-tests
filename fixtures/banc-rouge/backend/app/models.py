"""Schéma relationnel du banc — 3 tables, 8 contraintes hors clés primaires."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

STATUTS = ("brouillon", "validee", "annulee")


class Utilisateur(Base):
    __tablename__ = "utilisateur"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    mot_de_passe_hash = Column(String, nullable=False)
    actif = Column(Integer, default=1)
    __table_args__ = (UniqueConstraint("email", name="utilisateur_email_unique"),)


class Commande(Base):
    __tablename__ = "commande"
    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(
        Integer, ForeignKey("utilisateur.id", name="commande_utilisateur_fk"), nullable=False
    )
    statut = Column(String, nullable=False)
    cree_le = Column(String, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "statut IN ('brouillon','validee','annulee')", name="commande_statut_check"
        ),
    )


class LigneCommande(Base):
    __tablename__ = "ligne_commande"
    id = Column(Integer, primary_key=True)
    commande_id = Column(
        Integer, ForeignKey("commande.id", name="ligne_commande_commande_fk"), nullable=False
    )
    plat = Column(String, nullable=False)
    quantite = Column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("quantite > 0", name="ligne_commande_quantite_positive"),
    )
