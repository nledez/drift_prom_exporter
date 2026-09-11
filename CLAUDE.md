# drift_prom_exporter

Prometheus exporter qui surveille l'expiration (drift) de tokens Vault, accessors Vault et certificats TLS.

## Stack

- Python 3.14, gestion des deps avec UV
- Libs : hvac, prometheus-client, pyopenssl, pyyaml
- Docker multi-stage (uv + python slim)
- Pas de tests automatises

## Structure

- `main.py` : tout le code (collecte, lookup, metriques, boucle principale)
- `drift_prom_exporter.yml.sample` : exemple de config
- `Makefile` : build/run Docker, run local via virtualenv
- `Dockerfile` : image basee sur uv + python slim
- `pyproject.toml` : deps UV

## Configuration

Fichier YAML avec les sections :
- `vault.server` / `vault.verify` : connexion Vault
- `tokens` : map nom -> client_token (lookup direct)
- `accessors` : map nom -> accessor (lookup via VAULT_TOKEN)
- `tls` : map nom -> {fqdn, port} (certificats internes)
- `tls_le` : map nom -> {fqdn, port} (certificats publics)

## Variables d'environnement

- `CONFIG` : chemin vers le fichier YAML (sinon argv[1])
- `PORT` : port HTTP (defaut 8000)
- `INTERVAL` : intervalle de scrape en secondes (defaut 300)
- `VAULT_TOKEN` : token pour les lookups d'accessors

## Metriques exposees

- `token_drift_seconds` / `token_drift_days` : tokens + accessors (fusionnes)
- `certificate_drift_seconds` / `certificate_drift_days` : certificats TLS
- `public_certificate_drift_seconds` / `public_certificate_drift_days` : certificats publics

## Conventions

- Pas de classes, tout en fonctions
- Pattern repete : collect_*_drift() -> lookup_*() -> calcul drift en s/d
- Valeur -1 quand le lookup echoue
- Les exceptions Vault (Unauthorized, Forbidden) sont catchees silencieusement
