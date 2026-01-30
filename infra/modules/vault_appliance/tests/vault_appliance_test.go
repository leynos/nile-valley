package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

func baseVars(t *testing.T) map[string]interface{} {
	t.Helper()
	suffix := strings.ToLower(random.UniqueId())
	name := fmt.Sprintf("vault-%s", suffix)
	commonName := fmt.Sprintf("%s.example.test", name)
	return map[string]interface{}{
		"name":                    name,
		"region":                  "nyc1",
		"tags":                    []string{"terratest"},
		"ha_enabled":              false,
		"allowed_ssh_cidrs":       []string{"203.0.113.5/32"},
		"certificate_common_name": commonName,
		"certificate_dns_names":   []string{commonName},
		"certificate_ip_sans":     []string{},
		"recovery_shares":         5,
		"recovery_threshold":      3,
		"recovery_key_length":     32,
	}
}

func setupTerraform(t *testing.T, vars map[string]interface{}, env map[string]string) (string, *terraform.Options) {
	t.Helper()
	return testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, env),
	})
}

func requireBinary(t *testing.T, name, skipMessage string) {
	t.Helper()
	if _, err := exec.LookPath(name); err != nil {
		t.Skip(skipMessage)
	}
}

func renderPlanJSON(t *testing.T, vars map[string]interface{}) (string, string) {
	t.Helper()
	env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
	tfDir, opts := setupTerraform(t, vars, env)
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

func policyPath(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	require.True(t, ok, "unable to resolve caller path")
	policyDir := filepath.Join(filepath.Dir(thisFile), "..", "policy")
	entries, err := os.ReadDir(policyDir)
	require.NoError(t, err, "policy directory not readable")
	hasRego := false
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".rego") {
			hasRego = true
			break
		}
	}
	require.True(t, hasRego, "policy directory contains no .rego files")
	return policyDir
}

func runConftestPolicyTest(t *testing.T, vars map[string]interface{}) ([]byte, error) {
	t.Helper()

	requireBinary(t, "conftest", "conftest not installed; skipping policy test")
	_, planJSON := renderPlanJSON(t, vars)
	return runConftestWithPlan(t, planJSON)
}

func runConftestWithPlan(t *testing.T, planJSON string) ([]byte, error) {
	t.Helper()

	requireBinary(t, "conftest", "conftest not installed; skipping policy test")
	policyDir := policyPath(t)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "conftest", "test", planJSON, "--policy", policyDir, "--namespace", "policy")
	cmd.Env = testutil.TerraformEnv(t, nil)
	output, err := cmd.CombinedOutput()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "conftest timed out")

	return output, err
}

func mutatePlanJSON(t *testing.T, planJSON string, mutate func(map[string]interface{})) string {
	t.Helper()

	data, err := os.ReadFile(planJSON)
	require.NoError(t, err, "failed to read plan JSON")

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()

	var document map[string]interface{}
	require.NoError(t, decoder.Decode(&document), "failed to decode plan JSON")

	mutate(document)

	mutatedPath := filepath.Join(t.TempDir(), filepath.Base(planJSON))
	mutated, err := json.MarshalIndent(document, "", "  ")
	require.NoError(t, err, "failed to encode mutated plan JSON")
	require.NoError(t, os.WriteFile(mutatedPath, mutated, 0600))

	return mutatedPath
}

func mutateLoadBalancerForwardingRules(t *testing.T, doc map[string]interface{}, mutate func(map[string]interface{})) {
	t.Helper()

	mutateResourceRules(t, doc, "digitalocean_loadbalancer", []ruleSelector{
		{section: "after", list: "forwarding_rule"},
		{section: "after_unknown", list: "forwarding_rule"},
	}, mutate)
}

func mutateFirewallInboundRules(t *testing.T, doc map[string]interface{}, mutate func(map[string]interface{})) {
	t.Helper()

	mutateResourceRules(t, doc, "digitalocean_firewall", []ruleSelector{
		{section: "after", list: "inbound_rule"},
		{section: "after_unknown", list: "inbound_rule"},
	}, mutate)
}

type ruleSelector struct {
	section string
	list    string
}

func mutateResourceRules(t *testing.T, doc map[string]interface{}, resourceType string, selectors []ruleSelector, mutate func(map[string]interface{})) {
	t.Helper()

	mutateResourceChanges(t, doc, resourceType, func(delta map[string]interface{}) {
		for _, selector := range selectors {
			mutateRulesInSection(t, delta, selector, mutate)
		}
	})
}

func mutateResourceRuleList(t *testing.T, doc map[string]interface{}, resourceType string, selector ruleSelector, mutate func([]interface{}) []interface{}) {
	t.Helper()

	mutateResourceChanges(t, doc, resourceType, func(delta map[string]interface{}) {
		mutateRuleList(t, delta, selector, mutate)
	})
}

func mutateResourceChanges(t *testing.T, doc map[string]interface{}, resourceType string, visit func(map[string]interface{})) {
	t.Helper()

	changes, ok := doc["resource_changes"].([]interface{})
	require.True(t, ok, "plan JSON missing resource_changes")

	for _, raw := range changes {
		change, ok := raw.(map[string]interface{})
		if !ok || !isResourceType(change, resourceType) {
			continue
		}

		delta, _ := change["change"].(map[string]interface{})
		if delta == nil {
			continue
		}

		visit(delta)
	}
}

func isResourceType(change map[string]interface{}, expected string) bool {
	typ, ok := change["type"].(string)
	return ok && typ == expected
}

func mutateRulesInSection(t *testing.T, delta map[string]interface{}, selector ruleSelector, mutate func(map[string]interface{})) {
	t.Helper()

	_, raw, ok := accessRuleSection(delta, selector)
	if !ok {
		return
	}

	mutateListEntries(t, raw, mutate)
}

func mutateRuleList(t *testing.T, delta map[string]interface{}, selector ruleSelector, mutate func([]interface{}) []interface{}) {
	t.Helper()

	container, raw, ok := accessRuleSection(delta, selector)
	if !ok {
		return
	}

	rules, _ := raw.([]interface{})
	container[selector.list] = mutate(rules)
}

func accessRuleSection(delta map[string]interface{}, selector ruleSelector) (map[string]interface{}, interface{}, bool) {
	container, _ := delta[selector.section].(map[string]interface{})
	if container == nil {
		return nil, nil, false
	}

	raw, exists := container[selector.list]
	if !exists {
		return nil, nil, false
	}

	return container, raw, true
}

func mutateListEntries(t *testing.T, raw interface{}, mutate func(map[string]interface{})) {
	t.Helper()

	if _, ok := raw.(bool); ok {
		require.Fail(t, "cannot mutate unknown inbound_rule; ensure rules are materialised in the plan for this test")
		return
	}

	rules, _ := raw.([]interface{})
	for _, ruleRaw := range rules {
		rule, ok := ruleRaw.(map[string]interface{})
		if !ok {
			continue
		}
		mutate(rule)
	}
}

func appendLoadBalancerForwardingRule(t *testing.T, doc map[string]interface{}, rule map[string]interface{}) {
	t.Helper()

	mutateResourceRuleList(t, doc, "digitalocean_loadbalancer", ruleSelector{section: "after", list: "forwarding_rule"}, func(rules []interface{}) []interface{} {
		return append(rules, rule)
	})
}

func TestMutateFirewallInboundRules_MalformedEntries(t *testing.T) {
	t.Parallel()
	doc := map[string]interface{}{
		"resource_changes": []interface{}{
			map[string]interface{}{
				"type": "digitalocean_firewall",
				"change": map[string]interface{}{
					"after": map[string]interface{}{
						"inbound_rule": []interface{}{
							"not_a_map",
							map[string]interface{}{"unexpected_field": 123},
							map[string]interface{}{"source_load_balancer_uids": []interface{}{"lb-uid"}},
						},
					},
					"after_unknown": map[string]interface{}{
						"inbound_rule": []interface{}{
							map[string]interface{}{"source_addresses": []interface{}{"10.0.0.1/32"}},
							42,
						},
					},
				},
			},
		},
	}

	mutated := 0
	mutateFirewallInboundRules(t, doc, func(rule map[string]interface{}) {
		if _, ok := rule["source_load_balancer_uids"]; ok {
			mutated++
			return
		}
		if _, ok := rule["source_addresses"]; ok {
			mutated++
		}
	})

	require.Equal(t, 2, mutated, "expected only well-formed inbound rules to be mutated")
}

func TestMutateFirewallInboundRulesFailsOnUnknownList(t *testing.T) {
	t.Parallel()

	doc := map[string]interface{}{
		"resource_changes": []interface{}{
			map[string]interface{}{
				"type": "digitalocean_firewall",
				"change": map[string]interface{}{
					"after_unknown": map[string]interface{}{
						"inbound_rule": true,
					},
				},
			},
		},
	}

	ok := t.Run("detect unknown inbound rules", func(t *testing.T) {
		mutateFirewallInboundRules(t, doc, func(map[string]interface{}) {
			t.Fatal("mutate callback must not be invoked for unknown inbound_rule")
		})
	})

	require.False(t, ok, "mutateFirewallInboundRules must fail when inbound_rule is unknown")
}

func TestVaultApplianceModuleValidate(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
	_, opts := setupTerraform(t, vars, env)
	terraform.InitAndValidate(t, opts)
}

func TestVaultApplianceModuleValidateErrors(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mutateVars     func(map[string]interface{})
		expectedDetail string
	}{
		"missing region": {
			mutateVars: func(vars map[string]interface{}) {
				delete(vars, "region")
			},
			expectedDetail: "region",
		},
		"invalid load balancer algorithm": {
			mutateVars: func(vars map[string]interface{}) {
				vars["load_balancer_algorithm"] = "invalid-algorithm"
			},
			expectedDetail: "load_balancer_algorithm",
		},
	}

	for name, tc := range tests {
		tc := tc
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			vars := baseVars(t)
			tc.mutateVars(vars)
			env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
			_, opts := setupTerraform(t, vars, env)

			err := terraform.InitAndValidateE(t, opts)
			require.Error(t, err, "expected validation to fail")
			if tc.expectedDetail != "" {
				require.Contains(t, err.Error(), tc.expectedDetail)
			}
		})
	}
}

func TestVaultAppliancePlanUnauthenticated(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	env := map[string]string{"DIGITALOCEAN_TOKEN": ""}
	_, opts := setupTerraform(t, vars, env)

	_, err := terraform.InitAndPlanE(t, opts)
	if err == nil {
		_, err = terraform.ApplyE(t, opts)
	}
	require.Error(t, err, "expected unauthenticated plan/apply to fail")

	combined := err.Error()
	re := regexp.MustCompile(`(?i)(authentication|authenticate|token|unauthori[sz]ed|credentials)`)
	require.Truef(t, re.MatchString(combined), "error %q should reference authentication", combined)
}

func TestVaultAppliancePolicyPasses(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	output, err := runConftestPolicyTest(t, vars)
	require.NoErrorf(t, err, "conftest reported failure: %s", string(output))
}

func TestVaultAppliancePolicyRejectsOpenSSH(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	vars["allowed_ssh_cidrs"] = []string{"0.0.0.0/0"}

	output, err := runConftestPolicyTest(t, vars)
	require.Error(t, err, "expected conftest to reject public SSH")
	require.Contains(t, string(output), "must not expose SSH")
}

func TestVaultAppliancePolicyEnforcesHTTPS(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	_, planJSON := renderPlanJSON(t, vars)
	mutated := mutatePlanJSON(t, planJSON, func(doc map[string]interface{}) {
		mutateLoadBalancerForwardingRules(t, doc, func(rule map[string]interface{}) {
			rule["entry_protocol"] = "http"
			rule["entry_port"] = json.Number("80")
		})
	})

	output, err := runConftestWithPlan(t, mutated)
	require.Error(t, err, "expected conftest to reject HTTP-only load balancer rules")
	require.Contains(t, string(output), "must terminate HTTPS on port 443")
}

func TestVaultAppliancePolicyRejectsMixedHTTPAndHTTPSRules(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	_, planJSON := renderPlanJSON(t, vars)
	mutated := mutatePlanJSON(t, planJSON, func(doc map[string]interface{}) {
		var template map[string]interface{}
		mutateLoadBalancerForwardingRules(t, doc, func(rule map[string]interface{}) {
			if template != nil {
				return
			}
			template = map[string]interface{}{}
			for k, v := range rule {
				template[k] = v
			}
		})

		require.NotNil(t, template, "expected to capture existing forwarding rule template")

		httpRule := map[string]interface{}{}
		for k, v := range template {
			httpRule[k] = v
		}
		httpRule["entry_protocol"] = "http"
		httpRule["entry_port"] = json.Number("80")
		httpRule["target_protocol"] = "http"
		delete(httpRule, "certificate_id")
		delete(httpRule, "tls_passthrough")

		appendLoadBalancerForwardingRule(t, doc, httpRule)
	})

	output, err := runConftestWithPlan(t, mutated)
	require.Error(t, err, "expected conftest to reject mixed HTTP/HTTPS forwarding rules")
	require.Contains(t, string(output), "must not expose HTTP forwarding rules")
}

func TestVaultAppliancePolicyRedirectsHTTPToHTTPS(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	vars["load_balancer_redirect_http_to_https"] = false

	output, err := runConftestPolicyTest(t, vars)
	require.Error(t, err, "expected conftest to require HTTP to HTTPS redirection")
	require.Contains(t, string(output), "must redirect HTTP to HTTPS")
}

func testFirewallPolicyViolation(t *testing.T, mutate func(map[string]interface{}), assert func(*testing.T, []byte, error)) {
	t.Helper()

	vars := baseVars(t)
	_, planJSON := renderPlanJSON(t, vars)
	mutated := mutatePlanJSON(t, planJSON, mutate)

	output, err := runConftestWithPlan(t, mutated)
	assert(t, output, err)
}

func TestVaultAppliancePolicyLoadBalancerFirewallRules(t *testing.T) {
	t.Parallel()
	testFirewallPolicyViolation(t, func(doc map[string]interface{}) {
		mutateFirewallInboundRules(t, doc, func(rule map[string]interface{}) {
			delete(rule, "source_load_balancer_uids")
		})
	}, func(t *testing.T, output []byte, err error) {
		require.Error(t, err, "expected conftest to require load balancer firewall rules")
		require.Contains(t, string(output), "must allow traffic from the managed load balancer")
	})
}

func TestVaultAppliancePolicyRejectsPublicLoadBalancerFirewallSources(t *testing.T) {
	t.Parallel()
	testFirewallPolicyViolation(t, func(doc map[string]interface{}) {
		mutateFirewallInboundRules(t, doc, func(rule map[string]interface{}) {
			rule["source_addresses"] = []interface{}{"0.0.0.0/0", "::/0"}
			delete(rule, "source_load_balancer_uids")
		})
	}, func(t *testing.T, output []byte, err error) {
		require.Error(t, err, "expected conftest to reject public firewall sources")
		require.Contains(t, string(output), "must not allow traffic from 0.0.0.0/0")
		require.Contains(t, string(output), "must not allow traffic from ::/0")
	})
}

func TestVaultAppliancePolicyRejectsUnknownPublicLoadBalancerFirewallSources(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	_, planJSON := renderPlanJSON(t, vars)
	mutated := mutatePlanJSON(t, planJSON, func(doc map[string]interface{}) {
		var template map[string]interface{}
		mutateFirewallInboundRules(t, doc, func(rule map[string]interface{}) {
			if template != nil {
				return
			}
			template = map[string]interface{}{}
			for k, v := range rule {
				template[k] = v
			}
		})

		require.NotNil(t, template, "expected to capture existing inbound rule template")

		mutateResourceRuleList(t, doc, "digitalocean_firewall", ruleSelector{section: "after_unknown", list: "inbound_rule"}, func(rules []interface{}) []interface{} {
			cloned := append([]interface{}{}, rules...)
			newRule := map[string]interface{}{}
			for k, v := range template {
				newRule[k] = v
			}
			newRule["source_addresses"] = []interface{}{"::/0"}
			delete(newRule, "source_load_balancer_uids")
			return append(cloned, newRule)
		})
	})

	output, err := runConftestWithPlan(t, mutated)
	require.Error(t, err, "expected conftest to reject public firewall sources in unknown rules")
	require.Contains(t, string(output), "must not allow traffic from ::/0")
}

func TestVaultApplianceInvalidRecoveryThreshold(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	vars["recovery_shares"] = 2
	vars["recovery_threshold"] = 3
	env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
	_, opts := setupTerraform(t, vars, env)
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Contains(t, err.Error(), "recovery_threshold cannot exceed recovery_shares")
}

func TestVaultApplianceHAPlanRendersTwoDroplets(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	vars["ha_enabled"] = true
	env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
	tfDir, opts := setupTerraform(t, vars, env)
	plan, err := terraform.InitAndPlanE(t, opts)
	require.NoError(t, err)
	require.Contains(t, plan, "digitalocean_droplet.vault[1]", "expected plan to create a second droplet in HA mode")
	t.Cleanup(func() { _ = os.Remove(filepath.Join(tfDir, "terraform.tfstate")) })
}

func TestVaultApplianceDetailedExitCode(t *testing.T) {
	t.Parallel()
	vars := baseVars(t)
	env := map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}
	tfDir, opts := setupTerraform(t, vars, env)
	terraform.Init(t, opts)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	args := terraform.FormatArgs(opts, "plan", "-detailed-exitcode")
	command := exec.CommandContext(ctx, "tofu", args...)
	command.Dir = opts.TerraformDir
	command.Env = testutil.TerraformEnv(t, opts.EnvVars)
	output, err := command.CombinedOutput()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "terraform plan timed out")
	exitErr := &exec.ExitError{}
	require.ErrorAs(t, err, &exitErr, "expected detailed exit code to produce non-zero exit status")
	require.Equal(t, 2, exitErr.ExitCode(), "expected plan to return detailed exit code 2 when creating resources\nOutput: %s", string(output))
	t.Cleanup(func() { _ = os.Remove(filepath.Join(tfDir, "terraform.tfstate")) })
}

func TestVaultApplianceApplyWhenExplicitlyAuthorised(t *testing.T) {
	token := os.Getenv("DIGITALOCEAN_TOKEN")
	if token == "" {
		t.Skip("DIGITALOCEAN_TOKEN not set; skipping apply test")
	}
	if strings.ToLower(os.Getenv("VAULT_APPLIANCE_ACCEPT_APPLY")) != "true" {
		t.Skip("VAULT_APPLIANCE_ACCEPT_APPLY must be 'true' to permit live apply tests")
	}

	vars := baseVars(t)
	vars["ha_enabled"] = false
	env := map[string]string{"DIGITALOCEAN_TOKEN": token}
	_, opts := setupTerraform(t, vars, env)

	defer terraform.Destroy(t, opts)
	terraform.InitAndApply(t, opts)

	endpoint := terraform.OutputMap(t, opts, "public_endpoint")
	require.NotEmpty(t, endpoint["name"], "expected name in public_endpoint output")
	require.NotEmpty(t, endpoint["ip"], "expected IP in public_endpoint output")

	ca := terraform.Output(t, opts, "ca_certificate")
	require.NotEmpty(t, ca, "expected CA certificate to be populated")

	var recoveryKeys []string
	rawKeys := terraform.Output(t, opts, "recovery_keys")
	require.NoError(t, json.Unmarshal([]byte(rawKeys), &recoveryKeys))
	require.Len(t, recoveryKeys, 5)
}
