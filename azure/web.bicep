// Static Web App hosting the built React frontend (web/dist).
//
// Free tier — no cost when idle. Deployment of the built dist/ content happens out-of-band
// (via `swa deploy` or the Static Web Apps GitHub Action, see azure/README.md); this template
// only provisions the resource.
param location string
param staticWebAppName string = 'cgp-web'
param apiFqdn string

resource staticWebApp 'Microsoft.Web/staticSites@2024-04-01' = {
  name: staticWebAppName
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    // web/staticwebapp.config.json (checked into the repo) routes /api/* here at build/deploy
    // time via the Static Web Apps linked-backend mechanism — this output just documents the
    // Container App FQDN the app expects.
    stagingEnvironmentPolicy: 'Disabled'
  }
}

output staticWebAppDefaultHostname string = staticWebApp.properties.defaultHostname
output linkedApiFqdn string = apiFqdn
