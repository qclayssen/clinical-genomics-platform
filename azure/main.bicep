// Top-level Azure deployment for the Clinical Genomics Insight Platform's REST API + React
// frontend (api/, web/) — additive to, and entirely separate from, the AWS CDK infra in
// ../infra/ which hosts the genomics pipeline's data lake, orchestration, and demo hosting.
//
// Deploy with:
//   az deployment group create --resource-group <rg> --template-file main.bicep \
//     --parameters containerImage=<registry>/cgp-api:<tag>
//
// See ./README.md for the full walkthrough. Not run by CI — CI only validates the template
// compiles (`bicep build`), the same stance ../infra/'s CI takes toward `cdk synth` vs. a real
// `cdk deploy`.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param containerImage string
@secure()
param cgpDbUrl string = ''

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cgp-env'
  location: location
  properties: {}
}

module api 'api.bicep' = {
  name: 'cgp-api-deployment'
  params: {
    location: location
    containerAppEnvId: containerAppEnv.id
    containerImage: containerImage
    cgpDbUrl: cgpDbUrl
  }
}

module web 'web.bicep' = {
  name: 'cgp-web-deployment'
  params: {
    location: location
    apiFqdn: api.outputs.apiFqdn
  }
}

output apiUrl string = 'https://${api.outputs.apiFqdn}'
output webUrl string = 'https://${web.outputs.staticWebAppDefaultHostname}'
