package tests

import (
	"context"
	"encoding/json"
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

const traefikModuleName = "traefik"

const traefikPolicyManifestsNamespace = "traefik.policy.manifests"
const traefikPolicyPlanNamespace = "traefik.policy.plan"

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
		"namespace":                          "traefik",
		"acme_email":                         "admin@example.test",
		"cloudflare_api_token_secret_name":   "cloudflare-api-token",
		"cloudflare_api_token_secret_key":    "token",
		"cluster_issuer_name":                "letsencrypt-prod",
		"acme_server":                        "https://acme-v02.api.letsencrypt.org/directory",
		"dashboard_enabled":                  false,
		"http_to_https_redirect":             true,
		"prometheus_metrics_enabled":         true,
		"service_monitor_enabled":            true,
		"kubeconfig_path":                    kubeconfigPath,
		"helm_values":                        []string{},
		"helm_values_files":                  []string{},
	}
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	return map[string]interface{}{
		"namespace":                        "traefik",
		"acme_email":                       "admin@example.test",
		"cloudflare_api_token_secret_name": "cloudflare-api-token",
		"service_annotations": map[string]string{
			"example.com/unit-test": "true",
		},
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
	require.NoError(t, os.WriteFile(path, payload, 0600))
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

func traefikPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func traefikManifestsPolicyPath(tfDir string) string {
	return filepath.Join(traefikPolicyRoot(tfDir), "manifests")
}

func traefikPlanPolicyPath(tfDir string) string {
	return filepath.Join(traefikPolicyRoot(tfDir), "plan")
}

func renderTraefikPlan(t *testing.T, vars map[string]interface{}) (string, string) {
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

	args := append([]string{"test", "--policy", cfg.PolicyPath, cfg.PlanPath}, cfg.ExtraArgs...)
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
	plan, err := os.CreateTemp("", "traefik-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}

func TestTraefikModuleValidate(t *testing.T) {
	t.Parallel()
	_, opts := setup(t, testVars(t))
	terraform.InitAndValidate(t, opts)
}

func TestTraefikModuleRenderOutputs(t *testing.T) {
	t.Parallel()

	vars := renderVars(t)
	vars["cluster_issuer_name"] = "issuer-render"
	vars["dashboard_enabled"] = true
	vars["dashboard_hostname"] = "traefik-dashboard.example.test"

	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	helmRelease, ok := rendered["platform/traefik/helmrelease.yaml"]
	require.True(t, ok, "expected platform/traefik/helmrelease.yaml output key")
	require.True(
		t,
		strings.Contains(helmRelease, "kind: HelmRelease") ||
			strings.Contains(helmRelease, "\"kind\": \"HelmRelease\""),
		"expected HelmRelease manifest to contain kind HelmRelease",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "name: traefik") ||
			strings.Contains(helmRelease, "\"name\": \"traefik\""),
		"expected HelmRelease manifest to contain metadata.name traefik",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "example.com/unit-test: \"true\"") ||
			strings.Contains(helmRelease, "example.com/unit-test: true") ||
			strings.Contains(helmRelease, "\"example.com/unit-test\": \"true\"") ||
			strings.Contains(helmRelease, "\"example.com/unit-test\": true"),
		"expected service annotation example.com/unit-test to be present in rendered helmrelease",
	)

	_, ok = rendered["platform/traefik/crds/traefik-crds.yaml"]
	require.True(t, ok, "expected platform/traefik/crds/traefik-crds.yaml output key")

	_, ok = rendered["platform/sources/traefik-repo.yaml"]
	require.True(t, ok, "expected platform/sources/traefik-repo.yaml output key")

	dashboardHostnames := terraform.OutputList(t, opts, "dashboard_hostnames")
	require.NotEmpty(t, dashboardHostnames, "expected dashboard_hostnames output to be non-empty when dashboard is enabled")
	require.Equal(t, []string{"traefik-dashboard.example.test"}, dashboardHostnames)

	dashboardHostname := terraform.Output(t, opts, "dashboard_hostname")
	require.Equal(t, "traefik-dashboard.example.test", dashboardHostname)

	defaultIssuer := terraform.Output(t, opts, "default_certificate_issuer_name")
	require.NotEmpty(t, defaultIssuer, "expected default_certificate_issuer_name output to be non-empty")
	require.Equal(t, "issuer-render", defaultIssuer)
	require.Equal(t, terraform.Output(t, opts, "cluster_issuer_name"), defaultIssuer)
}

func TestTraefikModuleRenderPolicy(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")

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

	policyPath := traefikManifestsPolicyPath(tfDir)
	out, err := runConftestAgainstPlan(t, conftestRun{
		PlanPath:   outDir,
		PolicyPath: policyPath,
		Kubeconfig: "",
		ExtraArgs: []string{
			"--fail-on-warn",
			"--namespace",
			traefikPolicyManifestsNamespace,
		},
		Timeout: 60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

func TestTraefikModuleRenderPolicyRejectsMissingChartVersion(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")

	tfDir, _ := setupRender(t, renderVars(t))
	policyPath := traefikManifestsPolicyPath(tfDir)

	tmpDir := t.TempDir()
	manifestPath := filepath.Join(tmpDir, "helmrelease.yaml")
	payload := `apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: traefik
  namespace: traefik
spec:
  chart:
    spec:
      chart: traefik
      sourceRef:
        kind: HelmRepository
        name: traefik
        namespace: flux-system
  values:
    service:
      type: LoadBalancer
      spec:
        externalTrafficPolicy: Local
`
	require.NoError(t, os.WriteFile(manifestPath, []byte(payload), 0o600))

	out, err := runConftestAgainstPlan(t, conftestRun{
		PlanPath:   manifestPath,
		PolicyPath: policyPath,
		Kubeconfig: "",
		ExtraArgs: []string{
			"--fail-on-warn",
			"--namespace",
			traefikPolicyManifestsNamespace,
		},
		Timeout: 60 * time.Second,
	})
	require.Error(t, err, "expected conftest to report a violation")
	require.Contains(t, string(out), "must pin chart.spec.version")
}

func TestTraefikModuleRenderRejectsBlankServiceAnnotationKey(t *testing.T) {
	t.Parallel()

	vars := renderVars(t)
	vars["service_annotations"] = map[string]string{
		"  ": "value",
	}

	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Contains(t, err.Error(), "service_annotations")
}

func TestTraefikModuleInvalidEmail(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["acme_email"] = "not-an-email"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`acme_email`), err.Error())
}

func TestTraefikModuleInvalidChartVersion(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["chart_version"] = "invalid"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`chart_version`), err.Error())
}

func TestTraefikModuleInvalidNamespace(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["namespace"] = "Invalid_Namespace"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`namespace`), err.Error())
}

func TestTraefikModuleDashboardHostnameRequired(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["dashboard_enabled"] = true
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`dashboard_hostname`), err.Error())
}

func TestTraefikModuleServiceMonitorRequiresMetrics(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["prometheus_metrics_enabled"] = false
	vars["service_monitor_enabled"] = true
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`service_monitor_enabled`), err.Error())
}

func TestTraefikModuleInvalidACMEServer(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	vars["acme_server"] = "http://invalid.example.com"
	_, opts := setup(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`acme_server`), err.Error())
}

// nullVariableValidationTestCases defines test cases for null/invalid variable validation error messages
var nullVariableValidationTestCases = []struct {
	name            string
	varName         string
	value           interface{}
	expectedMessage string
}{
	{
		name:            "NullNamespace",
		varName:         "namespace",
		value:           nil,
		expectedMessage: "namespace must be a valid Kubernetes namespace name",
	},
	{
		name:            "NullChartRepository",
		varName:         "chart_repository",
		value:           nil,
		expectedMessage: "chart_repository must be an HTTPS URL",
	},
	{
		name:            "NullChartName",
		varName:         "chart_name",
		value:           nil,
		expectedMessage: "chart_name must not be blank",
	},
	{
		name:            "NullChartVersion",
		varName:         "chart_version",
		value:           nil,
		expectedMessage: "chart_version must be a semantic version",
	},
	{
		name:            "NullHelmReleaseName",
		varName:         "helm_release_name",
		value:           nil,
		expectedMessage: "helm_release_name must not be blank",
	},
	{
		name:            "NullHelmValuesFilesList",
		varName:         "helm_values_files",
		value:           nil,
		expectedMessage: "helm_values_files must not contain blank file paths",
	},
	{
		name:            "NullHelmValuesFilesElement",
		varName:         "helm_values_files",
		value:           []interface{}{nil},
		expectedMessage: "helm_values_files must not contain blank file paths",
	},
	{
		name:            "NullIngressClassName",
		varName:         "ingress_class_name",
		value:           nil,
		expectedMessage: "ingress_class_name must not be blank",
	},
	{
		name:            "NullAcmeEmail",
		varName:         "acme_email",
		value:           nil,
		expectedMessage: "acme_email must be a valid email address",
	},
	{
		name:            "NullAcmeServer",
		varName:         "acme_server",
		value:           nil,
		expectedMessage: "acme_server must be a valid Let's Encrypt production or staging URL",
	},
	{
		name:            "NullClusterIssuerName",
		varName:         "cluster_issuer_name",
		value:           nil,
		expectedMessage: "cluster_issuer_name must be a valid Kubernetes resource name",
	},
}

func TestTraefikModuleNullVariableValidationReturnsErrorMessage(t *testing.T) {
	t.Parallel()
	for _, tc := range nullVariableValidationTestCases {
		t.Run(tc.name, func(t *testing.T) {
			vars := testVars(t)
			vars[tc.varName] = tc.value
			tfDir, opts := setup(t, vars)
			writeAutoTfvarsJSON(t, tfDir, vars)
			opts.Vars = map[string]interface{}{}

			stdout, err := terraform.InitAndPlanE(t, opts)
			require.Error(t, err)

			combined := strings.Join([]string{stdout, err.Error()}, "\n")
			require.Contains(t, combined, tc.expectedMessage)
			require.NotContains(t, combined, "Invalid function argument")
		})
	}
}

// inputValidationTestCases defines test cases for Terraform variable validation
var inputValidationTestCases = []struct {
	name         string
	varName      string
	invalidValue interface{}
	errorPattern string
}{
	{
		name:         "BlankCloudflareSecretName",
		varName:      "cloudflare_api_token_secret_name",
		invalidValue: "   ",
		errorPattern: "cloudflare_api_token_secret_name",
	},
	{
		name:         "BlankCloudflareSecretKey",
		varName:      "cloudflare_api_token_secret_key",
		invalidValue: "",
		errorPattern: "cloudflare_api_token_secret_key",
	},
	{
		name:         "InvalidClusterIssuerName",
		varName:      "cluster_issuer_name",
		invalidValue: "Invalid_Issuer_Name",
		errorPattern: "cluster_issuer_name",
	},
	{
		name:         "InvalidServiceType",
		varName:      "service_type",
		invalidValue: "ExternalName",
		errorPattern: "service_type",
	},
	{
		name:         "InvalidExternalTrafficPolicy",
		varName:      "external_traffic_policy",
		invalidValue: "Invalid",
		errorPattern: "external_traffic_policy",
	},
	{
		name:         "BlankIngressClassName",
		varName:      "ingress_class_name",
		invalidValue: "",
		errorPattern: "ingress_class_name",
	},
	{
		name:         "InvalidChartRepository",
		varName:      "chart_repository",
		invalidValue: "http://insecure.example.com",
		errorPattern: "chart_repository",
	},
	{
		name:         "BlankHelmReleaseName",
		varName:      "helm_release_name",
		invalidValue: "  ",
		errorPattern: "helm_release_name",
	},
	{
		name:         "InvalidDashboardHostname",
		varName:      "dashboard_hostname",
		invalidValue: "not-a-valid-fqdn",
		errorPattern: "dashboard_hostname",
	},
}

// TestTraefikModuleInputValidation uses table-driven tests to verify validation
// blocks for variables not covered by individual tests above.
func TestTraefikModuleInputValidation(t *testing.T) {
	t.Parallel()

	for _, tc := range inputValidationTestCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			vars := testVars(t)
			vars[tc.varName] = tc.invalidValue
			_, opts := setup(t, vars)
			_, err := terraform.InitAndPlanE(t, opts)
			require.Error(t, err, "expected validation error for %s", tc.varName)
			require.Regexp(t, regexp.MustCompile(tc.errorPattern), err.Error(),
				"expected error message to mention %s", tc.varName)
		})
	}
}

func TestTraefikExampleRejectsBlankKubeconfigPath(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, "")
}

func TestTraefikExampleRejectsWhitespaceKubeconfig(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, " \n\t ")
}

func TestTraefikModulePlanFailsWithoutKubeconfig(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, "/nonexistent/kubeconfig")
}

func TestTraefikModulePlanDetailedExitCode(t *testing.T) {
	t.Parallel()
	requireBinary(t, "tofu", "tofu not found; skipping detailed exit code plan")
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping detailed exit code plan")
	}
	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("traefik-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["cluster_issuer_name"] = fmt.Sprintf("issuer-%s", strings.ToLower(random.UniqueId()))
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

func TestTraefikModuleSupportsHelmValues(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	valuesDir := t.TempDir()
	valuesFile := filepath.Join(valuesDir, "values.yaml")
	fileContent := "additionalArguments:\n  - --log.level=DEBUG\n"
	require.NoError(t, os.WriteFile(valuesFile, []byte(fileContent), 0600))
	vars["helm_values"] = []string{"resources:\n  requests:\n    cpu: 100m"}
	vars["helm_values_files"] = []string{valuesFile}
	tfDir, opts := setup(t, vars)
	writeAutoTfvarsJSON(t, tfDir, vars)
	opts.Vars = map[string]interface{}{}
	// InitAndPlanE returns an error because the stub kubeconfig cannot connect to a real
	// cluster. However, the plan output is captured before the failure, allowing verification
	// that helm_values and helm_values_files are correctly merged into the Helm release.
	stdout, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Contains(t, stdout, "resources")
	require.Contains(t, stdout, "additionalArguments")
}

func TestTraefikModulePolicy(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")
	kubeconfig := requireEnvVar(t, "KUBECONFIG", "KUBECONFIG not set; skipping policy test")

	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("traefik-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["cluster_issuer_name"] = fmt.Sprintf("issuer-%s", strings.ToLower(random.UniqueId()))
	vars["kubeconfig_path"] = kubeconfig

	tfDir, planJSON := renderTraefikPlan(t, vars)
	policyPath := traefikPlanPolicyPath(tfDir)

	out, err := runConftestAgainstPlan(t, conftestRun{
		PlanPath:   planJSON,
		PolicyPath: policyPath,
		Kubeconfig: kubeconfig,
		ExtraArgs: []string{
			"--fail-on-warn",
			"--namespace",
			traefikPolicyPlanNamespace,
		},
		Timeout:    60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

func TestTraefikModulePolicyViolations(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")
	tfDir, _ := setup(t, testVars(t))
	policyPath := traefikPlanPolicyPath(tfDir)

	testCases := []struct {
		name          string
		payload       string
		expectedError string
	}{
		{
			name:          "InvalidACMEServer",
			payload:       `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"ClusterIssuer","metadata":{"name":"invalid"},"spec":{"acme":{"server":"http://invalid","email":"","solvers":[]}}}}}}]}`,
			expectedError: "must use HTTPS ACME server URL",
		},
		{
			name:          "MissingEmail",
			payload:       `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"ClusterIssuer","metadata":{"name":"no-email"},"spec":{"acme":{"server":"https://acme.example.com","email":"","solvers":[{"dns01":{}}]}}}}}}]}`,
			expectedError: "must have a valid ACME email address",
		},
		{
			name:          "NoSolvers",
			payload:       `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"ClusterIssuer","metadata":{"name":"no-solvers"},"spec":{"acme":{"server":"https://acme.example.com","email":"test@example.com","solvers":[]}}}}}}]}`,
			expectedError: "must have at least one ACME solver configured",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			planPath := writePlanFixture(t, tc.payload)
			violationOut, violationErr := runConftestAgainstPlan(t, conftestRun{
				PlanPath:   planPath,
				PolicyPath: policyPath,
				Kubeconfig: "",
				ExtraArgs: []string{
					"--namespace",
					traefikPolicyPlanNamespace,
				},
				Timeout:    10 * time.Second,
			})
			require.Error(t, violationErr, "expected conftest to report a violation")
			var exitErr *exec.ExitError
			require.ErrorAs(t, violationErr, &exitErr, "expected ExitError from conftest for policy violation")
			require.NotZero(t, exitErr.ExitCode(), "expected non-zero exit code for policy violation")
			stdout := string(violationOut)
			require.Contains(t, stdout, tc.expectedError, "expected policy violation error message")
		})
	}
}

func TestTraefikModulePolicyWarnStagingACME(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")
	tfDir, _ := setup(t, testVars(t))
	policyPath := traefikPlanPolicyPath(tfDir)

	payload := `{"resource_changes":[{"type":"kubernetes_manifest","change":{"after":{"manifest":{"kind":"ClusterIssuer","metadata":{"name":"staging"},"spec":{"acme":{"server":"https://acme-staging-v02.api.letsencrypt.org/directory","email":"test@example.com","privateKeySecretRef":{"name":"staging"},"solvers":[{"dns01":{"cloudflare":{}}}]}}}}}}]}`
	planPath := writePlanFixture(t, payload)
	// Warnings don't cause conftest to fail, so we just check the output contains the warning
	warnOut, err := runConftestAgainstPlan(t, conftestRun{
		PlanPath:   planPath,
		PolicyPath: policyPath,
		Kubeconfig: "",
		ExtraArgs: []string{
			"--namespace",
			traefikPolicyPlanNamespace,
		},
		Timeout:    10 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(warnOut))
	stdout := string(warnOut)
	require.Contains(t, stdout, "uses ACME staging server - certificates will not be trusted",
		"expected staging server warning in output")
}

func TestTraefikModuleApplyIfKubeconfigPresent(t *testing.T) {
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping apply test")
	}
	if os.Getenv("TRAEFIK_ACCEPT_APPLY") == "" {
		t.Skip("TRAEFIK_ACCEPT_APPLY not set; skipping apply test")
	}

	// Arrange: set up unique resource names for this test run
	expectedNamespace := fmt.Sprintf("traefik-terratest-%s", strings.ToLower(random.UniqueId()))
	expectedClusterIssuerName := fmt.Sprintf("issuer-%s", strings.ToLower(random.UniqueId()))

	vars := testVars(t)
	vars["namespace"] = expectedNamespace
	vars["cluster_issuer_name"] = expectedClusterIssuerName
	vars["kubeconfig_path"] = kubeconfig
	vars["http_to_https_redirect"] = true
	vars["dashboard_enabled"] = false
	vars["service_monitor_enabled"] = false

	_, opts := setup(t, vars)
	t.Cleanup(func() {
		terraform.Destroy(t, opts)
	})

	// Act
	terraform.InitAndApply(t, opts)

	// Assert: verify outputs match expected inputs
	namespace := terraform.Output(t, opts, "namespace")
	helmRelease := terraform.Output(t, opts, "helm_release_name")
	clusterIssuer := terraform.Output(t, opts, "cluster_issuer_name")
	ingressClassName := terraform.Output(t, opts, "ingress_class_name")

	require.Equal(t, expectedNamespace, namespace,
		"namespace output should match input")
	require.NotEmpty(t, helmRelease,
		"helm_release_name output should not be empty")
	require.Equal(t, expectedClusterIssuerName, clusterIssuer,
		"cluster_issuer_name output should match input")
	require.Equal(t, "traefik", ingressClassName,
		"ingress_class_name output should default to traefik")

	// Assert: verify cluster_issuer_ref structure if output exists
	if terraformOutputExists(t, opts, "cluster_issuer_ref") {
		clusterIssuerRef := terraform.OutputMap(t, opts, "cluster_issuer_ref")
		require.Equal(t, expectedClusterIssuerName, clusterIssuerRef["name"],
			"cluster_issuer_ref.name should match cluster_issuer_name input")
		require.Equal(t, "ClusterIssuer", clusterIssuerRef["kind"],
			"cluster_issuer_ref.kind should be ClusterIssuer")
		require.Equal(t, "cert-manager.io", clusterIssuerRef["group"],
			"cluster_issuer_ref.group should be cert-manager.io")
	}

	// Assert: verify dashboard_hostname is null when dashboard disabled
	if terraformOutputExists(t, opts, "dashboard_hostname") {
		dashboardHostname := terraform.Output(t, opts, "dashboard_hostname")
		require.Empty(t, dashboardHostname,
			"dashboard_hostname should be empty when dashboard is disabled")
	}

	// Assert: verify Helm release exists in state
	resourceAddr := fmt.Sprintf("module.%s.helm_release.%s[0]", traefikModuleName, traefikModuleName)
	stdout, err := terraform.RunTerraformCommandAndGetStdoutE(t, opts, "state", "show", resourceAddr)
	require.NoError(t, err)
	require.Contains(t, stdout, "traefik")
}
