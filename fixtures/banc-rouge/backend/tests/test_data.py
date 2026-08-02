"""Suite Data."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Commande, LigneCommande, Utilisateur


@pytest.fixture()
def session() -> Session:
    moteur = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(moteur)
    with Session(moteur) as s:
        yield s


def test_insertion_nominale(session: Session) -> None:
    u = Utilisateur(email="a@b.fr", mot_de_passe_hash="h")
    session.add(u)
    session.commit()
    c = Commande(utilisateur_id=u.id, statut="brouillon", cree_le="2026-08-02")
    session.add(c)
    session.commit()
    session.add(LigneCommande(commande_id=c.id, plat="curry", quantite=2))
    session.commit()
    assert session.query(LigneCommande).count() == 1
