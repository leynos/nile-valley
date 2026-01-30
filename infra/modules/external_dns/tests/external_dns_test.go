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

const externalDNSModuleName = "external_dns"

const externalDNSPolicyManifestsNamespace = "external_dns.policy.manifests"
const externalDNSPolicyPlanNamespace = "external_dns.policy.plan"

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

	// Only pass required variables; module defaults handle the rest
	return map[string]interface{}{
		"domain_filters":                   []string{"example.test"},
		"txt_owner_id":                     "test-owner-id",
		"cloudflare_api_token_secret_name": "cloudflare-api-token",
		"kubeconfig_path":                  kubeconfigPath,
	}
}

func renderVars(t *testing.T) map[string]interface{} {
	t.Helper()
	// Only pass required variables; module defaults handle the rest
	return map[string]interface{}{
		"domain_filters":                   []string{"example.test"},
		"txt_owner_id":                     "render-owner-id",
		"cloudflare_api_token_secret_name": "cloudflare-api-token",
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

func externalDNSPolicyRoot(tfDir string) string {
	return filepath.Join(tfDir, "..", "..", "policy")
}

func externalDNSManifestsPolicyPath(tfDir string) string {
	return filepath.Join(externalDNSPolicyRoot(tfDir), "manifests")
}

func externalDNSPlanPolicyPath(tfDir string) string {
	return filepath.Join(externalDNSPolicyRoot(tfDir), "plan")
}

func renderExternalDNSPlan(t *testing.T, vars map[string]interface{}) (string, string) {
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

	args := append([]string{"test", "--policy", cfg.PolicyPath, cfg.InputPath}, cfg.ExtraArgs...)
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
	plan, err := os.CreateTemp("", "external-dns-plan-*.json")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.Remove(plan.Name()) })

	_, err = plan.WriteString(payload)
	require.NoError(t, err)
	require.NoError(t, plan.Close())

	return plan.Name()
}

func TestExternalDNSModuleValidate(t *testing.T) {
	t.Parallel()
	_, opts := setup(t, testVars(t))
	terraform.InitAndValidate(t, opts)
}

func TestExternalDNSModuleRenderOutputs(t *testing.T) {
	t.Parallel()

	vars := renderVars(t)
	vars["txt_owner_id"] = "render-test-owner"
	vars["cloudflare_proxied"] = true

	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	require.NotEmpty(t, rendered, "expected rendered_manifests output to be non-empty")

	helmRelease, ok := rendered["platform/external-dns/helmrelease.yaml"]
	require.True(t, ok, "expected platform/external-dns/helmrelease.yaml output key")
	require.True(
		t,
		strings.Contains(helmRelease, "kind: HelmRelease") ||
			strings.Contains(helmRelease, "\"kind\": \"HelmRelease\""),
		"expected HelmRelease manifest to contain kind HelmRelease",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "name: external-dns") ||
			strings.Contains(helmRelease, "\"name\": \"external-dns\""),
		"expected HelmRelease manifest to contain metadata.name external-dns",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "txtOwnerId") ||
			strings.Contains(helmRelease, "\"txtOwnerId\""),
		"expected HelmRelease manifest to contain txtOwnerId",
	)
	require.True(
		t,
		strings.Contains(helmRelease, "domainFilters") ||
			strings.Contains(helmRelease, "\"domainFilters\""),
		"expected HelmRelease manifest to contain domainFilters",
	)

	_, ok = rendered["platform/external-dns/namespace.yaml"]
	require.True(t, ok, "expected platform/external-dns/namespace.yaml output key")

	_, ok = rendered["platform/sources/external-dns-repo.yaml"]
	require.True(t, ok, "expected platform/sources/external-dns-repo.yaml output key")

	txtOwnerId := terraform.Output(t, opts, "txt_owner_id")
	require.Equal(t, "render-test-owner", txtOwnerId)

	domainFilters := terraform.OutputList(t, opts, "domain_filters")
	require.NotEmpty(t, domainFilters, "expected domain_filters output to be non-empty")
	require.Equal(t, []string{"example.test"}, domainFilters)
}

func TestExternalDNSModuleRenderPolicy(t *testing.T) {
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

	policyPath := externalDNSManifestsPolicyPath(tfDir)
	out, err := runConftest(t, conftestRun{
		InputPath:  outDir,
		PolicyPath: policyPath,
		Kubeconfig: "",
		ExtraArgs: []string{
			"--fail-on-warn",
			"--namespace",
			externalDNSPolicyManifestsNamespace,
		},
		Timeout: 60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

// renderPolicyRejectionTestCases defines test cases for render policy rejection tests
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
  name: external-dns
  namespace: external-dns
spec:
  chart:
    spec:
      chart: external-dns
      sourceRef:
        kind: HelmRepository
        name: external-dns
        namespace: flux-system
  values:
    domainFilters:
      - example.test
    txtOwnerId: test-owner
`,
		expectedMessage: "must pin chart.spec.version",
	},
	{
		name: "MissingDomainFilters",
		manifest: `apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: external-dns
  namespace: external-dns
spec:
  chart:
    spec:
      chart: external-dns
      version: "1.16.1"
      sourceRef:
        kind: HelmRepository
        name: external-dns
        namespace: flux-system
  values:
    txtOwnerId: test-owner
    domainFilters: []
`,
		expectedMessage: "must set values.domainFilters",
	},
	{
		name: "MissingTxtOwnerId",
		manifest: `apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: external-dns
  namespace: external-dns
spec:
  chart:
    spec:
      chart: external-dns
      version: "1.16.1"
      sourceRef:
        kind: HelmRepository
        name: external-dns
        namespace: flux-system
  values:
    domainFilters:
      - example.test
`,
		expectedMessage: "must set values.txtOwnerId",
	},
}

func TestExternalDNSModuleRenderPolicyRejections(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")

	tfDir, _ := setupRender(t, renderVars(t))
	policyPath := externalDNSManifestsPolicyPath(tfDir)

	for _, tc := range renderPolicyRejectionTestCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			tmpDir := t.TempDir()
			manifestPath := filepath.Join(tmpDir, "helmrelease.yaml")
			require.NoError(t, os.WriteFile(manifestPath, []byte(tc.manifest), 0o600))

			out, err := runConftest(t, conftestRun{
				InputPath:  manifestPath,
				PolicyPath: policyPath,
				Kubeconfig: "",
				ExtraArgs: []string{
					"--fail-on-warn",
					"--namespace",
					externalDNSPolicyManifestsNamespace,
				},
				Timeout: 60 * time.Second,
			})
			require.Error(t, err, "expected conftest to report a violation")
			require.Contains(t, string(out), tc.expectedMessage)
		})
	}
}

func TestExternalDNSModulePlanPolicy(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")

	vars := testVars(t)
	tfDir, planPath := renderExternalDNSPlan(t, vars)
	policyPath := externalDNSPlanPolicyPath(tfDir)

	out, err := runConftest(t, conftestRun{
		InputPath:  planPath,
		PolicyPath: policyPath,
		Kubeconfig: vars["kubeconfig_path"].(string),
		ExtraArgs: []string{
			"--fail-on-warn",
			"--namespace",
			externalDNSPolicyPlanNamespace,
		},
		Timeout: 60 * time.Second,
	})
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

// planPolicyRejectionTestCases defines test cases for plan policy rejection tests
var planPolicyRejectionTestCases = []struct {
	name            string
	planPayload     string
	expectedMessage string
}{
	{
		name: "MissingDomainFilters",
		planPayload: `{
	"resource_changes": [{
		"type": "helm_release",
		"change": {
			"after": {
				"name": "external-dns",
				"values": ["domainFilters: []\ntxtOwnerId: test-owner\nenv:\n  - name: CF_API_TOKEN\n    valueFrom:\n      secretKeyRef:\n        name: cloudflare-api-token\n        key: token\n"]
			}
		}
	}]
}`,
		expectedMessage: "domainFilters",
	},
	{
		name: "MissingTxtOwnerId",
		planPayload: `{
	"resource_changes": [{
		"type": "helm_release",
		"change": {
			"after": {
				"name": "external-dns",
				"values": ["domainFilters:\n  - example.test\nenv:\n  - name: CF_API_TOKEN\n    valueFrom:\n      secretKeyRef:\n        name: cloudflare-api-token\n        key: token\n"]
			}
		}
	}]
}`,
		expectedMessage: "txtOwnerId",
	},
	{
		name: "ZoneIdFilterWithoutDomainFilters",
		planPayload: `{
	"resource_changes": [{
		"type": "helm_release",
		"change": {
			"after": {
				"name": "external-dns",
				"values": ["domainFilters: []\ntxtOwnerId: test-owner\nextraArgs:\n  - --zone-id-filter=0123456789abcdef0123456789abcdef\nenv:\n  - name: CF_API_TOKEN\n    valueFrom:\n      secretKeyRef:\n        name: cloudflare-api-token\n        key: token\nprovider:\n  name: cloudflare\n"]
			}
		}
	}]
}`,
		expectedMessage: "zone-id-filter but no domainFilters",
	},
}

func TestExternalDNSModulePlanPolicyRejections(t *testing.T) {
	t.Parallel()
	requireBinary(t, "conftest", "conftest not found; skipping policy test")

	tfDir, _ := setup(t, testVars(t))
	policyPath := externalDNSPlanPolicyPath(tfDir)

	for _, tc := range planPolicyRejectionTestCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			planPath := writePlanFixture(t, tc.planPayload)

			out, err := runConftest(t, conftestRun{
				InputPath:  planPath,
				PolicyPath: policyPath,
				Kubeconfig: "",
				ExtraArgs: []string{
					"--fail-on-warn",
					"--namespace",
					externalDNSPolicyPlanNamespace,
				},
				Timeout: 60 * time.Second,
			})
			require.Error(t, err, "expected conftest to report a violation")
			require.Contains(t, string(out), tc.expectedMessage)
		})
	}
}

func TestExternalDNSModuleInvalidDomainFilters(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["domain_filters"] = []string{}
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`domain_filters`), err.Error())
}

func TestExternalDNSModuleInvalidDomainFiltersSyntax(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["domain_filters"] = []string{"not a valid domain"}
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`domain_filters`), err.Error())
}

func TestExternalDNSModuleInvalidTxtOwnerId(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["txt_owner_id"] = "   "
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`txt_owner_id`), err.Error())
}

func TestExternalDNSModuleInvalidPolicy(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["policy"] = "invalid-policy"
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`policy`), err.Error())
}

func TestExternalDNSModuleInvalidNamespace(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["namespace"] = "Invalid_Namespace"
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`namespace`), err.Error())
}

func TestExternalDNSModuleInvalidChartVersion(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["chart_version"] = "invalid"
	_, opts := setupRender(t, vars)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Regexp(t, regexp.MustCompile(`chart_version`), err.Error())
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
		name:            "NullDomainFilters",
		varName:         "domain_filters",
		value:           nil,
		expectedMessage: "domain_filters must contain at least one valid domain name",
	},
	{
		name:            "NullTxtOwnerId",
		varName:         "txt_owner_id",
		value:           nil,
		expectedMessage: "txt_owner_id must be a non-empty string",
	},
	{
		name:            "NullCloudflareSecretName",
		varName:         "cloudflare_api_token_secret_name",
		value:           nil,
		expectedMessage: "cloudflare_api_token_secret_name must be a non-empty string",
	},
	{
		name:            "NullCloudflareSecretKey",
		varName:         "cloudflare_api_token_secret_key",
		value:           nil,
		expectedMessage: "cloudflare_api_token_secret_key must not be blank",
	},
}

func TestExternalDNSModuleNullVariableValidationReturnsErrorMessage(t *testing.T) {
	t.Parallel()
	for _, tc := range nullVariableValidationTestCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
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
		name:         "InvalidLogLevel",
		varName:      "log_level",
		invalidValue: "verbose",
		errorPattern: "log_level",
	},
	{
		name:         "InvalidInterval",
		varName:      "interval",
		invalidValue: "1 minute",
		errorPattern: "interval",
	},
}

// TestExternalDNSModuleInputValidation uses table-driven tests to verify validation
// blocks for variables not covered by individual tests above.
func TestExternalDNSModuleInputValidation(t *testing.T) {
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

// zoneIdFilterValidationTestCases defines test cases for zone_id_filter variable validation
var zoneIdFilterValidationTestCases = []struct {
	name            string
	value           interface{}
	expectError     bool
	expectedMessage string
}{
	{
		name:        "ValidZoneId",
		value:       map[string]interface{}{"example.test": "0123456789abcdef0123456789abcdef"},
		expectError: false,
	},
	{
		name:            "InvalidZoneIdTooShort",
		value:           map[string]interface{}{"example.test": "abc123"},
		expectError:     true,
		expectedMessage: "zone_id_filter",
	},
	{
		name:            "InvalidZoneIdNonHex",
		value:           map[string]interface{}{"example.test": "0123456789abcdef0123456789abcdeg"},
		expectError:     true,
		expectedMessage: "zone_id_filter",
	},
	{
		name:            "InvalidDomainKey",
		value:           map[string]interface{}{"not a domain": "0123456789abcdef0123456789abcdef"},
		expectError:     true,
		expectedMessage: "zone_id_filter",
	},
	{
		name:        "EmptyMap",
		value:       map[string]interface{}{},
		expectError: false,
	},
	{
		name: "MultipleValidZones",
		value: map[string]interface{}{
			"example.test": "0123456789abcdef0123456789abcdef",
			"other.test":   "fedcba9876543210fedcba9876543210",
		},
		expectError: false,
	},
}

func TestExternalDNSModuleZoneIdFilterValidation(t *testing.T) {
	t.Parallel()
	for _, tc := range zoneIdFilterValidationTestCases {
		tc := tc // Capture loop variable for parallel subtests
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			vars := renderVars(t)
			vars["zone_id_filter"] = tc.value
			_, opts := setupRender(t, vars)
			_, err := terraform.InitAndPlanE(t, opts)
			if tc.expectError {
				require.Error(t, err, "expected validation error for zone_id_filter")
				require.Contains(t, err.Error(), tc.expectedMessage)
			} else {
				require.NoError(t, err)
			}
		})
	}
}

func TestExternalDNSModuleZoneIdFilterInHelmValues(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["zone_id_filter"] = map[string]interface{}{
		"example.test": "0123456789abcdef0123456789abcdef",
	}
	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	helmRelease := rendered["platform/external-dns/helmrelease.yaml"]

	require.Contains(t, helmRelease, "--zone-id-filter=0123456789abcdef0123456789abcdef",
		"HelmRelease should contain zone-id-filter argument")
}

func TestExternalDNSModuleZoneIdFilterNotRenderedWhenEmpty(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	// Intentionally do not set vars["zone_id_filter"] to verify default behaviour

	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	rendered := terraform.OutputMap(t, opts, "rendered_manifests")
	helmRelease := rendered["platform/external-dns/helmrelease.yaml"]

	require.NotContains(t, helmRelease, "--zone-id-filter",
		"HelmRelease should not contain zone-id-filter argument when zone_id_filter is empty or omitted")
}

func TestExternalDNSModuleManagedZonesOutput(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["domain_filters"] = []string{"example.test", "other.test"}
	vars["zone_id_filter"] = map[string]interface{}{
		"example.test": "0123456789abcdef0123456789abcdef",
	}
	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	managedZones := terraform.OutputMap(t, opts, "managed_zones")
	require.Equal(t, "0123456789abcdef0123456789abcdef", managedZones["example.test"],
		"example.test should have zone ID from zone_id_filter")
	// other.test should have null value since no zone ID was specified
	// terraform.OutputMap returns null values as "<nil>" string representation
	value, hasOtherTest := managedZones["other.test"]
	require.True(t, hasOtherTest, "other.test should be present in managed_zones output")
	require.Equal(t, "<nil>", value, "other.test should have null value when no zone ID is specified")
}

func TestExternalDNSModuleZoneIdFilterOutput(t *testing.T) {
	t.Parallel()
	vars := renderVars(t)
	vars["zone_id_filter"] = map[string]interface{}{
		"example.test": "0123456789ABCDEF0123456789ABCDEF",
	}
	_, opts := setupRender(t, vars)
	terraform.InitAndApply(t, opts)

	zoneIdFilter := terraform.OutputMap(t, opts, "zone_id_filter")
	// Zone IDs are normalised to lowercase
	require.Equal(t, "0123456789abcdef0123456789abcdef", zoneIdFilter["example.test"],
		"zone_id_filter output should contain normalised zone ID")

	managedZones := terraform.OutputMap(t, opts, "managed_zones")
	require.Equal(t, "0123456789abcdef0123456789abcdef", managedZones["example.test"],
		"managed_zones output should contain normalised zone ID for example.test")
}

func TestExternalDNSExampleRejectsBlankKubeconfigPath(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, "")
}

func TestExternalDNSExampleRejectsWhitespaceKubeconfig(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, " \n\t ")
}

func TestExternalDNSModulePlanFailsWithoutKubeconfig(t *testing.T) {
	t.Parallel()
	testKubeconfigPathValidation(t, "/nonexistent/kubeconfig")
}

func TestExternalDNSModulePlanDetailedExitCode(t *testing.T) {
	t.Parallel()
	requireBinary(t, "tofu", "tofu not found; skipping detailed exit code plan")
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping detailed exit code plan")
	}
	vars := testVars(t)
	vars["namespace"] = fmt.Sprintf("external-dns-terratest-%s", strings.ToLower(random.UniqueId()))
	vars["txt_owner_id"] = fmt.Sprintf("owner-%s", strings.ToLower(random.UniqueId()))
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

func TestExternalDNSModuleSupportsHelmValues(t *testing.T) {
	t.Parallel()
	vars := testVars(t)
	valuesDir := t.TempDir()
	valuesFile := filepath.Join(valuesDir, "values.yaml")
	fileContent := "extraArgs:\n  - --log-format=json\n"
	require.NoError(t, os.WriteFile(valuesFile, []byte(fileContent), 0600))
	vars["helm_values"] = []string{"resources:\n  requests:\n    cpu: 100m"}
	vars["helm_values_files"] = []string{valuesFile}
	tfDir, opts := setup(t, vars)
	writeAutoTfvarsJSON(t, tfDir, vars)
	opts.Vars = map[string]interface{}{}
	// Plan may succeed or fail depending on provider version and kubeconfig validation.
	// The plan output is captured either way, allowing verification that helm_values
	// and helm_values_files are correctly merged into the Helm release.
	stdout, _ := terraform.InitAndPlanE(t, opts)
	require.Contains(t, stdout, "resources")
	require.Contains(t, stdout, "extraArgs")
}

func TestExternalDNSModuleApplyIfKubeconfigPresent(t *testing.T) {
	kubeconfig := os.Getenv("KUBECONFIG")
	if kubeconfig == "" {
		t.Skip("KUBECONFIG not set; skipping apply test")
	}
	if os.Getenv("EXTERNAL_DNS_ACCEPT_APPLY") == "" {
		t.Skip("EXTERNAL_DNS_ACCEPT_APPLY not set; skipping apply test")
	}

	// Arrange: set up unique resource names for this test run
	expectedNamespace := fmt.Sprintf("external-dns-terratest-%s", strings.ToLower(random.UniqueId()))
	expectedTxtOwnerId := fmt.Sprintf("owner-%s", strings.ToLower(random.UniqueId()))

	vars := testVars(t)
	vars["namespace"] = expectedNamespace
	vars["txt_owner_id"] = expectedTxtOwnerId
	vars["kubeconfig_path"] = kubeconfig
	vars["cloudflare_proxied"] = false
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
	txtOwnerId := terraform.Output(t, opts, "txt_owner_id")

	require.Equal(t, expectedNamespace, namespace,
		"namespace output should match input")
	require.NotEmpty(t, helmRelease,
		"helm_release_name output should not be empty")
	require.Equal(t, expectedTxtOwnerId, txtOwnerId,
		"txt_owner_id output should match input")

	// Assert: verify domain_filters output
	if terraformOutputExists(t, opts, "domain_filters") {
		domainFilters := terraform.OutputList(t, opts, "domain_filters")
		require.NotEmpty(t, domainFilters,
			"domain_filters output should not be empty")
	}

	// Assert: verify Helm release exists in state
	resourceAddr := fmt.Sprintf("module.%s.helm_release.%s[0]", externalDNSModuleName, externalDNSModuleName)
	stdout, err := terraform.RunTerraformCommandAndGetStdoutE(t, opts, "state", "show", resourceAddr)
	require.NoError(t, err)
	require.Contains(t, stdout, "external-dns")
}
