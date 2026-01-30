package testutil

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// envEntriesToMap converts VAR=value slices into a map for easier assertions.
func envEntriesToMap(entries []string) map[string]string {
	env := make(map[string]string, len(entries))
	for _, entry := range entries {
		parts := strings.SplitN(entry, "=", 2)
		if len(parts) != 2 {
			continue
		}
		env[parts[0]] = parts[1]
	}
	return env
}

// parseEnvOutput converts the output from the `env` command to a map so tests
// can assert on individual keys.
func parseEnvOutput(output string) map[string]string {
	lines := strings.Split(strings.TrimSpace(output), "\n")
	env := make(map[string]string, len(lines))
	for _, line := range lines {
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		env[parts[0]] = parts[1]
	}
	return env
}

func TestTerraformEnvVarsIncludesAutomation(t *testing.T) {
	t.Parallel()
	env := TerraformEnvVars(t, nil)
	if got := env["TF_IN_AUTOMATION"]; got != "1" {
		t.Fatalf("TF_IN_AUTOMATION mismatch: want 1, got %q", got)
	}
}

func TestTerraformEnvVarsMergesExtras(t *testing.T) {
	t.Parallel()
	extras := map[string]string{"FOO": "bar"}
	env := TerraformEnvVars(t, extras)
	if got := env["FOO"]; got != "bar" {
		t.Fatalf("expected FOO=bar, got %q", got)
	}
	if _, ok := extras["TF_IN_AUTOMATION"]; ok {
		t.Fatalf("extras map was mutated: %v", extras)
	}
}

func TestTerraformEnvVarsAllowsOverrides(t *testing.T) {
	t.Parallel()
	env := TerraformEnvVars(t, map[string]string{"TF_IN_AUTOMATION": "0"})
	if got := env["TF_IN_AUTOMATION"]; got != "0" {
		t.Fatalf("expected override to win, got %q", got)
	}
}

func TestTerraformEnvVarsConfiguresPluginCacheDir(t *testing.T) {
	cacheHome := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", cacheHome)

	env := TerraformEnvVars(t, nil)

	pluginCacheDir, ok := env["TF_PLUGIN_CACHE_DIR"]
	if !ok {
		t.Fatalf("expected TF_PLUGIN_CACHE_DIR to be set when XDG_CACHE_HOME is writable")
	}

	expected := filepath.Join(cacheHome, "nile-valley", "opentofu", "plugin-cache")
	if pluginCacheDir != expected {
		t.Fatalf("TF_PLUGIN_CACHE_DIR mismatch: want %q, got %q", expected, pluginCacheDir)
	}

	if _, err := os.Stat(expected); err != nil {
		t.Fatalf("expected TF_PLUGIN_CACHE_DIR to exist on disk: %v", err)
	}
}

func TestTerraformEnvVarsRespectsExistingPluginCacheDir(t *testing.T) {
	cacheHome := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", cacheHome)

	extras := map[string]string{"TF_PLUGIN_CACHE_DIR": "/tmp/nile-valley-plugin-cache"}
	env := TerraformEnvVars(t, extras)

	if got := env["TF_PLUGIN_CACHE_DIR"]; got != extras["TF_PLUGIN_CACHE_DIR"] {
		t.Fatalf("expected TF_PLUGIN_CACHE_DIR override to win, got %q", got)
	}
	if _, ok := extras["TF_IN_AUTOMATION"]; ok {
		t.Fatalf("extras map was mutated: %v", extras)
	}

	expectedDefault := filepath.Join(cacheHome, "nile-valley", "opentofu", "plugin-cache")
	if _, err := os.Stat(expectedDefault); err == nil {
		t.Fatalf("did not expect default plugin cache directory %s to be created when override is set", expectedDefault)
	}
}

func TestTerraformEnvDoesNotMutateProcessEnvironment(t *testing.T) {
	const fooKey = "WILDSIDE_TERRAFORM_ENV_FOO"

	t.Setenv("PATH", "/tmp/nile-valley:test")
	t.Setenv("SHOULD_NOT_LEAK", "1")
	t.Setenv(fooKey, "existing")

	envSlice := TerraformEnv(t, map[string]string{fooKey: "override"})
	env := envEntriesToMap(envSlice)

	if got := os.Getenv(fooKey); got != "existing" {
		t.Fatalf("process environment mutated for %s: got %q", fooKey, got)
	}
	if got := env[fooKey]; got != "override" {
		t.Fatalf("env slice missing override for %s, got %q", fooKey, got)
	}
	if got := env["TF_IN_AUTOMATION"]; got != "1" {
		t.Fatalf("env slice missing TF_IN_AUTOMATION=1 entry, got %q", got)
	}
	if got := env["PATH"]; got != "/tmp/nile-valley:test" {
		t.Fatalf("env slice did not propagate PATH, got %q", got)
	}
	if _, ok := env["SHOULD_NOT_LEAK"]; ok {
		t.Fatalf("env slice leaked parent variable: %v", env)
	}
}

func TestTerraformEnvIsolatesPerTest(t *testing.T) {
	const key = "WILDSIDE_TERRAFORM_ENV_ISOLATION"

	t.Run("first", func(t *testing.T) {
		envSlice := TerraformEnv(t, map[string]string{key: "one"})
		env := envEntriesToMap(envSlice)
		if got := env[key]; got != "one" {
			t.Fatalf("env slice missing override, got %q", got)
		}
		if _, ok := os.LookupEnv(key); ok {
			t.Fatalf("process environment mutated for key %q", key)
		}
	})

	t.Run("second", func(t *testing.T) {
		if value, ok := os.LookupEnv(key); ok {
			t.Fatalf("expected %s to be unset after previous subtest, found %q", key, value)
		}
		TerraformEnv(t, map[string]string{key: "two"})
	})
}

func TestTerraformEnvAppliesToCommands(t *testing.T) {
	t.Setenv("SHOULD_NOT_LEAK", "1")
	envSlice := TerraformEnv(t, map[string]string{"FOO": "bar"})

	cmd := exec.Command("env")
	cmd.Env = envSlice
	output, err := cmd.Output()
	if err != nil {
		t.Fatalf("env command failed: %v", err)
	}

	env := parseEnvOutput(string(output))
	if got := env["FOO"]; got != "bar" {
		t.Fatalf("expected child env to contain FOO=bar, got %q", got)
	}
	if got := env["TF_IN_AUTOMATION"]; got != "1" {
		t.Fatalf("expected child env to contain TF_IN_AUTOMATION=1, got %q", got)
	}
	if _, ok := env["SHOULD_NOT_LEAK"]; ok {
		t.Fatalf("child env leaked parent variable: %v", env)
	}
}

func TestTerraformEnvIncludesPluginCacheDir(t *testing.T) {
	cacheHome := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", cacheHome)

	envSlice := TerraformEnv(t, nil)
	env := envEntriesToMap(envSlice)

	pluginCacheDir, ok := env["TF_PLUGIN_CACHE_DIR"]
	if !ok {
		t.Fatalf("expected TerraformEnv to include TF_PLUGIN_CACHE_DIR when XDG_CACHE_HOME is writable")
	}

	expected := filepath.Join(cacheHome, "nile-valley", "opentofu", "plugin-cache")
	if pluginCacheDir != expected {
		t.Fatalf("TF_PLUGIN_CACHE_DIR mismatch: want %q, got %q", expected, pluginCacheDir)
	}
}

func TestTerraformEnvHandlesNilExtras(t *testing.T) {
	envSlice := TerraformEnv(t, nil)
	env := envEntriesToMap(envSlice)
	if got := env["TF_IN_AUTOMATION"]; got != "1" {
		t.Fatalf("expected automation flag for nil extras, got %q", got)
	}
}

func TestSetupTerraformRemovesTemporaryDirectory(t *testing.T) {
	if _, err := exec.LookPath("tofu"); err != nil {
		t.Skip("tofu not found; skipping SetupTerraform cleanup test")
	}

	sourceDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(sourceDir, "main.tf"), []byte(`terraform {}`), 0o600); err != nil {
		t.Fatalf("failed to write test terraform config: %v", err)
	}

	var tempDir string
	t.Run("setup", func(t *testing.T) {
		tfDir, _ := SetupTerraform(t, TerraformConfig{
			SourceRootRel: sourceDir,
			TfSubDir:      ".",
		})
		tempDir = tfDir
		if tempDir == "" {
			t.Fatal("expected SetupTerraform to return a non-empty temp directory path")
		}
		if _, err := os.Stat(tempDir); err != nil {
			t.Fatalf("expected temp directory %s to exist during subtest: %v", tempDir, err)
		}
	})

	if tempDir == "" {
		t.Fatal("expected SetupTerraform subtest to capture a temp directory path")
	}
	if _, err := os.Stat(tempDir); err == nil || !os.IsNotExist(err) {
		t.Fatalf("expected temp directory %s to be removed after cleanup, got err=%v", tempDir, err)
	}
}
