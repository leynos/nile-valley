package tests

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
	testutil "nile-valley/infra/testutil"
)

func testVars() map[string]interface{} {
	return map[string]interface{}{
		"cluster_name": "nile-valley-preview",
		"region":       "nyc1",
		"node_pools": []map[string]interface{}{
			{
				"name":       "default",
				"size":       "s-2vcpu-2gb",
				"node_count": 2,
				"auto_scale": false,
				"min_nodes":  2,
				"max_nodes":  2,
				"tags":       []string{"env:preview"},
			},
		},
		"tags":              []string{"env:preview"},
		"expose_kubeconfig": false,
		"flux_install":      false,
	}
}

func TestNileValleyInfraK8sValidate(t *testing.T) {
	t.Parallel()
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "../../..",
		TfSubDir:      "clusters/nile-valley-infra-k8s",
		Vars:          testVars(),
	})
	terraform.InitAndValidate(t, opts)
}

func TestNileValleyInfraK8sPlanUnauthenticated(t *testing.T) {
	t.Parallel()
	if os.Getenv("DIGITALOCEAN_TOKEN") != "" {
		t.Skip("DIGITALOCEAN_TOKEN set; skipping unauthenticated plan")
	}
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "../../..",
		TfSubDir:      "clusters/nile-valley-infra-k8s",
		Vars:          testVars(),
	})
	_, err := terraform.InitAndPlanE(t, opts)
	require.NoError(t, err)
}

func TestNileValleyInfraK8sPlanDetailedExitCode(t *testing.T) {
	t.Parallel()
	token := os.Getenv("DIGITALOCEAN_TOKEN")
	if token == "" {
		t.Skip("DIGITALOCEAN_TOKEN not set; skipping detailed exit code plan")
	}
	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "../../..",
		TfSubDir:      "clusters/nile-valley-infra-k8s",
		Vars:          testVars(),
		EnvVars:       map[string]string{"DIGITALOCEAN_TOKEN": token},
	})
	terraform.Init(t, opts)
	args := terraform.FormatArgs(opts, "plan", "-input=false", "-no-color", "-detailed-exitcode")
	cmd := exec.Command("tofu", args...)
	cmd.Dir = opts.TerraformDir
	cmd.Env = testutil.TerraformEnv(t, opts.EnvVars)
	err := cmd.Run()
	if err == nil {
		t.Fatalf("expected exit code 2 (changes present), got 0")
	}
	exitErr, ok := err.(*exec.ExitError)
	require.True(t, ok, "expected ExitError")
	require.Equal(t, 2, exitErr.ExitCode())
}

func TestNileValleyInfraK8sPolicy(t *testing.T) {
	t.Parallel()
	token := os.Getenv("DIGITALOCEAN_TOKEN")
	if token == "" {
		t.Skip("DIGITALOCEAN_TOKEN not set; skipping policy test")
	}
	if _, err := exec.LookPath("conftest"); err != nil {
		t.Skip("conftest not found; skipping policy test")
	}
	tfDir, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "../../..",
		TfSubDir:      "clusters/nile-valley-infra-k8s",
		Vars:          testVars(),
		EnvVars:       map[string]string{"DIGITALOCEAN_TOKEN": token},
	})
	planFile := filepath.Join(tfDir, "tfplan.binary")
	opts.PlanFilePath = planFile
	terraform.InitAndPlan(t, opts)
	t.Cleanup(func() { _ = os.Remove(planFile) })

	show, err := terraform.RunTerraformCommandE(t, opts, "show", "-json", planFile)
	require.NoError(t, err)
	planJSON := filepath.Join(tfDir, "plan.json")
	require.NoError(t, os.WriteFile(planJSON, []byte(show), 0600))
	t.Cleanup(func() { _ = os.Remove(planJSON) })

	policyRoot := filepath.Join(tfDir, "..", "..", "modules", "doks", "policy")
	clusterPolicy := filepath.Join(tfDir, "policy")
	cmd := exec.Command(
		"conftest",
		"test",
		planJSON,
		"--policy",
		policyRoot,
		"--policy",
		clusterPolicy,
	)
	cmd.Env = testutil.TerraformEnv(t, nil)
	out, err := cmd.CombinedOutput()
	require.NoErrorf(t, err, "conftest failed: %s", string(out))
}

func TestNileValleyInfraK8sFluxRequiresKubeconfig(t *testing.T) {
	t.Parallel()
	vars := testVars()
	vars["flux_install"] = true
	vars["flux_kubeconfig_path"] = ""

	_, opts := testutil.SetupTerraform(t, testutil.TerraformConfig{
		SourceRootRel: "../../..",
		TfSubDir:      "clusters/nile-valley-infra-k8s",
		Vars:          vars,
	})
	_, err := terraform.InitAndPlanE(t, opts)
	require.Error(t, err)
	require.Contains(t, err.Error(), "flux_kubeconfig_path")
}
