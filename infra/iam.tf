data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.nome_lambda}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "LerEApagarEntrada"
    actions   = ["s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.dados.arn}/${local.prefixo_entrada}*"]
  }

  # Sem ListBucket, o S3 responde AccessDenied (e não NoSuchKey) para arquivo inexistente,
  # e o handler não conseguiria tratar a retentativa como "já processado".
  statement {
    sid       = "ListarEntrada"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.dados.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.prefixo_entrada}*"]
    }
  }

  statement {
    sid     = "GravarSaidas"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.dados.arn}/processado/*",
      "${aws_s3_bucket.dados.arn}/rejeitado/*",
    ]
  }

  statement {
    sid       = "PublicarAlertas"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alertas.arn]
  }

  statement {
    sid       = "EnviarParaDlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.nome_lambda}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
