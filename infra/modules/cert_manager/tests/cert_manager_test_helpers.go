package tests

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

const exampleKubeconfigError = "Set kubeconfig_path to a readable kubeconfig file before running the example"

const certManagerPolicyManifestsNamespace = "cert_manager.policy.manifests"
const certManagerPolicyPlanNamespace = "cert_manager.policy.plan"

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
    token: fake-token
`)
	require.NoError(t, os.WriteFile(kubeconfigPath, stubConfig, 0o600))

	return map[string]interface{}{
		"acme_email":                "platform@example.test",
		"namecheap_api_secret_name": "namecheap-api-credentials",
		"vault_enabled":             true,
		"vault_server":              "https://vault.example.test:8200",
		"vault_pki_path":            "pki/sign/example",
		"vault_token_secret_name":   "vault-token",
		"vault_ca_bundle_pem":       "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
		"kubeconfig_path":           kubeconfigPath,
	}
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"acme_email":                "platform@example.test",
		"namecheap_api_secret_name": "namecheap-api-credentials",
		"vault_enabled":             true,
		"vault_server":              "https://vault.example.test:8200",
		"vault_pki_path":            "pki/sign/example",
		"vault_token_secret_name":   "vault-token",
		"vault_ca_bundle_pem":       "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
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

func testKubeconfigPathValidation(t *testing.T, kubeconfigPath string) {
	t.Helper()
	vars := testVars(t)
	vars["kubeconfig_path"] = kubeconfigPath
	_, opts := setup(t, vars)
	stdout, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	combined := strings.Join([]string{stdout, err.Error()}, "\n")
	require.Contains(t, combined, exampleKubeconfigError)
}

func requireBinary(t *testing.T, binary, skipMessage string) {
	t.Helper()
	if _, err := exec.LookPath(binary); err != nil {
		t.Skip(skipMessage)
	}
}

func requireEnvVar(t *testing.T, key, skipMessage string) string {
	t.Helper()
	value := os.Getenv(key)
	if value == "" {
		t.Skip(skipMessage)
	}
	return value
}

func terraformOutputExists(t *testing.T, opts *terraform.Options, name string) bool {
	t.Helper()
	_, err := terraform.OutputE(t, opts, name)
	return err == nil
}

func certManagerPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func certManagerManifestsPolicyPath(tfDir string) string {
	return filepath.Join(certManagerPolicyRoot(tfDir), "manifests")
}

func certManagerPlanPolicyPath(tfDir string) string {
	return filepath.Join(certManagerPolicyRoot(tfDir), "plan")
}

func renderCertManagerPlan(t *testing.T, vars map[string]interface{}) (string, string) {
	t.Helper()
	tfDir, opts := setup(t, vars)
	planFile := filepath.Join(tfDir, "tfplan.binary")
	opts.PlanFilePath = planFile
	terraform.InitAndPlan(t, opts)
	t.Cleanup(func() { _ = os.Remove(planFile) })

	show, err := terraform.RunTerraformCommandE(t, opts, "show", "-json", planFile)
	require.NoError(t, err)

	jsonPath := filepath.Join(tfDir, "plan.json")
	require.NoError(t, os.WriteFile(jsonPath, []byte(show), 0o600))
	t.Cleanup(func() { _ = os.Remove(jsonPath) })

	return tfDir, jsonPath
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
	plan, err := os.CreateTemp("", "cert-manager-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}
