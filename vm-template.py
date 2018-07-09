"""Creates a Compute Engine Instance."""

COMPUTE_URL_BASE = 'https://www.googleapis.com/compute/v1/'

def GlobalComputeUrl(project, collection, name):
  return ''.join([COMPUTE_URL_BASE, 'projects/', project,
                  '/global/', collection, '/', name])


def ZonalComputeUrl(project, zone, collection, name):
  return ''.join([COMPUTE_URL_BASE, 'projects/', project,
                  '/zones/', zone, '/', collection, '/', name])

def GenerateConfig(context):
  """Generate configuration."""
  resources = []

  base_name = '-'.join([context.env['deployment'], context.env['name']])

  serviceAccountName = '-'.join([base_name, 'service-account'])

  # Create a service account
  resources.append({
      'name': serviceAccountName,
      'type': 'iam.v1.serviceAccount',
      'properties': {
        'name': '/'.join(['projects', '-', 'serviceAccounts', '-']),
        'accountId': '-'.join([base_name, 'deployment']),
        'displayName': '-'.join([base_name, 'deployment'])
      }
  })

  # Create a cluster with the service account
  resources.append({
    'name': '-'.join([base_name, 'gke-cluster']),
    'type': 'container.v1.cluster',
    'properties': {
      'zone': context.properties['zone'],
      'cluster': {
        'name': '-'.join([base_name, 'deployment']),
        'initialNodeCount': context.properties['nodeCount'],
        'initialClusterVersion': context.properties['clusterVersion'],
        'nodeConfig': {
          'machineType': context.properties['machineType'],
          'diskSizeGb': 20,
          'serviceAccount': '$(ref.' + serviceAccountName + '.email)',
          'preemptible': context.properties['preemptibleInstances'],
        }
      }
    }
  })

  # Create a VM instance that will setup Helm and Istio on the cluster
  # resources.append({
  #   'name': '-'.join([base_name, 'setup-vm']),
  #   'type': 'compute.v1.instance',
  #   'properties': {
  #     'zone': context.properties['zone'],
  #     'machineType': ZonalComputeUrl(
  #       context.env['project'],
  #       context.properties['zone'],
  #       'machineTypes',
  #       'n1-standard-1'
  #     ),
  #     'networkInterfaces': [{
  #       'network': ''.join([COMPUTE_URL_BASE, 'projects/', context.env['project'], '/global/networks/default']),
  #       'accessConfigs': [{
  #         'name': 'External NAT',
  #         'type': 'ONE_TO_ONE_NAT'} ],
  #     }],
  #     'serviceAccounts': [{
  #       'email': 'default',
  #       'scopes': [
  #         'https://www.googleapis.com/auth/cloud-platform',
  #         'https://www.googleapis.com/auth/compute',
  #         'https://www.googleapis.com/auth/logging.write',
  #         'https://www.googleapis.com/auth/monitoring',
  #         'https://www.googleapis.com/auth/servicecontrol',
  #         'https://www.googleapis.com/auth/service.management.readonly',
  #         'https://www.googleapis.com/auth/userinfo.email'
  #       ]
  #     }]
  #   }      
  # })                

  return {'resources': resources}