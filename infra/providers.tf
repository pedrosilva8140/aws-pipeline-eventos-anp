terraform {
  required_version = ">= 1.17.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State local (fora do git, ver .gitignore). Tudo é destruído no fim do projeto.
}

provider "aws" {
  region = var.regiao

  default_tags {
    tags = {
      Projeto    = var.projeto
      Gerenciado = "terraform"
    }
  }
}

data "aws_caller_identity" "atual" {}

locals {
  nome_base       = var.projeto
  nome_bucket     = "${var.projeto}-${data.aws_caller_identity.atual.account_id}"
  nome_lambda     = "${var.projeto}-processador"
  caminho_pacote  = "${path.module}/build/lambda.zip"
  chave_pacote    = "artefatos/lambda/lambda.zip"
  prefixo_entrada = "entrada/"
}
