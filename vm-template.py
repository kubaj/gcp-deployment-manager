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

  baseName = '-'.join([context.env['deployment'], context.env['name']])

  serviceAccountName = '-'.join([baseName, 'service-account'])

  # Create a service account
  resources.append({
      'name': serviceAccountName,
      'type': 'iam.v1.serviceAccount',
      'properties': {
        'name': '/'.join(['projects', '-', 'serviceAccounts', '-']),
        'accountId': '-'.join([baseName, 'deployment']),
        'displayName': '-'.join([baseName, 'deployment'])
      }
  })

  clusterName = '-'.join([baseName, 'gke-cluster'])

  # Create a cluster with the service account
  resources.append({
    'name': clusterName,
    'type': 'container.v1.cluster',
    'properties': {
      'zone': context.properties['zone'],
      'cluster': {
        'name': clusterName,
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

  configName = '-'.join([clusterName, 'config'])

  resources.append({
    'name': configName,
    'type': 'runtimeconfig.v1beta1.config',
    'properties': {
      'config': configName,
    }
  })

  waiterName = '-'.join([clusterName, 'waiter'])

  resources.append({
    'name': waiterName,
    'metadata': {
      'dependsOn': [ configName ]
    },
    'type': 'runtimeconfig.v1beta1.waiter',
    'properties': {
      'parent': '$(ref.' + configName + '.name)',
      'timeout': '600s',
      'waiter': waiterName,
      'success': {
        'cardinality': {
          'path': '/success',
          'number': 1
        }
      },
      'failure': {
          'cardinality': {
            'path': '/failure',
            'number': 1
          }
        }
      }
  })

  # Create a VM instance that will setup Helm and Istio on the cluster
  resources.append({
    'name': '-'.join([clusterName, 'setup-vm']),
    'type': 'compute.v1.instance',
    'metadata': {
      'dependsOn': [ clusterName ]
    },
    'properties': {
      'zone': context.properties['zone'],
      'machineType': ZonalComputeUrl(
        context.env['project'],
        context.properties['zone'],
        'machineTypes',
        'n1-standard-1'
      ),
      'networkInterfaces': [{
        'network': ''.join([COMPUTE_URL_BASE, 'projects/', context.env['project'], '/global/networks/default']),
        'accessConfigs': [{
          'name': 'External NAT',
          'type': 'ONE_TO_ONE_NAT'} ],
      }],
      'disks': [
        {
          'deviceName': 'boot',
          'type': 'PERSISTENT',
          'boot': True,
          'autoDelete': True,
          'initializeParams': {
            'diskName': '-'.join([context.env['deployment'], 'vm-disk']),
            'sourceImage': ''.join([COMPUTE_URL_BASE, 'projects/debian-cloud/global/images/family/debian-8'])
          }
        }
      ],
      'serviceAccounts': [{
        'email': 'default',
        'scopes': [
          'https://www.googleapis.com/auth/cloud-platform',
          'https://www.googleapis.com/auth/compute',
          'https://www.googleapis.com/auth/logging.write',
          'https://www.googleapis.com/auth/monitoring',
          'https://www.googleapis.com/auth/servicecontrol',
          'https://www.googleapis.com/auth/service.management.readonly',
          'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/cloud-platform'
        ]
      }],
      'metadata': {
        'items': [
          {
            'key': 'startup-script',
            'value': ''.join([
              '#!/bin/bash -x\n',
              'set -e\n',
              'apt-get update && apt-get install -y git google-cloud-sdk curl kubectl\n',
              'export HOME=/root\n',
              'cd /root/\n',
              'gcloud container clusters get-credentials {clusterName} --zone {zone}\n',
              'kubectl create clusterrolebinding cluster-admin-binding --clusterrole=cluster-admin --user=$(gcloud config get-value core/account)\n',
              'curl -L https://raw.githubusercontent.com/istio/istio/master/release/downloadIstioCandidate.sh | ISTIO_VERSION={version} sh -\n',
              'wget https://github.com/istio/istio/releases/download/{version}/istio-{version}-linux.tar.gz\n',
              'tar xzf istio-{version}-linux.tar.gz\n',
              'wget -P /root/helm/ https://storage.googleapis.com/kubernetes-helm/helm-v2.9.1-linux-amd64.tar.gz\n',
              'tar xf /root/helm/helm-v2.9.1-linux-amd64.tar.gz  -C /root/helm/\n',
              'export PATH="$PATH:/root/istio-{version}/bin::/root/helm/linux-amd64/"\n',
              'cd /root/istio-{version}\n',
              'kubectl create ns istio-system\n',
              'ISTIO_OPTIONS=" --set global.proxy.image=proxyv2 "\n',
              '{tls}',
              '{grafana}',
              '{prometheus}',
              '{tracing}',
              '{serviceGraph}',
              "IP_RANGES_WHITELIST=$(gcloud container clusters describe {clusterName} --zone={zone} | grep -e clusterIpv4Cidr -e servicesIpv4Cidr | awk '{{print $2}}' | sed ':a;N;$!ba;s/\\n/\\\\,/g')\n",
              'ISTIO_OPTIONS=$ISTIO_OPTIONS" --set global.proxy.includeIPRanges=\\\""$IP_RANGES_WHITELIST"\\\""\n',
              'helm template install/kubernetes/helm/istio --name istio --namespace istio-system $ISTIO_OPTIONS  > istio.yaml\n',
              'kubectl apply -f istio.yaml\n',
              'kubectl label namespace default istio-injection=enabled\n',
              'gcloud beta runtime-config configs variables set success/{clusterName}-waiter success --config-name $(ref.{clusterName}-config.name)\n',
              'gcloud -q compute instances delete {clusterName}-setup-vm --zone {zone}'
            ]).format(
              clusterName=clusterName,
              zone=context.properties["zone"],
              version=context.properties["istio"]['version'],
              tls="" if not context.properties["istio"]['enableMutualTLS'] else "ISTIO_OPTIONS=$ISTIO_OPTIONS\" --set global.mtls.enabled=true\"\n",
              grafana="" if not context.properties["istio"]['enableGrafana'] else "ISTIO_OPTIONS=$ISTIO_OPTIONS\" --set grafana.enabled=true\"\n",
              prometheus="" if not context.properties["istio"]['enablePrometheus'] else "ISTIO_OPTIONS=$ISTIO_OPTIONS\" --set prometheus.enabled=true\"\n",
              tracing="" if not context.properties["istio"]['enableTracing'] else "ISTIO_OPTIONS=$ISTIO_OPTIONS\" --set tracing.enabled=true\"\n",
              serviceGraph="" if not context.properties["istio"]['enableServiceGraph'] else "ISTIO_OPTIONS=$ISTIO_OPTIONS\" --set servicegraph.enabled=true\"\n"
            )
          }
        ]
      }
    }      
  })                

  """ gcloud container clusters describe dev --zone=europe-west2-b | grep -e clusterIpv4Cidr -e servicesIpv4Cidr | awk '{print $2}' | paste -sd "," -
  """

  return {'resources': resources}