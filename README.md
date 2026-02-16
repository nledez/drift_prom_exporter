Launch it
=========

```
cp drift_prom_exporter.yml.sample drift_prom_exporter.yml
make docker_build
make docker_run
```


Test it
=======

```
make curl
```


Example
=======

```
curl http://127.0.0.1:8000 | grep -i drift
# HELP token_drift_seconds Seconds remind before token expiration
# TYPE token_drift_seconds gauge
token_drift_seconds{token="vaultbot"} 2.548082e+06
token_drift_seconds{token="apps"} 2.49488e+06
token_drift_seconds{token="prometheus"} 2.571535e+06
token_drift_seconds{token="transit-boundary"} -1.0
token_drift_seconds{token="token-lookup"} 2.746223e+06
# HELP token_drift_days Days remind before token expiration
# TYPE token_drift_days gauge
token_drift_days{token="vaultbot"} 29.0
token_drift_days{token="apps"} 28.0
token_drift_days{token="prometheus"} 29.0
token_drift_days{token="transit-boundary"} -1.0
token_drift_days{token="token-lookup"} 31.0
# HELP certificate_drift_seconds Seconds remind before certificate expiration
# TYPE certificate_drift_seconds gauge
certificate_drift_seconds{certificate="google"} 2.80579239e+08
certificate_drift_seconds{certificate="duckduckgo"} 2.3625639e+07
# HELP certificate_drift_days Days remind before certificate expiration
# TYPE certificate_drift_days gauge
certificate_drift_days{certificate="google"} 3247.0
certificate_drift_days{certificate="duckduckgo"} 273.0
```


Accessors
=========

Instead of storing `client_token` in plain text in the configuration, you can use Vault accessors to monitor token expiration. This requires a `VAULT_TOKEN` environment variable set with a token that has the `accessor-lookup` policy.

Create the following Vault policy:

```hcl
path "auth/token/lookup-accessor" {
  capabilities = ["update"]
}
```

Apply it:

```
vault policy write accessor-lookup accessor-lookup.hcl
```

Then add an `accessors` section to your configuration file:

```yaml
accessors:
  my-app: "accessor_abc123..."
  my-service: "accessor_def456..."
```

And export the `VAULT_TOKEN`:

```
export VAULT_TOKEN=s.mytoken
```


Prometheus configuration
========================

Add this to your Prometheus configuration:

```
scrape_configs:
  - job_name: drift_prom_exporter
    scheme: http
    static_configs:
      - targets: ["127.0.0.1:8000"]
    scrape_interval: 60s
    params:
      format: ["prometheus"]
```


Grafana
=======

You can import `grafana_drift.json` dashboard in your Grafana. Now you can have their graph:

![Token drift in days](sc_tokens_in_days.png)

![Certificate drift in seconds](sc_certificates_in_seconds.png)


Release
=======

1. Update `VERSION` (and `pyproject.toml` version field)
2. Commit and push
3. `git tag v<version>` then `git push origin v<version>`
4. GitHub Actions builds and pushes the Docker image automatically
