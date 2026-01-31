package tests

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

const exampleKubeconfigError = "Set kubeconfig_path to a readable kubeconfig file before running the example"

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
	require.NoError(t, os.WriteFile(kubeconfigPath, stubConfig, 0600))

	return map[string]interface{}{
		"namespace":                  "flux-system",
		"git_repository_name":        "flux-system",
		"kustomization_name":         "flux-system",
		"git_repository_url":         "https://github.com/fluxcd/flux2-kustomize-helm-example.git",
		"git_repository_branch":      "main",
		"git_repository_path":        "./clusters/my-cluster",
		"reconcile_interval":         "1m",
		"kustomization_prune":        true,
		"kustomization_suspend":      false,
		"git_repository_secret_name": nil,
		"kubeconfig_path":            kubeconfigPath,
		"helm_values":                []string{},
		"helm_values_files":          []string{},
	}
}

func setup(t *testing.T, vars map[string]interface{}) (string, *terraform.Options) {
	t.Helper()
	return testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, nil),
	})
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

func renderFluxPlan(t *testing.T, vars map[string]interface{}) (string, string) {
	t.Helper()
	tfDir, opts := setup(t, vars)
	planFile := filepath.Join(tfDir, "tfplan.binary")
	opts.PlanFilePath = planFile
	terraform.InitAndPlan(t, opts)
	t.Cleanup(func() { _ = os.Remove(planFile) })

	show, err := terraform.RunTerraformCommandE(t, opts, "show", "-json", planFile)
	require.NoError(t, err)

	jsonPath := filepath.Join(tfDir, "plan.json")
	require.NoError(t, os.WriteFile(jsonPath, []byte(show), 0600))
	t.Cleanup(func() { _ = os.Remove(jsonPath) })

	return tfDir, jsonPath
}

type conftestRun struct {
	PlanPath   string
	PolicyPath string
	Kubeconfig string
	ExtraArgs  []string
	Timeout    time.Duration
}

func runConftestAgainstPlan(t *testing.T, cfg conftestRun) ([]byte, error) {
	t.Helper()
	timeout := cfg.Timeout
	if timeout == 0 {
		timeout = 60 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	args := append([]string{"test", cfg.PlanPath, "--policy", cfg.PolicyPath}, cfg.ExtraArgs...)
	cmd := exec.CommandContext(ctx, "conftest", args...)
	cmd.Env = testutil.TerraformEnv(t, map[string]string{
		"KUBECONFIG": cfg.Kubeconfig,
	})
	out, err := cmd.CombinedOutput()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "conftest timed out")
	return out, err
}

func writePlanFixture(t *testing.T, payload string) string {
	t.Helper()
	plan, err := os.CreateTemp("", "fluxcd-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}

func writePolicyDataFile(t *testing.T, payload string) string {
	t.Helper()
	file, err := os.CreateTemp("", "fluxcd-policy-data-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(file.Name()) })
	_, err = file.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, file.Close())
	return file.Name()
}

func TestFluxModuleValidate(t *testing.T) {
	t.Parallel()
	_, opts := setup(t, testVars(t))
	terraform.InitAndValidate(t, opts)
}

func TestFluxModuleInvalidURL(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["git_repository_url"] = "ftp://invalid"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`git_repository_url`), err.Error())
}

func TestFluxExampleRequiresKubeconfigPath(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, "")
}

func TestFluxExampleRejectsWhitespaceKubeconfig(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, " \n\t ")
}

func TestFluxModuleInvalidPath(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["git_repository_path"] = "/absolute/path"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`git_repository_path must be a non-empty relative path without\s+parent-directory traversal`), err.Error())
}

func TestFluxModuleInvalidBranch(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["git_repository_branch"] = ""
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`git_repository_branch must not be blank`), err.Error())
}

func TestFluxModuleSupportsHelmValues(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	valuesDir := t.TempDir()
	valuesFile := filepath.Join(valuesDir, "values.yaml")
	fileContent := "featureFlags:\n  tracing: true\n"
	require.NoError(t, os.WriteFile(valuesFile, []byte(fileContent), 0600))
	vars["helm_values"] = []string{"installCRDs: true"}
	vars["helm_values_files"] = []string{valuesFile}
	_, opts := setup(t, vars)
	stdout, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Contains(t, stdout, "installCRDs: true")
	require.Contains(t, stdout, "featureFlags")
	require.Contains(t, stdout, "tracing: true")
}

func TestFluxModulePlanFailsWithoutKubeconfig(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["kubeconfig_path"] = "/nonexistent/kubeconfig"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	lowered := strings.ToLower(err.Error())
	require.Truef(t, strings.Contains(lowered, "no such file") || strings.Contains(lowered, "stat"), "expected missing kubeconfig error, got %q", err.Error())
}

func TestFluxModulePlanDetailedExitCode(t *testing.T) {
	t.Parallel()
	requireBinary(t, "tofu", "tofu not found; skipping detailed exit code plan")
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping detailed exit code plan")
	}
	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("flux-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["git_repository_name"] = fmt.Sprintf("flux-repo-%s", strings.ToLower(random.UniqueId()))
	vars["kustomization_name"] = fmt.Sprintf("flux-kustomization-%s", strings.ToLower(random.UniqueId()))
	vars["kubeconfig_path"] = kubeconfig
	tfDir, opts := setup(t, vars)
	terraform.Init(t, opts)
	cmd := exec.Command("tofu", "plan", "-input=false", "-no-color", "-detailed-exitcode")
	cmd.Dir = tfDir
	cmd.Env = testutil.TerraformEnv(t, nil)
	err := cmd.Run()
	if err == nil {
		t.Fatalf("expected exit code 2 indicating changes, got 0")
	}
	exitErr, ok := err.(*exec.ExitError)
	require.True(t, ok, "expected ExitError")
	require.Equal(t, 2, exitErr.ExitCode())
}

func TestFluxModulePolicy(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")
	kubeconfig := requireEnvVar(t, "KUBECONFIG", "KUBECONFIG not set; skipping policy test")

	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("flux-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["git_repository_name"] = fmt.Sprintf("flux-repo-%s", strings.ToLower(random.UniqueId()))
	vars["kustomization_name"] = fmt.Sprintf("flux-kustomization-%s", strings.ToLower(random.UniqueId()))
	vars["kubeconfig_path"] = kubeconfig

	tfDir, planJSON := renderFluxPlan(t, vars)
	policyPath := filepath.Join(tfDir, "..", "policy")

	out, err := runConftestAgainstPlan(t, conftestRun{
		PlanPath:   planJSON,
		PolicyPath: policyPath,
		Kubeconfig: kubeconfig,
		Timeout:    60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))

	t.Run("PolicyViolation", func(t *testing.T) {
		t.Parallel()
		payload := `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"GitRepository","metadata":{"name":"invalid"},"spec":{"url":"ftp://invalid","interval":"15m"}}}}}]}`
		planPath := writePlanFixture(t, payload)
		violationOut, violationErr := runConftestAgainstPlan(t, conftestRun{
			PlanPath:   planPath,
			PolicyPath: policyPath,
			Kubeconfig: kubeconfig,
			Timeout:    10 * time.Second,
		})
		require.Error(t, violationErr, "expected conftest to report a violation")
		exitErr, ok := violationErr.(*exec.ExitError)
		require.True(t, ok, "expected ExitError from conftest for policy violation")
		require.NotZero(t, exitErr.ExitCode(), "expected non-zero exit code for policy violation")
		require.Contains(t, strings.ToLower(string(violationOut)), "gitrepository", "expected policy violation output")
	})

	t.Run("AllowsFileSchemeWhenOptedIn", func(t *testing.T) {
		t.Parallel()
		payload := `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"GitRepository","metadata":{"name":"file"},"spec":{"url":"file:///tmp/repo","interval":"1m","ref":{"branch":"main"}}}}}}]}`
		planPath := writePlanFixture(t, payload)

		violationOut, violationErr := runConftestAgainstPlan(t, conftestRun{
			PlanPath:   planPath,
			PolicyPath: policyPath,
			Kubeconfig: kubeconfig,
			Timeout:    10 * time.Second,
		})
		require.Error(t, violationErr, "expected conftest to report a violation when file:// is disallowed")
		exitErr, ok := violationErr.(*exec.ExitError)
		require.True(t, ok, "expected ExitError from conftest for file-scheme violation")
		require.NotZero(t, exitErr.ExitCode(), "expected non-zero exit code for file-scheme violation")
		require.Contains(t, strings.ToLower(string(violationOut)), "gitrepository", "expected git repository policy violation output")

		dataFile := writePolicyDataFile(t, `{"allow_file_scheme":true}`)
		allowOut, allowErr := runConftestAgainstPlan(t, conftestRun{
			PlanPath:   planPath,
			PolicyPath: policyPath,
			Kubeconfig: kubeconfig,
			Timeout:    10 * time.Second,
			ExtraArgs:  []string{"-d", dataFile},
		})
		require.NoErrorf(t, allowErr, "conftest unexpectedly failed when allow_file_scheme=true: %s", string(allowOut))
	})

	t.Run("RejectsParentDirectoryTraversal", func(t *testing.T) {
		t.Parallel()
		payload := `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"Kustomization","metadata":{"name":"invalid-path"},"spec":{"path":"../hack","prune":true,"suspend":false,"sourceRef":{"kind":"GitRepository"}}}}}}]}`
		planPath := writePlanFixture(t, payload)
		violationOut, violationErr := runConftestAgainstPlan(t, conftestRun{
			PlanPath:   planPath,
			PolicyPath: policyPath,
			Kubeconfig: kubeconfig,
			Timeout:    10 * time.Second,
		})
		require.Error(t, violationErr, "expected conftest to report a violation for parent traversal")
		exitErr, ok := violationErr.(*exec.ExitError)
		require.True(t, ok, "expected ExitError from conftest for parent traversal")
		require.NotZero(t, exitErr.ExitCode(), "expected non-zero exit code for parent traversal violation")
		require.Contains(t, strings.ToLower(string(violationOut)), "kustomization", "expected kustomization path violation output")
	})
}

func TestFluxModuleApplyIfKubeconfigPresent(t *testing.T) {
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping apply test")
	}
	if os.Getenv("FLUXCD_ACCEPT_APPLY") == "" {
		t.Skip("FLUXCD_ACCEPT_APPLY not set; skipping apply test")
	}
	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("flux-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["git_repository_name"] = fmt.Sprintf("flux-repo-%s", strings.ToLower(random.UniqueId()))
	vars["kustomization_name"] = fmt.Sprintf("flux-kustomization-%s", strings.ToLower(random.UniqueId()))
	vars["kubeconfig_path"] = kubeconfig
	_, opts := setup(t, vars)
	t.Cleanup(func() {
		terraform.Destroy(t, opts)
	})
	terraform.InitAndApply(t, opts)

	namespace := terraform.Output(t, opts, "namespace")
	gitRepo := terraform.Output(t, opts, "git_repository_name")
	kustomization := terraform.Output(t, opts, "kustomization_name")

	require.NotEmpty(t, namespace)
	require.NotEmpty(t, gitRepo)
	require.NotEmpty(t, kustomization)

	stdout, err := terraform.RunTerraformCommandAndGetStdoutE(t, opts, "state", "show", fmt.Sprintf("kubernetes_manifest.git_repository"))
	require.NoError(t, err)
	require.Contains(t, stdout, vars["git_repository_url"].(string))
}
