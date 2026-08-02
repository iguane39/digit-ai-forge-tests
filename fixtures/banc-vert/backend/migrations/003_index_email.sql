-- +migrate Up
CREATE UNIQUE INDEX utilisateur_email_idx ON utilisateur (email);

-- +migrate Down
DROP INDEX utilisateur_email_idx;
