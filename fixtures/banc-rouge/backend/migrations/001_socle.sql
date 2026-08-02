-- +migrate Up
CREATE TABLE utilisateur (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL,
  mot_de_passe_hash TEXT NOT NULL,
  actif INTEGER DEFAULT 1,
  CONSTRAINT utilisateur_email_unique UNIQUE (email)
);
CREATE TABLE commande (
  id INTEGER PRIMARY KEY,
  utilisateur_id INTEGER NOT NULL,
  statut TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  CONSTRAINT commande_utilisateur_fk FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id)
);
CREATE TABLE ligne_commande (
  id INTEGER PRIMARY KEY,
  commande_id INTEGER NOT NULL,
  plat TEXT NOT NULL,
  quantite INTEGER NOT NULL,
  CONSTRAINT ligne_commande_commande_fk FOREIGN KEY (commande_id) REFERENCES commande (id)
);

-- +migrate Down
DROP TABLE ligne_commande;
DROP TABLE commande;
DROP TABLE utilisateur;
