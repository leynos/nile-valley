package tests

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
)

func TestCNPGModuleValidate(t *testing.T) {
	t.Parallel()
	_, opts := setup(t, testVars(t))
	terraform.InitAndValidate(t, opts)
}

func TestCNPGModuleRenderOutputs(t *testing.T) {
	t.Parallel()

	_, opts := setupRender(t, renderVars(t))
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	// Check operator HelmRelease
	helmRelease, ok := rendered["platform/databases/cnpg-operator-helmrelease.yaml"]
	require.True(t, ok, "expected platform/databases/cnpg-operator-helmrelease.yaml output key")
	require.True(
		t,
		strings.Contains(helmRelease, "kind: HelmRelease") ||
			strings.Contains(helmRelease, "\"kind\": \"HelmRelease\""),
		"expected HelmRelease manifest to contain kind HelmRelease",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "cloudnative-pg") ||
			strings.Contains(helmRelease, "\"cloudnative-pg\""),
		"expected HelmRelease manifest to reference cloudnative-pg",
	)

	// Check HelmRepository
	_, ok = rendered["platform/sources/cloudnative-pg-repo.yaml"]
	require.True(t, ok, "expected platform/sources/cloudnative-pg-repo.yaml output key")

	// Check Cluster
	cluster, ok := rendered["platform/databases/nile-valley-pg-cluster.yaml"]
	require.True(t, ok, "expected cluster manifest output")
	require.True(
		t,
		strings.Contains(cluster, "kind: Cluster") ||
			strings.Contains(cluster, "\"kind\": \"Cluster\""),
		"expected Cluster manifest to contain kind Cluster",
	)
	require.True(
		t,
		strings.Contains(cluster, "postgis") ||
			strings.Contains(cluster, "\"postgis\""),
		"expected Cluster to reference postgis image",
	)

	// Check PDB for HA cluster (instances > 1)
	_, ok = rendered["platform/databases/pdb-cnpg-cluster.yaml"]
	require.True(t, ok, "expected PDB manifest for HA cluster")

	// Check namespaces
	_, ok = rendered["platform/databases/namespace-cnpg-system.yaml"]
	require.True(t, ok, "expected operator namespace manifest")

	_, ok = rendered["platform/databases/namespace-databases.yaml"]
	require.True(t, ok, "expected cluster namespace manifest")

	// Check kustomization
	_, ok = rendered["platform/databases/kustomization.yaml"]
	require.True(t, ok, "expected kustomization output")
}

func TestCNPGModuleRenderWithBackup(t *testing.T) {
	t.Parallel()

	_, opts := setupRender(t, renderVarsWithBackup(t))
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	// Check cluster includes backup configuration
	cluster, ok := rendered["platform/databases/nile-valley-pg-cluster.yaml"]
	require.True(t, ok, "expected cluster manifest output")
	require.True(
		t,
		strings.Contains(cluster, "barmanObjectStore") ||
			strings.Contains(cluster, "\"barmanObjectStore\""),
		"expected Cluster to include backup configuration",
	)

	// Check S3 credentials secret
	_, ok = rendered["platform/databases/s3-credentials-secret.yaml"]
	require.True(t, ok, "expected S3 credentials secret manifest")

	// Check scheduled backup
	_, ok = rendered["platform/databases/scheduled-backup.yaml"]
	require.True(t, ok, "expected scheduled backup manifest")
}

func TestCNPGModuleSyncPolicyContract(t *testing.T) {
	t.Parallel()

	_, opts := setupRender(t, renderVars(t))
	terraform.InitAndApply(t, opts)

	contract := terraform.OutputMap(t, opts, "sync_policy_contract")
	require.NotEmpty(t, contract, "expected sync_policy_contract output")

	// Verify required contract keys exist
	requiredKeys := []string{"cluster", "endpoints", "database", "credentials", "postgis_enabled"}
	for _, key := range requiredKeys {
		_, ok := contract[key]
		require.True(t, ok, "sync_policy_contract missing required key: %s", key)
	}
}

func TestCNPGModuleEndpoints(t *testing.T) {
	t.Parallel()

	_, opts := setupRender(t, renderVars(t))
	terraform.InitAndApply(t, opts)

	primary := terraform.Output(t, opts, "primary_endpoint")
	require.NotEmpty(t, primary, "expected primary_endpoint output")
	require.Contains(t, primary, "-rw.", "expected primary endpoint to contain -rw suffix")

	replica := terraform.Output(t, opts, "replica_endpoint")
	require.NotEmpty(t, replica, "expected replica_endpoint output")
	require.Contains(t, replica, "-ro.", "expected replica endpoint to contain -ro suffix")
}

func TestCNPGModuleRenderWithESO(t *testing.T) {
	t.Parallel()

	_, opts := setupRender(t, renderVarsWithESO(t))
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	// Verify ExternalSecret for superuser credentials is rendered
	superuserES, ok := rendered["platform/databases/external-secret-superuser.yaml"]
	require.True(t, ok, "expected external-secret-superuser.yaml when ESO enabled")
	require.Contains(t, superuserES, "ExternalSecret", "expected ExternalSecret kind")
	require.Contains(t, superuserES, "vault-backend", "expected ClusterSecretStore reference")

	// Verify ExternalSecret for app credentials is rendered
	appES, ok := rendered["platform/databases/external-secret-app.yaml"]
	require.True(t, ok, "expected external-secret-app.yaml when ESO enabled")
	require.Contains(t, appES, "ExternalSecret", "expected ExternalSecret kind")

	// Verify cluster references the superuser secret
	cluster, ok := rendered["platform/databases/nile-valley-pg-cluster.yaml"]
	require.True(t, ok, "expected cluster manifest")
	require.Contains(t, cluster, "superuserSecret", "cluster should reference superuserSecret when ESO enabled")
}

func TestCNPGModuleRenderWithoutESO(t *testing.T) {
	t.Parallel()

	// Use default renderVars which has eso_enabled=false (default)
	_, opts := setupRender(t, renderVars(t))
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	// Verify no ExternalSecret manifests are rendered when ESO is disabled
	_, hasSuperuserES := rendered["platform/databases/external-secret-superuser.yaml"]
	require.False(t, hasSuperuserES, "should not render external-secret-superuser.yaml when ESO disabled")

	_, hasAppES := rendered["platform/databases/external-secret-app.yaml"]
	require.False(t, hasAppES, "should not render external-secret-app.yaml when ESO disabled")

	// Verify cluster does NOT reference superuserSecret when ESO is disabled
	cluster, ok := rendered["platform/databases/nile-valley-pg-cluster.yaml"]
	require.True(t, ok, "expected cluster manifest")
	require.NotContains(t, cluster, "superuserSecret", "cluster should not reference superuserSecret when ESO disabled")
}

func TestCNPGModuleRenderPolicy(t *testing.T) {
	t.Parallel()
	requireBinary(t, binaryRequirement{Binary: "conftest", SkipMessage: "conftest not found; skipping policy test"})

	tfDir, opts := setupRender(t, renderVars(t))
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	outDir := filepath.Join(tfDir, "rendered")
	require.NoError(t, os.MkdirAll(outDir, 0o755))
	t.Cleanup(func() { _ = os.RemoveAll(outDir) })

	for relPath, content := range rendered {
		dest := filepath.Join(outDir, relPath)
		require.NoError(t, os.MkdirAll(filepath.Dir(dest), 0o755))
		require.NoError(t, os.WriteFile(dest, []byte(content), 0o600))
	}

	policyPath := cnpgManifestsPolicyPath(tfDir)
	out, err := runConftest(t, conftestRun{
		InputPath:  outDir,
		PolicyPath: policyPath,
		Kubeconfig: "",
		ExtraArgs: []string{
			"--namespace",
			cnpgPolicyManifestsNamespace,
			"--combine",
		},
		Timeout: 60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

var renderPolicyRejectionTestCases = []struct {
	name            string
	manifest        string
	expectedMessage string
}{
	{
		name: "MissingChartVersion",
		manifest: `apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: cloudnative-pg
  namespace: cnpg-system
  labels:
    app.kubernetes.io/part-of: cloudnative-pg
spec:
  chart:
    spec:
      chart: cloudnative-pg
      sourceRef:
        kind: HelmRepository
        name: cloudnative-pg
        namespace: flux-system
`,
		expectedMessage: "must pin chart.spec.version",
	},
	{
		name: "ClusterMissingInstances",
		manifest: `apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: test-cluster
  namespace: databases
  labels:
    app.kubernetes.io/part-of: cloudnative-pg
spec:
  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4
  storage:
    size: 10Gi
    storageClass: do-block-storage
  bootstrap:
    initdb:
      database: testdb
      owner: testuser
`,
		expectedMessage: "must set spec.instances > 0",
	},
	{
		name: "ClusterMissingStorageClass",
		manifest: `apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: test-cluster
  namespace: databases
  labels:
    app.kubernetes.io/part-of: cloudnative-pg
spec:
  instances: 3
  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4
  storage:
    size: 10Gi
  bootstrap:
    initdb:
      database: testdb
      owner: testuser
`,
		expectedMessage: "must set spec.storage.storageClass",
	},
	{
		name: "ClusterMissingStorageSize",
		manifest: `apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: test-cluster
  namespace: databases
  labels:
    app.kubernetes.io/part-of: cloudnative-pg
spec:
  instances: 3
  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4
  storage:
    storageClass: do-block-storage
  bootstrap:
    initdb:
      database: testdb
      owner: testuser
`,
		expectedMessage: "must set spec.storage.size",
	},
	{
		name: "ClusterMissingBootstrap",
		manifest: `apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: test-cluster
  namespace: databases
  labels:
    app.kubernetes.io/part-of: cloudnative-pg
spec:
  instances: 3
  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4
  storage:
    size: 10Gi
    storageClass: do-block-storage
`,
		expectedMessage: "must have spec.bootstrap configuration",
	},
}

func TestCNPGModuleRenderPolicyRejections(t *testing.T) {
	t.Parallel()
	requireBinary(t, binaryRequirement{Binary: "conftest", SkipMessage: "conftest not found; skipping policy test"})

	tfDir, opts := setupRender(t, renderVars(t))
	terraform.Init(t, opts)
	policyPath := cnpgManifestsPolicyPath(tfDir)

	for _, tc := range renderPolicyRejectionTestCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			tmpDir := t.TempDir()
			manifestPath := filepath.Join(tmpDir, "manifest.yaml")
			require.NoError(t, os.WriteFile(manifestPath, []byte(tc.manifest), 0o600))

			out, err := runConftest(t, conftestRun{
				InputPath:  manifestPath,
				PolicyPath: policyPath,
				Kubeconfig: "",
				ExtraArgs: []string{
					"--fail-on-warn",
					"--namespace",
					cnpgPolicyManifestsNamespace,
				},
				Timeout: 60 * time.Second,
			})
			require.Error(t, err, "expected conftest to report a violation")
			require.Contains(t, string(out), tc.expectedMessage)
		})
	}
}
