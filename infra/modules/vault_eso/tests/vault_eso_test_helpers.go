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

const vaultESOPolicyManifestsNamespace = "vault_eso.policy.manifests"
const vaultESOPolicyPlanNamespace = "vault_eso.policy.plan"

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
		"vault_address":       "https://vault.example.test:8200",
		"vault_ca_bundle_pem": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
		"approle_role_id":     "00000000-0000-0000-0000-000000000000", // #nosec G101 -- test fixture
		"approle_secret_id":   "00000000-0000-0000-0000-000000000001", // #nosec G101 -- test fixture
		"kubeconfig_path":     kubeconfigPath,
	}
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"vault_address":       "https://vault.example.test:8200",
		"vault_ca_bundle_pem": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
		"approle_role_id":     "00000000-0000-0000-0000-000000000000", // #nosec G101 -- test fixture
		"approle_secret_id":   "00000000-0000-0000-0000-000000000001", // #nosec G101 -- test fixture
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

func vaultESOPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func vaultESOManifestsPolicyPath(tfDir string) string {
	return filepath.Join(vaultESOPolicyRoot(tfDir), "manifests")
}

func vaultESOPlanPolicyPath(tfDir string) string {
	return filepath.Join(vaultESOPolicyRoot(tfDir), "plan")
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
	plan, err := os.CreateTemp("", "vault-eso-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}
