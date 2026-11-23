variable "regiao" {
  description = "Região da AWS."
  type        = string
  default     = "us-east-1"
}

variable "projeto" {
  description = "Prefixo dos nomes dos recursos."
  type        = string
  default     = "pipeline-eventos-anp"
}

variable "email_alertas" {
  description = "E-mail que recebe os alertas do SNS. Definir só no terraform.tfvars (fora do git)."
  type        = string
  sensitive   = true
}

variable "memoria_lambda_mb" {
  description = "Memória da Lambda em MB."
  type        = number
  default     = 1024
}

variable "timeout_lambda_segundos" {
  description = "Tempo máximo de execução da Lambda."
  type        = number
  default     = 120
}

variable "retencao_logs_dias" {
  description = "Retenção dos logs da Lambda no CloudWatch."
  type        = number
  default     = 7
}
