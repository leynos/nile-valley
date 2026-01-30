package tests

import (
	"context"
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

func testVars() map[string]interface{} {
	vars := map[string]interface{}{
		"cluster_name": "terratest-cluster",
		"region":       "nyc1",
		"node_pools": []map[string]interface{}{
			{
				"name":       "default",
				"size":       "s-2vcpu-2gb",
				"node_count": 2,
				"auto_scale": false,
				"min_nodes":  2,
				"max_nodes":  2,
			},
		},
		"tags":              []string{"terratest"},
		"expose_kubeconfig": true,
	}
	return vars
}

func withVersion(vars map[string]interface{}, version string) map[string]interface{} {
	out := make(map[string]interface{}, len(vars)+1)
	for k, v := range vars {
		out[k] = v
	}
	if version != "" {
		out["kubernetes_version"] = version
	}
	return out
}

// versionOverride returns the optional Kubernetes version requested by the
// environment via DOKS_KUBERNETES_VERSION. When unset,
// Terraform applies the module's pinned default.
func versionOverride() string {
	return testutil.KubernetesVersion()
}

func TestDoksModuleValidate(t *testing.T) {
	t.Parallel()

	vars := testVars()
	vars["cluster_name"] = fmt.Sprintf("terratest-%s", strings.ToLower(random.UniqueId()))
	vars = withVersion(vars, versionOverride())
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}),
	})
	terraform.InitAndValidate(t, opts)
}

func TestDoksModulePlanUnauthenticated(t *testing.T) {
	t.Parallel()

	vars := testVars()
	vars["cluster_name"] = fmt.Sprintf("terratest-%s", strings.ToLower(random.UniqueId()))
	vars = withVersion(vars, versionOverride())
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, map[string]string{"DIGITALOCEAN_TOKEN": ""}),
	})

	_, err := terraform.InitAndPlanE(t, opts)
	if err == nil {
		_, err = terraform.ApplyE(t, opts)
	}
	require.Error(t, err, "expected error when DIGITALOCEAN_TOKEN is missing")

	authErr := strings.ToLower(err.Error())
	re := regexp.MustCompile(`unable to authenticate|no api token|invalid token|not authenticated|missing token|authentication failed`)
	require.Truef(t, re.MatchString(authErr), "error message %q did not mention authentication failure", err.Error())
}

func TestDoksModuleApplyIfTokenPresent(t *testing.T) {
	token := os.Getenv("DIGITALOCEAN_TOKEN")
	if token == "" {
		t.Skip("DIGITALOCEAN_TOKEN not set; skipping apply test")
	}

	vars := testVars()
	vars["cluster_name"] = fmt.Sprintf("terratest-%s", strings.ToLower(random.UniqueId()))
	vars = withVersion(vars, versionOverride())
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, map[string]string{"DIGITALOCEAN_TOKEN": token}),
	})

	defer terraform.Destroy(t, opts)
	terraform.InitAndApply(t, opts)

	clusterID := terraform.Output(t, opts, "cluster_id")
	endpoint := terraform.Output(t, opts, "endpoint")
	kubeconfig := terraform.Output(t, opts, "kubeconfig")

	require.NotEmpty(t, clusterID, "expected cluster_id output to be set")
	require.NotEmpty(t, endpoint, "expected endpoint output to be set")
	require.NotEmpty(t, kubeconfig, "expected kubeconfig output to be set")

}

func TestDoksModulePolicy(t *testing.T) {
	t.Parallel()
	if _, err := exec.LookPath("conftest"); err != nil {
		t.Skip("conftest not found; skipping policy test")
	}

	vars := testVars()
	vars["cluster_name"] = fmt.Sprintf("terratest-%s", strings.ToLower(random.UniqueId()))
	vars = withVersion(vars, versionOverride())
	tfDir, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "..",
		TfSubDir:      "examples/basic",
		Vars:          vars,
		EnvVars:       testutil.TerraformEnvVars(t, map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}),
	})

	planFile := filepath.Join(tfDir, "tfplan.binary")
	opts.PlanFilePath = planFile
	terraform.InitAndPlan(t, opts)
	t.Cleanup(func() { _ = os.Remove(planFile) })

	show, err := terraform.RunTerraformCommandE(t, opts, "show", "-json", planFile)
	require.NoError(t, err)
	jsonPath := filepath.Join(tfDir, "plan.json")
	require.NoError(t, os.WriteFile(jsonPath, []byte(show), 0600))
	t.Cleanup(func() { _ = os.Remove(jsonPath) })

	// Resolve policy dir relative to this source file.
	_, thisFile, _, ok := runtime.Caller(0)
	require.True(t, ok, "unable to resolve caller path")
	thisDir := filepath.Dir(thisFile)
	policyPath := filepath.Join(thisDir, "..", "policy")
	entries, readErr := os.ReadDir(policyPath)
	require.NoError(t, readErr, "policy directory not found: %s", policyPath)
	hasRego := false
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".rego") {
			hasRego = true
			break
		}
	}
	require.True(t, hasRego, "no .rego files found in %s", policyPath)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "conftest", "test", jsonPath, "--policy", policyPath)
	cmd.Dir = tfDir
	cmd.Env = testutil.TerraformEnv(t, nil)
	output, err := cmd.CombinedOutput()
	require.NotEqual(t, context.DeadlineExceeded, ctx.Err(), "conftest timed out")
	require.NoErrorf(t, err, "conftest failed: %s", string(output))
}

func getInvalidInputTestCases() map[string]struct {
	Vars        map[string]interface{}
	ErrContains string
} {
	// Each case represents an invalid configuration expected to fail
	// module validation. The cases mirror policy enforcement to catch
	// mistakes early.
	return map[string]struct {
		Vars        map[string]interface{}
		ErrContains string
	}{
		"EmptyClusterName": {
			Vars: map[string]interface{}{
				"cluster_name": "",
				"region":       "nyc1",
				"node_pools":   testVars()["node_pools"],
			},
			ErrContains: "cluster_name must not be empty",
		},
		"InvalidRegion": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "invalid",
				"node_pools":   testVars()["node_pools"],
			},
			ErrContains: "region must be a valid DigitalOcean slug",
		},
		"InvalidKubernetesVersion": {
			Vars: withVersion(map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools":   testVars()["node_pools"],
			}, "1.28"),
			ErrContains: "kubernetes_version must match",
		},
		"EmptyNodePools": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools":   []map[string]interface{}{},
			},
			ErrContains: "node_pools must not be empty",
		},
		"OneNode": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools": []map[string]interface{}{
					{
						"name":       "default",
						"size":       "s-2vcpu-2gb",
						"node_count": 1,
						"auto_scale": false,
						"min_nodes":  1,
						"max_nodes":  1,
					},
				},
			},
			ErrContains: "node_count >= 2",
		},
		"MinNodesZero": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools": []map[string]interface{}{
					{
						"name":       "default",
						"size":       "s-2vcpu-2gb",
						"node_count": 2,
						"auto_scale": false,
						"min_nodes":  0,
						"max_nodes":  2,
					},
				},
			},
			ErrContains: "min_nodes >= 1",
		},
		"MaxLessThanNodeCount": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools": []map[string]interface{}{
					{
						"name":       "default",
						"size":       "s-2vcpu-2gb",
						"node_count": 3,
						"auto_scale": false,
						"min_nodes":  1,
						"max_nodes":  2,
					},
				},
			},
			ErrContains: "min_nodes <= node_count <=",
		},
		"MinGreaterThanNodeCount": {
			Vars: map[string]interface{}{
				"cluster_name": "terratest-cluster",
				"region":       "nyc1",
				"node_pools": []map[string]interface{}{
					{
						"name":       "default",
						"size":       "s-2vcpu-2gb",
						"node_count": 2,
						"auto_scale": false,
						"min_nodes":  3,
						"max_nodes":  5,
					},
				},
			},
			ErrContains: "min_nodes <= node_count <=",
		},
	}
}

func TestDoksModuleInvalidInputs(t *testing.T) {
	for name, tc := range getInvalidInputTestCases() {
		name := name
		tc := tc
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			localVars := make(map[string]interface{}, len(tc.Vars))
			for k, v := range tc.Vars {
				localVars[k] = v
			}
			_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
				SourceRootRel: "..",
				TfSubDir:      "examples/basic",
				Vars:          localVars,
				EnvVars:       testutil.TerraformEnvVars(t, map[string]string{"DIGITALOCEAN_TOKEN": "dummy"}),
			})
			_, err := terraform.InitAndPlanE(t, opts)
			require.Error(t, err)
			require.Regexp(t, regexp.MustCompile("(?i)"+regexp.QuoteMeta(tc.ErrContains)), err.Error())
		})
	}
}
