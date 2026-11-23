resource "aws_sns_topic" "alertas" {
  name = "${local.nome_base}-alertas"
}

# A assinatura por e-mail precisa ser confirmada pelo link que a AWS envia.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = var.email_alertas
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.nome_base}-dlq"
  message_retention_seconds = 1209600 # 14 dias (máximo)
  sqs_managed_sse_enabled   = true    # criptografia gerenciada pelo SQS, sem KMS
}

resource "aws_cloudwatch_metric_alarm" "dlq_com_mensagens" {
  alarm_name          = "${local.nome_base}-dlq-com-mensagens"
  alarm_description   = "Falha de infra/bug na Lambda: há eventos na DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}
