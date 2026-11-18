terraform {
  required_providers {
    docker = { source = "kreuzwerker/docker" }
  }
}

variable "prefix" { type = string }
variable "app_port" { type = number }
variable "enable_models" { type = bool }
variable "build_context" { type = string }

locals {
  # Same pins as compose.yaml.
  db_image     = "pgvector/pgvector:0.8.7-pg18-trixie@sha256:ab49524d18df7200b74ac9a475e1db6297fc1eb57da4c214c63d10ecc4b754fa"
  embed_image  = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.3@sha256:ad950d30878eceb72aaf32024d26fa2b1d04a75304fa0b4776b49aa1941fea07"
  ollama_image = "ollama/ollama:0.40.15@sha256:0e59999e0e8f9fd4e704bd788a89b7e4cad399367fb1365f8c102ac662288761"
  models       = var.enable_models ? 1 : 0
  # Rebuild the app image when any of these change.
  app_src = ["Dockerfile", "requirements.txt", "server/**", "translate_svc/**", "import_tools/**",
  "web/app/**", "web/lib/**", "web/*.json", "web/*.ts", "web/*.mjs"]
}

resource "docker_network" "net" {
  name = var.prefix
}

resource "docker_volume" "pg" {
  name = "${var.prefix}-pg"
}

resource "docker_image" "db" {
  name         = local.db_image
  keep_locally = true
}

resource "docker_image" "app" {
  name = "${var.prefix}-app:local"
  build {
    context = var.build_context
  }
  triggers = {
    src = sha1(join("", [
      for f in sort(flatten([for p in local.app_src : fileset(var.build_context, p)])) :
      filesha1("${var.build_context}/${f}") if !strcontains(f, "__pycache__")
    ]))
  }
}

resource "docker_container" "db" {
  name  = "${var.prefix}-db"
  image = docker_image.db.image_id
  env   = ["POSTGRES_USER=mbxread", "POSTGRES_PASSWORD=mbxread", "POSTGRES_DB=mbxread"]
  networks_advanced {
    name    = docker_network.net.id
    aliases = ["db"]
  }
  volumes {
    volume_name    = docker_volume.pg.name
    container_path = "/var/lib/postgresql"
  }
  healthcheck {
    test     = ["CMD", "pg_isready", "-U", "mbxread", "-d", "mbxread"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }
  wait         = true
  wait_timeout = 120
}

resource "docker_volume" "embed" {
  count = local.models
  name  = "${var.prefix}-embed"
}

resource "docker_image" "embed" {
  count        = local.models
  name         = local.embed_image
  keep_locally = true
}

resource "docker_container" "embed" {
  count   = local.models
  name    = "${var.prefix}-embed"
  image   = docker_image.embed[0].image_id
  command = ["--model-id", "BAAI/bge-m3", "--revision", "5617a9f61b028005a4858fdac845db406aefb181"]
  networks_advanced {
    name    = docker_network.net.id
    aliases = ["embed"]
  }
  volumes {
    volume_name    = docker_volume.embed[0].name
    container_path = "/data"
  }
}

resource "docker_volume" "ollama" {
  count = local.models
  name  = "${var.prefix}-ollama"
}

resource "docker_image" "ollama" {
  count        = local.models
  name         = local.ollama_image
  keep_locally = true
}

resource "docker_container" "ollama" {
  count = local.models
  name  = "${var.prefix}-ollama"
  image = docker_image.ollama[0].image_id
  gpus  = "all"
  networks_advanced {
    name    = docker_network.net.id
    aliases = ["ollama"]
  }
  volumes {
    volume_name    = docker_volume.ollama[0].name
    container_path = "/root/.ollama"
  }
}

resource "docker_container" "app" {
  name  = "${var.prefix}-app"
  image = docker_image.app.image_id
  env = [
    "DATABASE_URL=postgresql://mbxread:mbxread@db:5432/mbxread",
    "EMBED_URL=${var.enable_models ? "http://embed:80" : ""}",
    "OLLAMA_URL=http://ollama:11434",
  ]
  networks_advanced {
    name = docker_network.net.id
  }
  ports {
    internal = 8002
    external = var.app_port
    ip       = "127.0.0.1"
  }
  wait         = true
  wait_timeout = 180
  depends_on   = [docker_container.db]
}

output "app_url" {
  value = "http://127.0.0.1:${var.app_port}"
}
