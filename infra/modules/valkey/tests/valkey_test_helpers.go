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

const valkeyPolicyManifestsNamespace = "valkey.policy.manifests"

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
		"cluster_name":    "test-valkey",
		"nodes":           1,
		"replicas":        0,
		"storage_size":    "1Gi",
		"password_inline": "test-password-123",
		"kubeconfig_path": kubeconfigPath,
	}
}

// baseRenderVars returns the common base configuration for render tests.
func baseRenderVars() map[string]interface{} {
	return map[string]interface{}{
		"cluster_name": "test-valkey",
		"nodes":        1,
		"replicas":     0,
		"storage_size": "1Gi",
	}
}

// mergeVars merges base and override maps, with overrides taking precedence.
func mergeVars(base, overrides map[string]interface{}) map[string]interface{} {
	result := make(map[string]interface{}, len(base)+len(overrides))
	for k, v := range base {
		result[k] = v
	}
	for k, v := range overrides {
		result[k] = v
	}
	return result
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	return mergeVars(baseRenderVars(), map[string]interface{}{
		"password_inline": "test-password-for-render",
	})
}

func renderVarsHA(t *testing.T) map[string]interface{} {
	t.Helper()
	return mergeVars(baseRenderVars(), map[string]interface{}{
		"cluster_name":    "test-valkey-ha",
		"nodes":           3,
		"replicas":        1,
		"storage_size":    "2Gi",
		"password_inline": "test-password-for-ha",
	})
}

func renderVarsWithESO(t *testing.T) map[string]interface{} {
	t.Helper()
	return mergeVars(baseRenderVars(), map[string]interface{}{
		"eso_enabled":                   true,
		"eso_cluster_secret_store_name": "vault-backend",
		"password_vault_path":           "secret/data/valkey/password",
	})
}

func renderVarsWithTLS(t *testing.T) map[string]interface{} {
	t.Helper()
	return mergeVars(baseRenderVars(), map[string]interface{}{
		"password_inline":  "test-password",
		"tls_enabled":      true,
		"cert_issuer_name": "letsencrypt-staging",
	})
}

func renderVarsAnonymous(t *testing.T) map[string]interface{} {
	t.Helper()
	return mergeVars(baseRenderVars(), map[string]interface{}{
		"anonymous_auth": true,
	})
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

func valkeyPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func valkeyManifestsPolicyPath(tfDir string) string {
	return filepath.Join(valkeyPolicyRoot(tfDir), "manifests")
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
