# Azure deployment

Deploys the existing REST API (`../api/`) as an Azure Container App and the React frontend
(`../web/`) as an Azure Static Web App. This is additive to, and entirely separate from, the AWS
CDK infra in `../infra/`, which hosts the genomics pipeline's data lake, orchestration, and demo
hosting — nothing here changes AWS resources.

**Needs a real Azure subscription.** CI (`.github/workflows/azure-ci.yml`) only runs
`bicep build`/`bicep lint` to catch template errors — it does not deploy, and no Azure
credentials are configured for this repository. The commands below are for you to run yourself
with `az login`, the same stance the AWS side takes toward `cdk deploy` (see `CLAUDE.md`).

## 1. Build and push the API image

```bash
docker build -f ../docker/Dockerfile.api -t <registry>/cgp-api:latest ..
docker push <registry>/cgp-api:latest
```

Any registry works (Azure Container Registry, GHCR, Docker Hub). If using ACR:

```bash
az acr create --resource-group <rg> --name <acrName> --sku Basic
az acr login --name <acrName>
docker tag cgp-api:latest <acrName>.azurecr.io/cgp-api:latest
docker push <acrName>.azurecr.io/cgp-api:latest
```

## 2. Deploy the infra

```bash
az login
az group create --name <rg> --location <region>
az deployment group create \
  --resource-group <rg> \
  --template-file main.bicep \
  --parameters containerImage=<acrName>.azurecr.io/cgp-api:latest
```

Optionally set `cgpDbUrl` to point the API at a live Postgres instance instead of the committed
demo fixtures (matches `api/main.py`'s `CGP_DB_URL` behaviour):

```bash
az deployment group create \
  --resource-group <rg> \
  --template-file main.bicep \
  --parameters containerImage=<acrName>.azurecr.io/cgp-api:latest cgpDbUrl=<postgres-conn-string>
```

## 3. Deploy the frontend build

Build `web/` and push `dist/` to the Static Web App the previous step provisioned:

```bash
cd ../web
npm ci
VITE_API_BASE_URL=https://<api-fqdn-from-step-2-output> npm run build
npx @azure/static-web-apps-cli deploy ./dist --deployment-token <token-from-portal-or-az-cli>
```

The browser now calls the API host cross-origin, so the API must allow the Static Web App's
origin. Re-run the step-2 deployment with it (the `webUrl` output of the first deploy):

```bash
az deployment group create --resource-group <rg> --template-file main.bicep \
  --parameters containerImage=<image> corsOrigins=https://<webUrl-host>
```

Alternatively, link the Container App as the Static Web App's backend so `/api/*` (per
`../web/staticwebapp.config.json`) proxies there without CORS setup:

```bash
az staticwebapp backends link \
  --name cgp-web \
  --resource-group <rg> \
  --backend-resource-id <container-app-resource-id> \
  --backend-region <region>
```

## 4. Verify

```bash
curl https://<api-fqdn>/healthz
open https://<static-web-app-hostname>
```

## Known limitations

- CI never runs a real `az deployment group create` — there is no signal that the templates
  actually provision successfully end-to-end, only that they compile. Same honest caveat already
  used for `BedrockBackend` in ADR-0028.
- `min replicas: 0` on the Container App means the first request after idle will cold-start.
