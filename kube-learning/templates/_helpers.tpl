{{/* Expand the name of the chart. */}}
{{- define "kube-learning.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified application name. */}}
{{- define "kube-learning.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := include "kube-learning.name" . }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Chart labels shared by Kubernetes resources. */}}
{{- define "kube-learning.labels" -}}
helm.sh/chart: {{ include "kube-learning.chart" . }}
{{ include "kube-learning.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Chart name and version, suitable for a label value. */}}
{{- define "kube-learning.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Immutable labels used by the Deployment and Service selectors. */}}
{{- define "kube-learning.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-learning.name" . }}
{{- end }}

{{/* Service account name, whether it is created by this chart or supplied externally. */}}
{{- define "kube-learning.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kube-learning.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
