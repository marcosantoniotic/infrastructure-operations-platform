#!/usr/bin/env bash
set -euo pipefail

# Collects only publication-safe fields. It never reads container environment,
# labels, networks, addresses, published ports, secrets, mounts, logs or volume
# contents.

output_path="-"
source_json=""
logical_name="platform-host"

usage() {
  cat <<'EOF'
Usage:
  inventory-host.sh [--output PATH] [--logical-name NAME]
  inventory-host.sh --source-json PATH [--output PATH]

Live mode requires root access, Docker, Docker Compose and jq.
Fixture mode renders an already sanitized JSON document and is used by CI.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output_path="${2:?missing value for --output}"
      shift 2
      ;;
    --source-json)
      source_json="${2:?missing value for --source-json}"
      shift 2
      ;;
    --logical-name)
      logical_name="${2:?missing value for --logical-name}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v jq >/dev/null 2>&1 || {
  echo "jq is required." >&2
  exit 1
}

temporary_json=""
if [[ -z "$source_json" ]]; then
  command -v docker >/dev/null 2>&1 || {
    echo "Docker is required in live mode." >&2
    exit 1
  }

  temporary_json="$(mktemp)"
  trap 'rm -f -- "$temporary_json"' EXIT
  source_json="$temporary_json"

  # shellcheck disable=SC1091
  . /etc/os-release
  generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cpu_vcpu="$(nproc)"
  memory_gib="$(free -b | awk '/^Mem:/ {printf "%.1f", $2/1073741824}')"
  root_disk_gib="$(
    df -B1 --output=size / | awk 'NR == 2 {printf "%.1f", $1/1073741824}'
  )"
  root_used_percent="$(
    df --output=pcent / | awk 'NR == 2 {gsub(/%/, ""); print $1}'
  )"
  docker_engine="$(docker version --format '{{.Server.Version}}')"
  docker_compose="$(docker compose version --short)"
  projects_json="$(
    docker compose ls --format json |
      jq '[.[] | {name: .Name, status: .Status}]'
  )"
  containers_json="$(
    docker ps --format '{{json .}}' |
      jq -s '[.[] | {name: .Names, image: .Image, status: .Status}]'
  )"
  native_services_json="$(
    for service_name in docker firewalld zabbix-agent2; do
      enabled="$(systemctl is-enabled "$service_name" 2>/dev/null || true)"
      active="$(systemctl is-active "$service_name" 2>/dev/null || true)"
      jq -n \
        --arg name "$service_name" \
        --arg enabled "$enabled" \
        --arg active "$active" \
        '{name: $name, enabled: $enabled, active: $active}'
    done | jq -s '.'
  )"

  jq -n \
    --arg generated_at "$generated_at" \
    --arg logical_name "$logical_name" \
    --arg operating_system "$PRETTY_NAME" \
    --arg kernel "$(uname -r)" \
    --argjson cpu_vcpu "$cpu_vcpu" \
    --arg memory_gib "$memory_gib" \
    --arg root_disk_gib "$root_disk_gib" \
    --argjson root_used_percent "$root_used_percent" \
    --arg docker_engine "$docker_engine" \
    --arg docker_compose "$docker_compose" \
    --argjson projects "$projects_json" \
    --argjson containers "$containers_json" \
    --argjson native_services "$native_services_json" \
    '{
      schema_version: 1,
      generated_at: $generated_at,
      platform: {
        logical_name: $logical_name,
        operating_system: $operating_system,
        kernel: $kernel,
        deployment_model: "single-node"
      },
      resources: {
        cpu_vcpu: $cpu_vcpu,
        memory_gib: ($memory_gib | tonumber),
        root_disk_gib: ($root_disk_gib | tonumber),
        root_used_percent: $root_used_percent
      },
      runtime: {
        docker_engine: $docker_engine,
        docker_compose: $docker_compose
      },
      projects: $projects,
      containers: $containers,
      native_services: $native_services
    }' > "$source_json"
fi

jq -e '
  .schema_version == 1 and
  (.generated_at | type == "string") and
  (.platform.logical_name | type == "string") and
  (.projects | type == "array") and
  (.containers | type == "array") and
  (.native_services | type == "array") and
  ([
    paths(scalars) as $path |
    ($path | map(tostring) | join("."))
  ] | all(
    test("address|network|port|environment|secret|password|token|label|mount";
         "i") | not
  ))
' "$source_json" >/dev/null || {
  echo "Source inventory is invalid or contains a prohibited field." >&2
  exit 1
}

rendered="$(
  jq -r '
    "# Inventário sanitizado gerado automaticamente",
    "",
    "Data UTC: `\(.generated_at)`",
    "",
    "## Plataforma",
    "",
    "| Propriedade | Valor |",
    "|---|---|",
    "| Nome lógico | `\(.platform.logical_name)` |",
    "| Sistema operacional | \(.platform.operating_system) |",
    "| Kernel | `\(.platform.kernel)` |",
    "| Modelo de implantação | \(.platform.deployment_model) |",
    "",
    "## Capacidade",
    "",
    "| Recurso | Valor |",
    "|---|---:|",
    "| CPU | \(.resources.cpu_vcpu) vCPU |",
    "| Memória | \(.resources.memory_gib) GiB |",
    "| Disco raiz | \(.resources.root_disk_gib) GiB |",
    "| Uso do filesystem raiz | \(.resources.root_used_percent)% |",
    "",
    "## Runtime",
    "",
    "| Componente | Versão |",
    "|---|---|",
    "| Docker Engine | `\(.runtime.docker_engine)` |",
    "| Docker Compose | `\(.runtime.docker_compose)` |",
    "",
    "## Projetos Compose",
    "",
    "| Projeto | Estado sanitizado |",
    "|---|---|",
    (.projects[] | "| `\(.name)` | \(.status) |"),
    "",
    "## Containers",
    "",
    "| Container | Imagem | Estado sanitizado |",
    "|---|---|---|",
    (.containers[] | "| `\(.name)` | `\(.image)` | \(.status) |"),
    "",
    "## Serviços nativos",
    "",
    "| Serviço | Habilitado | Ativo |",
    "|---|---|---|",
    (.native_services[] |
      "| `\(.name)` | \(.enabled) | \(.active) |"),
    "",
    "## Campos deliberadamente excluídos",
    "",
    "- endereços, redes e portas;",
    "- variáveis de ambiente, labels e mounts;",
    "- segredos, tokens e conteúdo de volumes;",
    "- logs e dados das aplicações."
  ' "$source_json"
)"

if [[ "$output_path" == "-" ]]; then
  printf '%s\n' "$rendered"
else
  mkdir -p -- "$(dirname -- "$output_path")"
  printf '%s\n' "$rendered" > "$output_path"
  printf 'Sanitized inventory written to %s\n' "$output_path"
fi
