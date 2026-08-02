"""Suite Data couvrante : les 8 contraintes hors clés primaires, exercées PAR VIOLATION."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Commande, LigneCommande, Utilisateur


@pytest.fixture()
def session() -> Session:
    moteur = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(moteur, "connect")
    def _fk(dbapi_connection, _record) -> None:  # noqa: ANN001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(moteur)
    with Session(moteur) as s:
        yield s


def _utilisateur(s: Session, email: str = "a@b.fr") -> Utilisateur:
    u = Utilisateur(email=email, mot_de_passe_hash="h")
    s.add(u)
    s.commit()
    return u


# C1 — utilisateur_email_unique
def test_email_unique_viole(session: Session) -> None:
    _utilisateur(session)
    session.add(Utilisateur(email="a@b.fr", mot_de_passe_hash="h2"))
    with pytest.raises(IntegrityError):
        session.commit()


# C2 — utilisateur.email NOT NULL
def test_email_non_nul_viole(session: Session) -> None:
    session.add(Utilisateur(email=None, mot_de_passe_hash="h"))
    with pytest.raises(IntegrityError):
        session.commit()


# C3 — utilisateur.mot_de_passe_hash NOT NULL
def test_mot_de_passe_non_nul_viole(session: Session) -> None:
    session.add(Utilisateur(email="c@d.fr", mot_de_passe_hash=None))
    with pytest.raises(IntegrityError):
        session.commit()


# C4 — commande_utilisateur_fk
def test_commande_utilisateur_fk_viole(session: Session) -> None:
    session.add(Commande(utilisateur_id=9999, statut="brouillon", cree_le="2026-08-02"))
    with pytest.raises(IntegrityError):
        session.commit()


# C5 — commande_statut_check
def test_commande_statut_check_viole(session: Session) -> None:
    u = _utilisateur(session, "e@f.fr")
    session.add(Commande(utilisateur_id=u.id, statut="zzz", cree_le="2026-08-02"))
    with pytest.raises(IntegrityError):
        session.commit()


# C6 — commande.cree_le NOT NULL
def test_commande_cree_le_non_nul_viole(session: Session) -> None:
    u = _utilisateur(session, "g@h.fr")
    session.add(Commande(utilisateur_id=u.id, statut="brouillon", cree_le=None))
    with pytest.raises(IntegrityError):
        session.commit()


# C7 — ligne_commande_commande_fk
def test_ligne_commande_fk_viole(session: Session) -> None:
    session.add(LigneCommande(commande_id=9999, plat="curry", quantite=1))
    with pytest.raises(IntegrityError):
        session.commit()


# C8 — ligne_commande_quantite_positive
def test_quantite_positive_viole(session: Session) -> None:
    u = _utilisateur(session, "i@j.fr")
    c = Commande(utilisateur_id=u.id, statut="brouillon", cree_le="2026-08-02")
    session.add(c)
    session.commit()
    session.add(LigneCommande(commande_id=c.id, plat="curry", quantite=0))
    with pytest.raises(IntegrityError):
        session.commit()
