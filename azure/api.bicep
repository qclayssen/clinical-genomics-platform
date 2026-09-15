// Container App hosting the FastAPI service (api/).
//
// Fixture-backed by default — CGP_DB_URL is an optional secure param, left empty unless the
// deployer sets it, matching api/main.py's existing local-run behaviour (no DB required).
param location string
param containerAppEnvId string
param containerAppName string = 'cgp-api'
param containerImage string
@secure()
param cgpDbUrl string = ''

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnvId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: empty(cgpDbUrl) ? [] : [
        {
          name: 'cgp-db-url'
          value: cgpDbUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: empty(cgpDbUrl) ? [] : [
            {
              name: 'CGP_DB_URL'
              secretRef: 'cgp-db-url'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

output apiFqdn string = containerApp.properties.configuration.ingress.fqdn
