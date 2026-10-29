-- +migrate Up
-- Banc VERT de la fabrique de données (TF-2012) : un schéma à clés étrangères et à
-- vérifications que la fabrique sait tenir. Le jeu fabriqué doit s y charger sans un seul rejet.
CREATE TYPE statut_commande AS ENUM ('brouillon', 'validee', 'livree');

CREATE TABLE client (
  id SERIAL PRIMARY KEY,
  courriel TEXT NOT NULL,
  nom_affiche VARCHAR(60) NOT NULL CHECK (char_length(trim(nom_affiche)) > 0),
  niveau SMALLINT NOT NULL DEFAULT 1,
  parrain_id INTEGER REFERENCES client (id),
  inscrit_le DATE NOT NULL,
  CONSTRAINT client_courriel_unique UNIQUE (courriel),
  CONSTRAINT client_niveau_borne CHECK (niveau BETWEEN 1 AND 5)
);

CREATE TABLE produit (
  code CHAR(6) PRIMARY KEY,
  libelle VARCHAR(40) NOT NULL,
  prix NUMERIC(8, 2) NOT NULL CHECK (prix > 0 AND prix <= 999.99),
  categorie TEXT NOT NULL CHECK (categorie IN ('entree', 'plat', 'dessert')),
  actif BOOLEAN NOT NULL DEFAULT TRUE
);

-- +migrate Down
DROP TABLE produit;
DROP TABLE client;
DROP TYPE statut_commande;
