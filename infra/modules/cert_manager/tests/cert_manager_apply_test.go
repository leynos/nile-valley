package tests

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

func TestCertManagerModulePlanDetailedExitCode(t *testing.T) {
	t.Parallel()
	requireBinary(t, "tofu", "tofu not found; skipping detailed exit code plan")
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping detailed exit code plan")
	}
	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("cert-manager-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["kubeconfig_path"] = kubeconfig
	tfDir, opts := setup(t, vars)
	writeAutoTfvarsJSON(t, tfDir, vars)
	terraform.Init(t, opts)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, "tofu", "plan", "-input=false", "-no-color", "-detailed-exitcode")
	cmd.Dir = tfDir
	cmd.Env = testutil.TerraformEnv(t, nil)
	err := cmd.Run()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "tofu plan -detailed-exitcode timed out")
	if err == nil {
		t.Fatalf("expected exit code 2 indicating changes, got 0")
	}
	var exitErr *exec.ExitError
	require.ErrorAs(t, err, &exitErr, "expected ExitError")
	require.Equal(t, 2, exitErr.ExitCode())
}

func TestCertManagerModuleApplyIfKubeconfigPresent(t *testing.T) {
	t.Parallel()
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping apply test")
	}
	if os.Getenv("CERT_MANAGER_ACCEPT_APPLY") == "" {
		t.Skip("CERT_MANAGER_ACCEPT_APPLY not set; skipping apply test")
	}

	expectedNamespace := fmt.Sprintf("cert-manager-terratest-%s", strings.ToLower(random.UniqueId()))

	vars := testVars(t)
	vars["namespace"] = expectedNamespace
	vars["kubeconfig_path"] = kubeconfig

	_, opts := setup(t, vars)
	t.Cleanup(func() {
		terraform.Destroy(t, opts)
	})

	terraform.InitAndApply(t, opts)

	namespace := terraform.Output(t, opts, "namespace")
	helmRelease := terraform.Output(t, opts, "helm_release_name")

	require.Equal(t, expectedNamespace, namespace, "namespace output should match input")
	require.NotEmpty(t, helmRelease, "helm_release_name output should not be empty")

	if terraformOutputExists(t, opts, "acme_staging_issuer_name") {
		issuer := terraform.Output(t, opts, "acme_staging_issuer_name")
		require.NotEmpty(t, issuer, "acme_staging_issuer_name output should not be empty")
	}
}
