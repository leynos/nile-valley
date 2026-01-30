package tests

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"nile-valley/infra/testutil"
)

// TestREADMEDocumentsAllOutputs verifies that all outputs defined in outputs.tf
// are documented in README.md.
func TestREADMEDocumentsAllOutputs(t *testing.T) {
	t.Parallel()

	moduleDir := ".."
	readmePath := testutil.FilePath(filepath.Join(moduleDir, "README.md"))
	outputsPath := testutil.FilePath(filepath.Join(moduleDir, "outputs.tf"))

	// Extract output names from outputs.tf
	actualOutputs := testutil.ExtractHCLOutputNames(t, outputsPath)
	require.NotEmpty(t, actualOutputs, "outputs.tf should define at least one output")

	// Extract documented outputs from README.md
	documentedOutputs := testutil.ExtractREADMEOutputNames(t, readmePath)
	require.NotEmpty(t, documentedOutputs, "README.md should document at least one output")

	// Verify all actual outputs are documented
	for _, output := range actualOutputs {
		assert.Contains(t, documentedOutputs, output,
			"output %q is defined in outputs.tf but not documented in README.md", output)
	}

	// Verify README does not document outputs that are not defined in outputs.tf
	for _, output := range documentedOutputs {
		assert.Contains(t, actualOutputs, output,
			"output %q is documented in README.md but not defined in outputs.tf", output)
	}
}

// TestREADMEDocumentsAllRequiredInputs verifies that all required inputs are
// documented in README.md.
func TestREADMEDocumentsAllRequiredInputs(t *testing.T) {
	t.Parallel()

	moduleDir := ".."
	readmePath := testutil.FilePath(filepath.Join(moduleDir, "README.md"))

	// Find all variables files
	variablesFiles := []testutil.FilePath{
		testutil.FilePath(filepath.Join(moduleDir, "variables-core.tf")),
		testutil.FilePath(filepath.Join(moduleDir, "variables-cluster.tf")),
		testutil.FilePath(filepath.Join(moduleDir, "variables-credentials.tf")),
		testutil.FilePath(filepath.Join(moduleDir, "variables-tls.tf")),
	}

	// Extract all variable names from variables files
	var allVariables []string
	for _, vf := range variablesFiles {
		if _, err := os.Stat(string(vf)); err == nil {
			vars := testutil.ExtractHCLVariableNames(t, vf)
			allVariables = append(allVariables, vars...)
		}
	}
	require.NotEmpty(t, allVariables, "at least one variable should be defined")

	// Extract documented inputs from README.md
	documentedInputs := testutil.ExtractREADMEInputNames(t, readmePath)
	require.NotEmpty(t, documentedInputs, "README.md should document at least one input")

	// Verify all variables are documented
	for _, variable := range allVariables {
		assert.Contains(t, documentedInputs, variable,
			"variable %q is defined but not documented in README.md", variable)
	}

	// Verify README does not document inputs that are not defined as variables
	for _, documentedInput := range documentedInputs {
		assert.Contains(t, allVariables, documentedInput,
			"README.md documents input %q, but no matching variable is defined in variables-*.tf", documentedInput)
	}
}

// TestREADMEDocumentsSyncPolicyContract verifies that the sync_policy_contract
// output is documented with its structure.
func TestREADMEDocumentsSyncPolicyContract(t *testing.T) {
	t.Parallel()

	moduleDir := ".."
	readmePath := testutil.FilePath(filepath.Join(moduleDir, "README.md"))

	content, err := os.ReadFile(string(readmePath))
	require.NoError(t, err)

	readme := string(content)

	// Verify sync_policy_contract section exists
	assert.Contains(t, readme, "sync_policy_contract",
		"README.md should document sync_policy_contract output")

	// Verify key contract fields are documented
	assert.Contains(t, readme, "cluster",
		"sync_policy_contract documentation should include 'cluster' field")
	assert.Contains(t, readme, "endpoints",
		"sync_policy_contract documentation should include 'endpoints' field")
	assert.Contains(t, readme, "credentials",
		"sync_policy_contract documentation should include 'credentials' field")
	assert.Contains(t, readme, "tls",
		"sync_policy_contract documentation should include 'tls' field")
	assert.Contains(t, readme, "persistence",
		"sync_policy_contract documentation should include 'persistence' field")
	assert.Contains(t, readme, "replication",
		"sync_policy_contract documentation should include 'replication' field")
}
