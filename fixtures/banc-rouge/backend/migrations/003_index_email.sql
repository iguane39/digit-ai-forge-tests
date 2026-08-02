-- +migrate Up
CREATE UNIQUE INDEX utilisateur_email_idx ON utilisateur (email);
