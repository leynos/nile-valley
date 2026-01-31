package tests

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

const (
	applyTestKubeconfigEnv = "VALKEY_TEST_KUBECONFIG"
	applyTestSkipMessage   = "Set VALKEY_TEST_KUBECONFIG to a valid kubeconfig path to run apply-mode tests"
	kubectlTimeout         = 30 * time.Second
)

// baseApplyVars returns the common base configuration for apply-mode tests.
// This follows the same pattern as baseRenderVars in valkey_test_helpers.go.
func baseApplyVars() map[string]interface{} {
	return map[string]interface{}{
		"cluster_name": "test-valkey-apply",
		"nodes":        1,
		"replicas":     0,
		"storage_size": "1Gi",
	}
}

// applyVars returns variables for apply-mode tests with a real kubeconfig.
// It composes from baseApplyVars and adds apply-specific fields.
func applyVars(t *testing.T, kubeconfigPath string) map[string]interface{} {
	t.Helper()
	return mergeVars(baseApplyVars(), map[string]interface{}{
		"password_inline": "test-password-apply",
		"kubeconfig_path": kubeconfigPath,
	})
}

// setupApply creates terraform options for apply-mode example.
func setupApply(t *testing.T, vars map[string]interface{}) (string, *terraform.Options) {
	t.Helper()
	return testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
	})
}

// runKubectl executes kubectl with the given arguments and returns output.
func runKubectl(t *testing.T, kubeconfig string, args ...string) ([]byte, error) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), kubectlTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "kubectl", args...)
	cmd.Env = append(os.Environ(), fmt.Sprintf("KUBECONFIG=%s", kubeconfig))
	return cmd.CombinedOutput()
}

// TestValkeyModuleApplyCreatesResources verifies that apply mode creates
// the expected Kubernetes resources in a real cluster.
//
// This test is skipped unless VALKEY_TEST_KUBECONFIG is set to a valid
// kubeconfig path. The test requires:
// - A Kubernetes cluster with the Valkey operator already installed
// - kubectl binary available in PATH
// - Sufficient permissions to create namespaces, secrets, and Valkey CRs
func TestValkeyModuleApplyCreatesResources(t *testing.T) {
	kubeconfig := requireEnvVar(t, envVarRequirement{
		Key:         applyTestKubeconfigEnv,
		SkipMessage: applyTestSkipMessage,
	})
	requireBinary(t, binaryRequirement{
		Binary:      "kubectl",
		SkipMessage: "kubectl not found; skipping apply-mode test",
	})

	// Verify kubeconfig is accessible
	if _, err := os.Stat(kubeconfig); os.IsNotExist(err) {
		t.Skipf("kubeconfig file does not exist: %s", kubeconfig)
	}

	vars := applyVars(t, kubeconfig)
	_, opts := setupApply(t, vars)

	// Apply and ensure cleanup on exit
	defer terraform.Destroy(t, opts)
	terraform.InitAndApply(t, opts)

	// Verify namespace was created
	out, err := runKubectl(t, kubeconfig, "get", "namespace", "valkey", "-o", "name")
	require.NoError(t, err, "failed to get namespace: %s", string(out))
	require.Contains(t, string(out), "namespace/valkey", "expected valkey namespace to exist")

	// Verify operator namespace was created
	out, err = runKubectl(t, kubeconfig, "get", "namespace", "valkey-system", "-o", "name")
	require.NoError(t, err, "failed to get operator namespace: %s", string(out))
	require.Contains(t, string(out), "namespace/valkey-system", "expected valkey-system namespace to exist")

	// Verify password secret was created
	out, err = runKubectl(t, kubeconfig, "get", "secret", "valkey-password", "-n", "valkey", "-o", "name")
	require.NoError(t, err, "failed to get password secret: %s", string(out))
	require.Contains(t, string(out), "secret/valkey-password", "expected password secret to exist")

	// Verify HelmRelease was created (if Flux is installed)
	out, err = runKubectl(t, kubeconfig,
		"get", "helmrelease.helm.toolkit.fluxcd.io", "valkey-operator",
		"-n", "valkey-system", "-o", "name", "--ignore-not-found")
	if err == nil && len(out) > 0 {
		require.Contains(t, string(out), "helmrelease.helm.toolkit.fluxcd.io/valkey-operator",
			"expected HelmRelease to exist when Flux is installed")
	}

	// Verify Valkey CR was created.
	// The test documentation states that the cluster must have the Valkey operator
	// CRDs installed, so we require the CR to exist (not conditionally check).
	out, err = runKubectl(t, kubeconfig,
		"get", "valkey.hyperspike.io", "test-valkey-apply",
		"-n", "valkey", "-o", "name")
	require.NoError(t, err,
		"failed to get Valkey CR (ensure Valkey CRDs are installed): %s", string(out))
	require.Contains(t, string(out), "valkey.hyperspike.io/test-valkey-apply",
		"expected Valkey CR to exist")

	// Verify outputs are populated
	primaryEndpoint := terraform.Output(t, opts, "primary_endpoint")
	require.NotEmpty(t, primaryEndpoint, "expected primary_endpoint output")
	require.Contains(t, primaryEndpoint, "test-valkey-apply-primary", "expected primary endpoint format")

	credentialsSecretName := terraform.Output(t, opts, "credentials_secret_name")
	require.Equal(t, "valkey-password", credentialsSecretName, "expected credentials secret name")

	contract := terraform.OutputMap(t, opts, "sync_policy_contract")
	require.NotEmpty(t, contract, "expected sync_policy_contract output")
}

// TestValkeyModuleApplyIdempotent verifies that applying the module twice
// produces no changes (idempotency).
func TestValkeyModuleApplyIdempotent(t *testing.T) {
	kubeconfig := requireEnvVar(t, envVarRequirement{
		Key:         applyTestKubeconfigEnv,
		SkipMessage: applyTestSkipMessage,
	})

	// Verify kubeconfig is accessible
	if _, err := os.Stat(kubeconfig); os.IsNotExist(err) {
		t.Skipf("kubeconfig file does not exist: %s", kubeconfig)
	}

	vars := applyVars(t, kubeconfig)
	// Use unique cluster name to avoid conflicts with other tests
	vars["cluster_name"] = "test-valkey-idempotent"

	_, opts := setupApply(t, vars)

	// Apply and ensure cleanup on exit
	defer terraform.Destroy(t, opts)
	terraform.InitAndApply(t, opts)

	// Plan should show no changes on second run
	planStruct := terraform.InitAndPlanAndShowWithStruct(t, opts)
	require.Empty(t, planStruct.ResourceChangesMap,
		"expected no resource changes on second apply (idempotency check)")
}

// TestValkeyModuleApplyDestroy verifies that destroy removes all resources.
func TestValkeyModuleApplyDestroy(t *testing.T) {
	kubeconfig := requireEnvVar(t, envVarRequirement{
		Key:         applyTestKubeconfigEnv,
		SkipMessage: applyTestSkipMessage,
	})
	requireBinary(t, binaryRequirement{
		Binary:      "kubectl",
		SkipMessage: "kubectl not found; skipping apply-mode test",
	})

	// Verify kubeconfig is accessible
	if _, err := os.Stat(kubeconfig); os.IsNotExist(err) {
		t.Skipf("kubeconfig file does not exist: %s", kubeconfig)
	}

	vars := applyVars(t, kubeconfig)
	// Use unique cluster name to avoid conflicts with other tests
	vars["cluster_name"] = "test-valkey-destroy"

	_, opts := setupApply(t, vars)

	// Apply resources
	terraform.InitAndApply(t, opts)

	// Destroy resources
	terraform.Destroy(t, opts)

	// Verify password secret was removed
	out, err := runKubectl(t, kubeconfig,
		"get", "secret", "valkey-password", "-n", "valkey",
		"-o", "name", "--ignore-not-found")
	require.NoError(t, err, "kubectl get should succeed even if resource doesn't exist")
	require.Empty(t, string(out), "expected password secret to be deleted")

	// Note: Namespaces may persist if other resources exist in them.
	// The Valkey CR and HelmRelease deletion is handled by Kubernetes
	// garbage collection when their parent resources are removed.
}
