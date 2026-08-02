-- +migrate Up
CREATE TABLE commande_nouveau (
  id INTEGER PRIMARY KEY,
  utilisateur_id INTEGER NOT NULL,
  statut TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  CONSTRAINT commande_utilisateur_fk FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id),
  CONSTRAINT commande_statut_check CHECK (statut IN ('brouillon','validee','annulee'))
);
INSERT INTO commande_nouveau SELECT * FROM commande;
DROP TABLE commande;
ALTER TABLE commande_nouveau RENAME TO commande;

-- +migrate Down
CREATE TABLE commande_ancien (
  id INTEGER PRIMARY KEY,
  utilisateur_id INTEGER NOT NULL,
  statut TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  CONSTRAINT commande_utilisateur_fk FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id)
);
INSERT INTO commande_ancien SELECT * FROM commande;
DROP TABLE commande;
ALTER TABLE commande_ancien RENAME TO commande;
