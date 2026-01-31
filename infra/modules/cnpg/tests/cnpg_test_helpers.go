package tests

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

const exampleKubeconfigError = "Set kubeconfig_path to a readable kubeconfig file before running the example"

const cnpgPolicyManifestsNamespace = "cnpg.policy.manifests"

type binaryRequirement struct {
	Binary      string
	SkipMessage string
}

type envVarRequirement struct {
	Key         string
	SkipMessage string
}

func testVars(t *testing.T) map[string]interface{} {
	t.Helper()
	kubeconfigDir := t.TempDir()
	kubeconfigPath := filepath.Join(kubeconfigDir, "kubeconfig")
	stubConfig := []byte(`apiVersion: v1
clusters:
- cluster:
    insecure-skip-tls-verify: true
    server: https://127.0.0.1
  name: stub
contexts:
- context:
    cluster: stub
    user: stub
  name: stub
current-context: stub
kind: Config
users:
- name: stub
  user:
    token: STUB-TOKEN-NOT-A-REAL-SECRET
`)
	require.NoError(t, os.WriteFile(kubeconfigPath, stubConfig, 0o600))

	return map[string]interface{}{
		"cluster_name":    "test-pg-cluster",
		"instances":       3,
		"storage_size":    "10Gi",
		"database_name":   "testdb",
		"database_owner":  "testuser",
		"postgis_enabled": true,
		"kubeconfig_path": kubeconfigPath,
	}
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"cluster_name":    "test-pg-cluster",
		"instances":       3,
		"storage_size":    "10Gi",
		"database_name":   "testdb",
		"database_owner":  "testuser",
		"postgis_enabled": true,
	}
}

func renderVarsWithBackup(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"cluster_name":                "test-pg-cluster",
		"instances":                   3,
		"storage_size":                "10Gi",
		"database_name":               "testdb",
		"database_owner":              "testuser",
		"postgis_enabled":             true,
		"backup_enabled":              true,
		"backup_destination_path":     "s3://test-bucket/backups/",
		"backup_endpoint_url":         "https://nyc3.digitaloceanspaces.com",
		"backup_s3_access_key_id":     "TESTKEY123",
		"backup_s3_secret_access_key": "testsecret456",
	}
}

func renderVarsWithESO(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"cluster_name":                    "test-pg-cluster",
		"instances":                       3,
		"storage_size":                    "10Gi",
		"database_name":                   "testdb",
		"database_owner":                  "testuser",
		"postgis_enabled":                 true,
		"eso_enabled":                     true,
		"eso_cluster_secret_store_name":   "vault-backend",
		"superuser_credentials_vault_path": "secret/data/cnpg/superuser",
		"app_credentials_vault_path":      "secret/data/cnpg/app",
	}
}

func setup(t *testing.T, vars map[string]interface{}) (string, *terraform.Options) {
	t.Helper()
	return testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
	})
}

func setupRender(t *testing.T, vars map[string]interface{}) (string, *terraform.Options) {
	t.Helper()
	return testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/render",
		Vars:          vars,
	})
}

func writeAutoTfvarsJSON(t *testing.T, dir string, vars map[string]interface{}) {
	t.Helper()
	path := filepath.Join(dir, "terratest.auto.tfvars.json")
	payload, err := json.Marshal(vars)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(path, payload, 0o600))
	t.Cleanup(func() { _ = os.Remove(path) })
}

func requireBinary(t *testing.T, req binaryRequirement) {
	t.Helper()
	if _, err := exec.LookPath(req.Binary); err != nil {
		t.Skip(req.SkipMessage)
	}
}

func requireEnvVar(t *testing.T, req envVarRequirement) string {
	t.Helper()
	value := os.Getenv(req.Key)
	if value == "" {
		t.Skip(req.SkipMessage)
	}
	return value
}

func terraformOutputExists(t *testing.T, opts *terraform.Options, name string) bool {
	t.Helper()
	_, err := terraform.OutputE(t, opts, name)
	return err == nil
}

func cnpgPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func cnpgManifestsPolicyPath(tfDir string) string {
	return filepath.Join(cnpgPolicyRoot(tfDir), "manifests")
}

func cnpgPlanPolicyPath(tfDir string) string {
	return filepath.Join(cnpgPolicyRoot(tfDir), "plan")
}

type conftestRun struct {
	InputPath  string
	PolicyPath string
	Kubeconfig string
	ExtraArgs  []string
	Timeout    time.Duration
}

func runConftest(t *testing.T, cfg conftestRun) ([]byte, error) {
	t.Helper()
	timeout := cfg.Timeout
	if timeout == 0 {
		timeout = 60 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	args := make([]string, 0, 4+len(cfg.ExtraArgs))
	args = append(args, "test", "--policy", cfg.PolicyPath, cfg.InputPath)
	args = append(args, cfg.ExtraArgs...)
	cmd := exec.CommandContext(ctx, "conftest", args...)
	cmd.Env = testutil.TerraformEnv(t, map[string]string{
		"KUBECONFIG": cfg.Kubeconfig,
	})
	out, err := cmd.CombinedOutput()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "conftest timed out: %s", string(out))
	return out, err
}

func writePlanFixture(t *testing.T, payload string) string {
	t.Helper()
	plan, err := os.CreateTemp("", "cnpg-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}
