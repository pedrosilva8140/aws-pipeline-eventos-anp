resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.nome_lambda}"
  retention_in_days = var.retencao_logs_dias
}

resource "aws_lambda_function" "processador" {
  function_name = local.nome_lambda
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "processador.handler.lambda_handler"
  memory_size   = var.memoria_lambda_mb
  timeout       = var.timeout_lambda_segundos

  # Sem layer: dependências vão no pacote (ver arquivo local de regras do projeto).
  # O pacote vem do S3 porque passa do limite de upload direto (50 MB zipado).
  s3_bucket        = aws_s3_object.pacote_lambda.bucket
  s3_key           = aws_s3_object.pacote_lambda.key
  source_code_hash = filebase64sha256(local.caminho_pacote)

  environment {
    variables = {
      TOPICO_ALERTAS_ARN = aws_sns_topic.alertas.arn
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  # O log group precisa existir antes, senão a Lambda cria um sem retenção.
  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
}

# Falha de infra/bug: 2 novas tentativas assíncronas e, depois, o evento vai para a DLQ.
resource "aws_lambda_function_event_invoke_config" "processador" {
  function_name          = aws_lambda_function.processador.function_name
  maximum_retry_attempts = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.dlq.arn
    }
  }
}

resource "aws_lambda_permission" "s3_invoca_lambda" {
  statement_id   = "PermitirS3Invocar"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.processador.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.dados.arn
  source_account = data.aws_caller_identity.atual.account_id
}
