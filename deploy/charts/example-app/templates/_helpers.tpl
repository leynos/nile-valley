{{- define "example-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "example-app.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "example-app.name" . -}}
{{- if eq .Release.Name $name -}}
{{- $name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "example-app.labels" -}}
app.kubernetes.io/name: {{ include "example-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "example-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "example-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Validate that secretEnvFromKeys references an existing Secret when set.

- Requires .Values.existingSecretName when secretEnvFromKeys has entries.
- Optionally fails if the Secret is missing and allowMissingSecret is false.
- Validates that listed keys exist within the referenced Secret.
*/}}
{{- define "example-app.validateSecrets" -}}
{{- $raw := .Values.secretEnvFromKeys -}}
{{- if and $raw (not (kindIs "map" $raw)) -}}
{{- fail (printf "secretEnvFromKeys must be a map, got %s" (typeOf $raw)) -}}
{{- end -}}
{{- $sec := $raw | default dict -}}
{{- $name := .Values.existingSecretName -}}
{{- $allowMissing := .Values.allowMissingSecret | default true -}}
{{- if and (gt (len $sec) 0) (not $name) -}}
{{- fail "existingSecretName is required when secretEnvFromKeys is set" -}}
{{- end -}}
{{- if and (gt (len $sec) 0) $name -}}
{{- if not (semverCompare ">=3.2.0" .Capabilities.HelmVersion.Version) -}}
{{- fail "example-app.validateSecrets requires Helm >= 3.2.0" -}}
{{- end -}}
  {{- $found := lookup "v1" "Secret" .Release.Namespace $name -}}
  {{- $missingSecret := or (not $found) (and (kindIs "slice" $found) (eq (len $found) 0)) -}}
  {{- if and $missingSecret (not $allowMissing) -}}
  {{- fail (printf "Secret %q not found in namespace %q" $name .Release.Namespace) -}}
  {{- end -}}
  {{- if not $missingSecret -}}
{{- $data := (get $found "data") | default dict -}}
{{- $stringData := (get $found "stringData") | default dict -}}
{{- $missing := list -}}
{{- range $k, $secretKey := $sec -}}
{{- if not (regexMatch "^[A-Za-z_][A-Za-z0-9_]*$" $k) -}}
{{- fail (printf "secretEnvFromKeys has invalid env var name %q (must match ^[A-Za-z_][A-Za-z0-9_]*$)" $k) -}}
{{- end -}}
{{- if not $secretKey -}}
{{- fail (printf "secretEnvFromKeys maps %q to an empty secret key" $k) -}}
{{- end -}}
{{- if not (or (hasKey $data $secretKey) (hasKey $stringData $secretKey)) -}}
{{- $missing = append $missing $secretKey -}}
{{- end -}}
{{- end -}}
{{- if gt (len $missing) 0 -}}
{{- fail (printf "Secret %q missing keys: %s" $name (join ", " $missing)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
