output "bucket" {
  description = "Bucket de dados (entrada/, processado/, rejeitado/, artefatos/)."
  value       = aws_s3_bucket.dados.id
}

output "lambda" {
  description = "Nome da Lambda."
  value       = aws_lambda_function.processador.function_name
}

output "topico_alertas_arn" {
  description = "ARN do tópico SNS de alertas."
  value       = aws_sns_topic.alertas.arn
}

output "dlq_url" {
  description = "URL da fila DLQ."
  value       = aws_sqs_queue.dlq.url
}

output "comando_upload_exemplo" {
  description = "Exemplo de upload que dispara o pipeline."
  value       = "aws s3 cp dados/amostras/precos-gasolina-etanol-2026-10.csv s3://${aws_s3_bucket.dados.id}/entrada/"
}
