package testutil

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"testing"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/gruntwork-io/terratest/modules/test-structure"
)

// TerraformConfig bundles configuration for SetupTerraform.
//
// Example:
//
//	tfDir, opts := SetupTerraform(t, TerraformConfig{
//	        SourceRootRel: "..",
//	        TfSubDir:      "examples/basic",
//	        Vars:          map[string]interface{}{"foo": "bar"},
//	        EnvVars:       map[string]string{"DIGITALOCEAN_TOKEN": "dummy"},
//	})
//
// The function copies the Terraform configuration to a temporary directory,
// returning the directory path and execution options.
type TerraformConfig struct {
	SourceRootRel string
	TfSubDir      string
	Vars          map[string]interface{}
	EnvVars       map[string]string
}

// SetupTerraform copies a Terraform configuration to a temporary directory and
// returns its path and options for execution.
func SetupTerraform(t *testing.T, config TerraformConfig) (string, *terraform.Options) {
	t.Helper()
	if _, err := exec.LookPath("tofu"); err != nil {
		t.Skip("tofu not found; skipping Terraform-based tests")
	}
	tempRoot := test_structure.CopyTerraformFolderToTemp(t, config.SourceRootRel, ".")
	t.Cleanup(func() {
		if err := os.RemoveAll(tempRoot); err != nil {
			t.Logf("failed to clean up temporary directory %s: %v", tempRoot, err)
		}
	})
	tfDir := filepath.Join(tempRoot, config.TfSubDir)
	opts := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
		TerraformDir:    tfDir,
		TerraformBinary: "tofu",
		Vars:            config.Vars,
		EnvVars:         TerraformEnvVars(t, config.EnvVars),
		NoColor:         true,
	})
	return tfDir, opts
}

// TerraformEnv configures environment variables for Terraform CLI processes in
// tests. The helper ensures `TF_IN_AUTOMATION=1` is present and returns a fresh
// slice without mutating the parent process environment so parallel tests stay
// isolated.
//
// Example:
//
//	func TestPlan(t *testing.T) {
//	        cmd := exec.Command("tofu", "plan")
//	        cmd.Env = TerraformEnv(t, map[string]string{
//	                "DIGITALOCEAN_TOKEN": "dummy",
//	        })
//	        // cmd.Env now includes TF_IN_AUTOMATION=1 alongside the
//	        // additional variables passed above.
//	}
//
// TerraformEnv returns the merged Terraform environment slice suitable for
// assigning to an `exec.Cmd`. The helper includes a handful of essential host
// variables (currently PATH, HOME, and TMPDIR when present) so child processes
// can locate binaries and temporary directories without inheriting unrelated
// secrets from the parent shell.
func TerraformEnv(t testing.TB, extras map[string]string) []string {
	t.Helper()
	merged := TerraformEnvVars(t, extras)
	for _, key := range []string{"PATH", "HOME", "TMPDIR"} {
		if _, exists := merged[key]; exists {
			continue
		}
		if value, ok := os.LookupEnv(key); ok {
			merged[key] = value
		}
	}

	keys := make([]string, 0, len(merged))
	for key := range merged {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	env := make([]string, 0, len(keys))
	for _, key := range keys {
		env = append(env, fmt.Sprintf("%s=%s", key, merged[key]))
	}
	return env
}

// TerraformEnvVars merges Terraform-specific environment defaults with any
// caller-supplied overrides. The returned map includes `TF_IN_AUTOMATION=1` by
// default, which extras may override if necessary to emulate alternative
// automation contexts.
//
// Example:
//
//	opts := &terraform.Options{
//	        EnvVars: TerraformEnvVars(t, map[string]string{
//	                "DIGITALOCEAN_TOKEN": "dummy",
//	        }),
//	}
//
// The returned map may be passed directly to terratest helpers or other
// Terraform invocations.
func TerraformEnvVars(t testing.TB, extras map[string]string) map[string]string {
	t.Helper()
	env := map[string]string{"TF_IN_AUTOMATION": "1"}
	for key, value := range extras {
		env[key] = value
	}
	if _, exists := env["TF_PLUGIN_CACHE_DIR"]; !exists {
		cacheDir, err := os.UserCacheDir()
		if err != nil {
			t.Logf("unable to configure TF_PLUGIN_CACHE_DIR (os.UserCacheDir failed): %v", err)
			return env
		}
		if cacheDir == "" {
			t.Logf("unable to configure TF_PLUGIN_CACHE_DIR (os.UserCacheDir returned empty path)")
			return env
		}

		pluginCacheDir := filepath.Join(cacheDir, "nile-valley", "opentofu", "plugin-cache")
		if err := os.MkdirAll(pluginCacheDir, 0o755); err != nil {
			t.Logf(
				"unable to configure TF_PLUGIN_CACHE_DIR (os.MkdirAll(%s) failed): %v",
				pluginCacheDir,
				err,
			)
			return env
		}
		env["TF_PLUGIN_CACHE_DIR"] = pluginCacheDir
	}
	return env
}
