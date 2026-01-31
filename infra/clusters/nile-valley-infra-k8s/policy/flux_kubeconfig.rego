package nile_valley_infra_k8s.policy

deny contains msg if {
  flux_install := object.get(input.variables, "flux_install", {"value": false}).value
  flux_install
  kubeconfig := object.get(input.variables, "flux_kubeconfig_path", {"value": null}).value
  kubeconfig == null
  msg := "flux_install requires flux_kubeconfig_path to be set"
}

deny contains msg if {
  flux_install := object.get(input.variables, "flux_install", {"value": false}).value
  flux_install
  kubeconfig := object.get(input.variables, "flux_kubeconfig_path", {"value": ""}).value
  trim_space(kubeconfig) == ""
  msg := "flux_install requires flux_kubeconfig_path to be set"
}
